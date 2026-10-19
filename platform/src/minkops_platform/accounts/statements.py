"""Deterministic statement lifecycle and immutable native write manifest.

One native voucher is dispatched at a time. Every approved intent is durable
before the first import; a receipt independently verifies the observed voucher.
"""
import copy
import json
from collections import Counter
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from minkops_connectors.statement import parse_statement
from minkops_platform import attention, desktop
from minkops_platform.errors import ServiceError
from minkops_platform.runtime.launch import LaunchInputs
from minkops_platform.run_controls import require_active, control_state
from minkops_platform.workflows import resolve_run_config
from .handlers import AccountsHandler
from .repository import files_for, run_for, observe
from .statement_routing import route, named
from .client_context import master_lookup


def companies(context):
    return [c for s in context['sources'] if s['tool']=='tally' for c in s.get('snapshot',{}).get('companies',[])]


def operator(run, user):
    if run['workflow_key']!='statement-entry' or run['actor_id']!=user['id']:
        raise ServiceError('forbidden','Only this statement run operator can authorize its writes.')


def sync_attention(connection, run, result):
    for file_id in run['file_ids']:
        rows=[r for r in result['records'] if r['source_file_id']==file_id and r.get('code')]
        key=f"statement:{run['id']}:{file_id}:exceptions"
        if rows:
            counts=Counter(r['code'] for r in rows)
            identifier=next(f['path'] for f in run['config']['file_provenance'] if f['id']==file_id)
            reason=f"{len(rows)} statement rows need attention. Open the task for row details and exception CSV."
            item=attention.record(connection,run,key,identifier,'Statement exceptions',target={'reason':reason},actor=run['actor_id'])
            connection.execute('UPDATE attention_items SET target=%s WHERE id=%s',
                (Jsonb({'reason':reason,'counts':dict(counts)}),item['id']))
        else:
            connection.execute("UPDATE attention_items SET status='done',done_at=now(),done_by=%s WHERE tenant_id=%s AND event_key=%s AND status='pending'",
                (run['actor_id'],run['tenant_id'],key))


def complete(connection, run, result):
    sync_attention(connection,run,result)
    pending=connection.execute('SELECT count(*) AS n FROM account_tally_writes WHERE tenant_id=%s AND run_id=%s AND finished_at IS NULL AND cancelled_at IS NULL',
        (run['tenant_id'],run['id'])).fetchone()['n']
    state='writing' if pending else 'review' if any(r['status'] not in ('saved','duplicate','rejected') for r in result['records']) else 'completed'
    connection.execute('UPDATE account_runs SET result=%s WHERE tenant_id=%s AND id=%s',(Jsonb(result),run['tenant_id'],run['id']))
    observe(connection,run,state,{'writing':'Saving and verifying statement vouchers on your PC.',
        'review':'Review the statement preview and exception rows.', 'completed':'Statement saves verified. Exact overlaps were skipped.'}[state],100 if state=='completed' else 70)


def dispatch_next(connection, run):
    if control_state(connection,run['tenant_id'],run['task_id'])!='active': return
    if connection.execute("SELECT 1 FROM desktop_jobs WHERE tenant_id=%s AND task_id=%s AND operation='tally.statement' AND state IN ('queued','executing') LIMIT 1",
        (run['tenant_id'],run['task_id'])).fetchone(): return
    row=connection.execute('SELECT * FROM account_tally_writes WHERE tenant_id=%s AND run_id=%s AND finished_at IS NULL AND cancelled_at IS NULL ORDER BY record_index LIMIT 1',
        (run['tenant_id'],run['id'])).fetchone()
    if row: desktop.enqueue_approved(connection,run,row['device_id'],'tally.statement',row['id'])


class StatementHandler(AccountsHandler):
    deterministic=True
    queued_summary='Queued for deterministic statement checks.'
    executing_summary='Checking statement rows and running balances without a model.'

    def prepare_launch(self, connection, tenant, user, body, workflow, definition):
        ids=body['file_ids']
        if len(ids)!=len(set(ids)): raise ValueError('Select each statement file once.')
        files=files_for(connection,tenant['id'],ids)
        if any(not f['current'] for f in files): raise ValueError('Refresh changed source files first.')
        if any(Path(f['path']).suffix.lower() not in ('.csv','.xlsx') for f in files):
            raise ValueError('Statement entry accepts CSV and XLSX. Convert legacy XLS files in Excel.')
        if sum(len(f['content']) for f in files)>30_000_000: raise ValueError('Select at most 30 MB of statements.')
        from minkops_platform.discovery import workflow_context, get_run
        discovery_id=body['config'].get('discovery_id')
        if not discovery_id: raise ValueError('Confirm complete Source Discovery first.')
        found=get_run(connection,tenant['id'],discovery_id)
        if found['actor_id']!=user['id']: raise ValueError('Confirm Source Discovery with this operator account.')
        device=desktop.owned_device(connection,tenant['id'],user['id'],found['device_id'])
        desktop.require_companion(device,minimum=(0,8,0))
        if body.get('destination_device_id') and str(device['id'])!=str(body['destination_device_id']):
            raise ValueError('Source Discovery belongs to a different destination PC.')
        context=workflow_context(connection,tenant['id'],discovery_id,['tally'])
        selection={**body['config'],'source_ids':list({str(f['source_id']) for f in files})}
        config=resolve_run_config(definition,workflow['config_values'],selection,
            allowed_source_ids=set(selection['source_ids']),allowed_destination_ids=set())
        if not config['other_side_ledger'].strip(): raise ValueError('Choose the Other-side ledger before starting.')
        # Validate each explicitly enabled destination, while rows for unknown
        # branches remain exceptions in the preview instead of blocking siblings.
        available={c['company_guid']:c for c in companies(context)}
        if not config.get('bank_ledgers'): raise ValueError('Choose a bank ledger for at least one discovered company.')
        for guid, bank in config['bank_ledgers'].items():
            if guid not in available: raise ValueError('The bank destination is outside Source Discovery.')
            records=master_lookup(available[guid])['records']
            if len(named(records,'LEDGER',bank))!=1 or len(named(records,'LEDGER',config['other_side_ledger']))!=1:
                raise ValueError('Choose discovered Bank and Other-side ledgers for each selected company.')
        return LaunchInputs(files,ids,None,config,{'statement_context':context,'statement_device_id':str(device['id'])})

    def prepare(self, connection, run):
        return files_for(connection,run['tenant_id'],run['file_ids']),{},{}

    def execute(self, run, files, context, domain):
        result={'records':[],'findings':[]}
        for file in files:
            for row in parse_statement(bytes(file['content']),Path(file['path']).suffix,run['config']):
                row.update(source_file_id=str(file['id']),source_file=file['path'],status='held' if row.get('code') else 'ready')
                if not row.get('code'):
                    try:
                        resolved=route(row,companies(run['config']['statement_context']),run['config'])
                        key=f"statement:{resolved['company_guid']}:{resolved['data']['bank_ledger']}"
                        token=str(uuid5(NAMESPACE_URL,f"minkops:{run['tenant_id']}:{key}:{row['identity']}"))
                        row.update(company=resolved['company'],company_guid=resolved['company_guid'],matched_kind=resolved['matched_kind'],
                            plan={**resolved,'format_version':4,'remote_id':token,'operation':'append','destination_key':key})
                    except ValueError as error:
                        row.update(code='statement_routing',reason=str(error),status='held')
                result['records'].append(row)
        groups={}
        for index,row in enumerate(result['records']):
            if row.get('plan') and not row.get('code'):
                groups.setdefault((row['plan']['destination_key'],row['identity']),[]).append(index)
        for indexes in groups.values():
            def accounting(index):
                plan=result['records'][index]['plan']; data=plan['data']
                return json.dumps([data['date'],data['amount_cents'],data['bank_ledger'],data['counter_ledger'],plan['voucher_type'],plan['allocation']],sort_keys=True)
            if len({accounting(i) for i in indexes})>1:
                for i in indexes: result['records'][i].update(status='held',code='statement_conflict',reason='Overlapping files route the same bank transaction differently. Correct the sources before saving.')
            else:
                for i in indexes[1:]: result['records'][i]['duplicate_of']=indexes[0]
        return result

    def validate(self, run, files, context, domain, result): return result

    def finish(self, connection, store, run, context, domain, result):
        complete(connection,run,result)
        if run['config']['review_mode']=='only_exceptions' and not result.get('requires_review'):
            self.approve(connection,{'id':run['tenant_id']},{'id':run['actor_id']},run,{'action':'write_ready'},result=result)

    def approve(self, connection, tenant, user, run, body, *, result=None):
        operator(run,user); require_active(connection,tenant['id'],run['task_id'])
        action=body.get('result',{}).get('action',body.get('action','write_ready'))
        if action not in ('write_ready','retry_saves','nothing'): raise ValueError('Choose an offered statement action.')
        result=copy.deepcopy(result if result is not None else run['result'])
        if action=='nothing':
            for row in result['records']:
                if row['status'] not in ('saved','duplicate','writing'): row['status']='rejected'
            complete(connection,run,result); return
        for index,row in enumerate(result['records']):
            if row.get('duplicate_of') is not None: continue
            eligible=row['status']=='ready' or (action=='retry_saves' and row.get('save_hold'))
            if not eligible or not row.get('plan'): continue
            plan=row['plan']
            try:
                with connection.transaction():
                    connection.execute('''INSERT INTO account_tally_writes(tenant_id,run_id,device_id,company,identity,record_index,plan,destination_key)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',(run['tenant_id'],run['id'],run['config']['statement_device_id'],
                        plan['company'],row['identity'],index,Jsonb(plan),plan['destination_key']))
                row['status']='writing'; row.pop('save_hold',None); row.pop('code',None); row.pop('reason',None)
            except UniqueViolation:
                row.update(status='held',code='statement_save_waiting',reason='Another approved run is reconciling this transaction. Finish it before retrying.',save_hold=True)
        for row in result['records']:
            if row.get('duplicate_of') is not None:
                original=result['records'][row['duplicate_of']]
                row['status']='duplicate' if original['status'] in ('saved','duplicate') else original['status']
        complete(connection,run,result)
        dispatch_next(connection,run)

    def on_resume(self, connection, run, user): dispatch_next(connection,run)

    def on_stop(self, connection, run, user):
        result=copy.deepcopy(run.get('result') or {'records':[]})
        for row in result['records']:
            if row['status'] not in ('saved','duplicate','rejected'):
                row.update(status='held',code='run_stopped',reason='The run was stopped before this row was saved. Verify any underway operation in Tally.')
        connection.execute('UPDATE account_runs SET result=%s WHERE tenant_id=%s AND id=%s',(Jsonb(result),run['tenant_id'],run['id']))
        sync_attention(connection,run,result)


def accept(connection, device, payload, receipt):
    from .tally_writes import spec
    run,write=spec(connection,device,payload,pending=False)
    if run['workflow_key']!='statement-entry': raise ServiceError('invalid','Not a statement write.')
    if not isinstance(receipt,dict) or receipt.get('outcome') not in ('saved','duplicate','attention'):
        raise ServiceError('invalid','Invalid statement receipt.')
    outcome=receipt['outcome']; plan=write['plan']; data=plan['data']
    verified=outcome in ('saved','duplicate')
    if verified:
        current=receipt.get('current',{})
        if (not isinstance(current,dict) or not isinstance(current.get('entries'),list)
            or any(not isinstance(e,dict) or set(e)!={'ledger','amount'} or type(e['amount']) is not int or not isinstance(e['ledger'],str) for e in current['entries'])):
            raise ServiceError('invalid','Invalid native statement entries.')
        expected=sorted([{'ledger':data['bank_ledger'],'amount':-data['amount_cents']},
            {'ledger':data['counter_ledger'],'amount':data['amount_cents']}],key=lambda e:e['ledger'])
        if (receipt.get('company_guid')!=plan['company_guid'] or current.get('tag')!=plan['remote_id']
            or current.get('date')!=data['date'].replace('-','') or current.get('voucher_type')!=plan['voucher_type']['NAME']
            or not isinstance(current.get('guid'),str) or not current['guid'] or not current.get('fingerprint')
            or current.get('allocation')!=plan.get('allocation') or current.get('entries')!=expected):
            raise ServiceError('invalid','Native statement readback differs from the approved manifest.')
    result=copy.deepcopy(run['result']); row=result['records'][write['record_index']]
    row['status']=outcome if verified else 'held'
    if verified:
        row.pop('code',None); row.pop('reason',None); row['current']=receipt['current']
    else:
        code=receipt.get('hold','statement_save_held')
        if code not in ('possible_existing','uncertain_import','destination_changed','company_not_open','no_company','duplicate_company','not_running','port_closed','busy','too_many','invalid_response'):
            code='statement_save_held'
        row.update(code=code,reason={'possible_existing':'A matching untagged voucher may already exist. Verify it in Tally before manual handling.',
            'uncertain_import':'The import was interrupted. Reconcile Tally; Minkops will not resend an uncertain import.'}.get(code,
            'The native save could not be verified. Check Tally and the selected company, then retry reconciliation.'),save_hold=True)
    for sibling in result['records']:
        if sibling.get('duplicate_of')==write['record_index']:
            sibling['status']='duplicate' if verified else 'held'
            if not verified: sibling.update(code=row['code'],reason=row['reason'],save_hold=True)
            else:
                sibling.pop('code',None); sibling.pop('reason',None); sibling.pop('save_hold',None)
    connection.execute('UPDATE account_tally_writes SET outcome=%s,receipt=%s,finished_at=now(),verified_at=CASE WHEN %s THEN now() ELSE NULL END WHERE id=%s',
        (outcome,Jsonb(receipt),verified,write['id']))
    complete(connection,run,result)
    # finish() still owns the current executing job. Queue the next only after
    # that job is marked terminal (desktop calls dispatch_next after persistence).
    return {'verified':verified,'outcome':outcome}


def export_csv(run):
    from .bill_review import exception_csv, export_unavailable
    unavailable=export_unavailable(run)
    if unavailable: raise ServiceError('conflict',unavailable)
    return exception_csv(['Source file','Sheet','Row','Branch','Date','Reference','Amount','Balance','Company','Status','Code','Reason'],[
        [r.get('source_file'),r.get('sheet'),r.get('row'),r.get('branch'),r.get('date'),r.get('reference'),
         r.get('amount_cents',0)/100 if 'amount_cents' in r else '',r.get('balance_cents',0)/100 if 'balance_cents' in r else '',
         r.get('company'),r['status'],r.get('code'),r.get('reason')]
        for r in run['result']['records'] if r['status'] not in ('saved','duplicate')])
