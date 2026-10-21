import unittest
import uuid
from unittest.mock import Mock

import psycopg
import test_bill_entry as bills
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

URL=bills.URL


@unittest.skipUnless(URL,'TEST_DATABASE_URL is required')
class StatementTests(unittest.TestCase):
    setUp=bills.BillEntryTests.setUp
    launch=bills.BillEntryTests.launch
    execute_discovery=bills.BillEntryTests.execute_discovery
    tally_discovery=bills.BillEntryTests.tally_discovery

    LAYOUT={'columns':{'date':{'column':1,'order':'dmy'},'amount':{'mode':'debit_credit','debit':3,'credit':4},
        'balance':{'column':5},'reference':{'column':2},'narration':{'columns':[]},'account':None,
        'routing_hint':{'column':6,'label':'Branch'}},'row_order':'oldest_first',
        'rows':{'opening':[{'column':1,'starts_with':'Opening balance'}]},'evidence':'Headings on row 1; balances reconcile.'}

    def learn_layout(self, run, file, *, answer='dmy'):
        """Answer the layout session for a new bank format, then its one date-order question."""
        from minkops_platform.accounts.worker import process
        with psycopg.connect(URL,row_factory=dict_row) as c:
            child=c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s AND config->>'stage'='layout'",(run['id'],)).fetchone()
            if child is None: return None
            self.assertEqual(c.execute('SELECT config FROM account_runs WHERE id=%s',(run['id'],)).fetchone()['config']['awaits'],
                             {'layout_run':str(child['id'])})
            process(c,child,executor=lambda *a,**k:{'layouts':[{'source_file_id':file,'sheet':'','header_row':1,**self.LAYOUT}],'exceptions':[]})
            item=c.execute("SELECT * FROM attention_items WHERE task_id=%s AND kind='layout' AND status='pending'",(run['task_id'],)).fetchone()
        if item and answer:
            decided=self.client.post(f"/api/tenants/mock-tenant/attention/{item['id']}/profile",headers=self.csrf,json={'action':answer})
            self.assertEqual(decided.status_code,200,decided.text)
        return item

    TEXT='Date,Reference,Debit,Credit,Balance,Branch\nOpening balance,,,,1000,\n01/10/26,OUT1,11,,989,Test\n02/10/26,IN1,,17,1006,Test\n02/10/26,HOLD,3,,1003,Unknown branch\n'

    def ready(self, *, with_mapping=False, text=None, statuses=('ready','ready','held'), proposals=None):
        discovery=self.tally_discovery('statement-company',voucher_types=('Purchase','Payment','Receipt','Contra'))
        with psycopg.connect(URL,row_factory=dict_row) as c:
            catalog=c.execute('SELECT catalog FROM discovery_runs WHERE id=%s',(discovery,)).fetchone()['catalog']
            records=catalog['sources'][0]['snapshot']['companies'][0]['masters']['records']
            records.extend({'type':'LEDGER','data':{'NAME':name,'GUID':name+'-guid','ALTERID':'1','PARENT':parent}}
                for name,parent in [('Bank','Bank Accounts'),('Expense','Indirect Expenses'),('ICICI','Bank Accounts')])
            for record in records:
                if record['type']=='VOUCHERTYPE': record['data'].update(GUID=record['data']['NAME']+'-guid',PARENT=record['data']['NAME'])
            c.execute('UPDATE discovery_runs SET catalog=%s WHERE id=%s',(Jsonb(catalog),discovery))
        summary=self.client.get(f'/api/tenants/mock-tenant/discovery/latest?device_id={self.device["id"]}').json()
        company=summary['catalog']['sources'][0]['snapshot']['companies'][0]
        self.assertNotIn('records',company['masters'])
        self.assertEqual(company['statement_options']['banks'],[{'name':'Bank','guid':'Bank-guid'},{'name':'ICICI','guid':'ICICI-guid'}])
        text=text or self.TEXT
        file=self.client.post(self.base+'/sources',headers=self.csrf,data={'paths':'["statement.csv"]'},
            files=[('files',('statement.csv',text.encode('utf-8-sig')))]).json()['files'][0]['id']
        mapping=None
        if with_mapping:
            mapping=self.client.post(self.base+'/sources',headers=self.csrf,data={'paths':'["branch-mapping.csv"]'},
                files=[('files',('branch-mapping.csv',b'Client code,Meaning\n17,Test company\n'))]).json()['files'][0]['id']
        run,_=self.launch('statement-entry',file_ids=[file],config={'discovery_id':discovery,'branch_mapping_file_id':mapping})
        from minkops_platform.accounts.worker import process
        self.learn_layout(run,file)
        def interpret(key,files,context,on_event,**kwargs):
            self.assertEqual(key,'statement-entry')
            self.assertEqual(context['branch_mapping_file_id'],mapping)
            self.assertEqual(len(context['transactions']),len(statuses))
            self.assertEqual({r['source_file_id'] for r in context['transactions']},{file})
            self.assertTrue(context['source_catalog']['companies'][0]['master_lookup_path'])
            self.assertTrue(any(f['path'].endswith('masters-lookup-v1-0.json') for f in files))
            if mapping:self.assertTrue(any(str(f['id'])==mapping for f in files))
            on_event('agent.session.created','statement-session-'+str(uuid.uuid4()),'turn')
            if proposals: return {'records':proposals(context['transactions'],file)}
            return {'records':[{'source_file_id':file,'sheet':'','row':r['row'],
                'company_guid':'statement-company','bank_ledger_guid':'Bank-guid','counter_ledger_guid':'Expense-guid',
                'voucher_type_guid':('Payment' if r['amount_cents']<0 else 'Receipt')+'-guid',
                'cost_centre_guid':None,'cost_category_guid':None,'evidence':'Statement account and discovered expense allocation.',
                'exception':{'code':'branch_unresolved','detail':'Client label has no supported meaning.'} if r['reference']=='HOLD' else None}
                for r in context['transactions']]}
        executor=Mock(side_effect=interpret)
        with psycopg.connect(URL,row_factory=dict_row) as c:
            process(c,c.execute('SELECT * FROM account_runs WHERE id=%s',(run['id'],)).fetchone(),executor=executor)
        executor.assert_called_once()
        loaded=self.client.get(self.base+f"/runs/{run['id']}").json()
        with psycopg.connect(URL,row_factory=dict_row) as c:
            from minkops_platform.accounts.repository import run_for
            internal=run_for(c,run['tenant_id'],run['id'])
        self.assertTrue(internal['session_id'])
        self.assertNotIn('execution_snapshot',loaded['config'])
        self.assertEqual(internal['config']['execution_snapshot']['execution']['model'],'gpt-6-luna')
        self.assertEqual([r['status'] for r in loaded['result']['records']],list(statuses))
        # Test setup needs pinned identities for subsequent launches, not a
        # public status response containing the private execution evidence.
        return {**loaded,'config':internal['config']}

    def statement(self, name, text):
        return self.client.post(self.base+'/sources',headers=self.csrf,data={'paths':f'["{name}"]'},
            files=[('files',(name,text.encode('utf-8-sig')))]).json()['files'][0]['id']

    def layout_children(self, run):
        with psycopg.connect(URL,row_factory=dict_row) as c:
            return c.execute("SELECT * FROM account_runs WHERE parent_run_id=%s AND config->>'stage'='layout'",(run['id'],)).fetchall()

    def test_one_learned_layout_reads_every_matching_file_and_sheet(self):
        from datetime import date

        from minkops_platform.accounts.statement_layouts import parse, resolve

        run = self.ready()
        files = [{'id': str(uuid.uuid4()), 'path': name, 'content': self.TEXT.encode()}
                 for name in ('first.csv', 'overlap.csv')]
        with psycopg.connect(URL, row_factory=dict_row) as c:
            tenant = c.execute('SELECT tenant_id FROM workflow_runs WHERE id=%s', (run['id'],)).fetchone()
            entries = resolve(c, tenant['tenant_id'], files)
        self.assertTrue(all('profile' in entry for entry in entries),
                        'Every sheet sharing the learned header must receive the layout.')
        rows = parse(entries, today=date(2026, 10, 20))
        self.assertEqual(len(rows), 6)
        self.assertFalse(any(r.get('code') == 'statement_layout_unknown' for r in rows))

    def config(self, run):
        with psycopg.connect(URL,row_factory=dict_row) as c:
            return c.execute('SELECT config FROM account_runs WHERE id=%s',(run['id'],)).fetchone()['config']

    def test_a_transfer_between_own_banks_is_written_once_and_settles_both_rows(self):
        text='Date,Reference,Debit,Credit,Balance,Branch\nOpening balance,,,,1000,\n01/10/26,TO-ICICI,500,,500,Test\n01/10/26,FROM-HDFC,,500,1000,Test\n'
        def transfer(rows,file):
            out,into=rows
            def leg(r, bank, other, mate):
                return {'source_file_id':file,'sheet':'','row':r['row'],'company_guid':'statement-company',
                            'bank_ledger_guid':bank,'counter_ledger_guid':other,'voucher_type_guid':'Contra-guid','family':'contra',
                            'pair':{'source_file_id':file,'sheet':'','row':mate['row']},'cost_centre_guid':None,'cost_category_guid':None,
                            'evidence':'Same-day transfer between the two own accounts.','exception':None}
            return [leg(out,'Bank-guid','ICICI-guid',into),leg(into,'ICICI-guid','Bank-guid',out)]
        run=self.ready(text=text,statuses=('ready','ready'),proposals=transfer)
        approved=self.client.post(self.base+f"/runs/{run['id']}/approve",headers=self.csrf,json={'result':{'action':'write_ready'}})
        self.assertEqual(approved.status_code,200,approved.text)
        with psycopg.connect(URL) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM account_tally_writes WHERE run_id=%s',(run['id'],)).fetchone()[0],1)
        job=self.client.post('/api/desktop/worker/claim',headers=self.worker,json={}).json()
        route=f"/api/desktop/worker/jobs/{job['id']}"
        plan=self.client.get(route+'/plan?claim_token='+job['claim_token'],headers={**self.worker,'X-Minkops-Plan-Version':'5'}).json()
        self.assertEqual((plan['family'],[(ln['ledger'],ln['side']) for ln in plan['lines']]),('contra',[('Bank','credit'),('ICICI','debit')]))
        older=self.client.get(route+'/plan?claim_token='+job['claim_token'],headers={**self.worker,'X-Minkops-Plan-Version':'4'})
        self.assertEqual(older.status_code,409)
        current={'guid':'a1b2c3d4-0000-4000-8000-000000000009','master_id':'9','date':'20261001','voucher_type':'Contra',
            'family':'contra','reference':plan['header']['reference'],'number':'','narration':'','party_ledger':'','tag':plan['remote_id'],
            'lines':[{'ledger':'Bank','amount_cents':50000},{'ledger':'ICICI','amount_cents':-50000}],'allocations':[],'fingerprint':'v5:'+'d'*64}
        finished=self.client.post(route+'/finish',headers=self.worker,json={'claim_token':job['claim_token'],
            'result':{'outcome':'saved','company_guid':'statement-company','current':current}})
        self.assertEqual(finished.status_code,200,finished.text)
        rows=self.client.get(self.base+f"/runs/{run['id']}").json()['result']['records']
        self.assertEqual([r['status'] for r in rows],['saved','duplicate'])

    def test_a_known_bank_format_is_read_with_no_layout_session(self):
        first=self.ready()
        file=self.statement('next-week.csv','Date,Reference,Debit,Credit,Balance,Branch\n03/10/26,OUT2,6,,1000,Test\n')
        run,_=self.launch('statement-entry',file_ids=[file],config={'discovery_id':first['config']['discovery_id'],'branch_mapping_file_id':None})
        self.assertEqual(self.layout_children(run),[])
        self.assertNotIn('awaits',self.config(run))

    def test_a_saved_layout_refuted_by_new_balances_is_inferred_once(self):
        first = self.ready()
        text = 'Date,Reference,Debit,Credit,Balance,Branch\n03/10/26,A,6,,1012,Test\n04/10/26,B,2,,1014,Test\n'
        file = self.statement('changed.csv', text)
        run, _ = self.launch('statement-entry', file_ids=[file],
                             config={'discovery_id': first['config']['discovery_id'], 'branch_mapping_file_id': None})
        self.assertEqual(len(self.layout_children(run)), 1,
                         'A learned header cannot hide a changed amount interpretation.')
        # A second failed reading must hold; it must not create an inference loop.
        self.learn_layout(run, file)
        from minkops_platform.accounts.worker import process
        with psycopg.connect(URL, row_factory=dict_row) as c:
            process(c, c.execute('SELECT * FROM account_runs WHERE id=%s', (run['id'],)).fetchone(),
                    executor=lambda *a, **k: {'records': []})
        rows = self.client.get(self.base + f"/runs/{run['id']}").json()['result']['records']
        self.assertEqual({r['code'] for r in rows}, {'statement_layout_changed'})
        self.assertEqual(len(self.layout_children(run)), 1)

    def test_new_statement_launch_requires_the_protocol_five_companion_release(self):
        first = self.ready()
        with psycopg.connect(URL) as c:
            c.execute("UPDATE desktop_devices SET companion_version='0.8.1' WHERE id=%s", (self.device['id'],))
        response = self.client.post(self.base + '/runs', headers=self.csrf, json={
            'key': 'statement-entry', 'request_key': str(uuid.uuid4()), 'file_ids': first['file_ids'],
            'config': {'discovery_id': first['config']['discovery_id']}})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn('0.9.0', response.text)

    def test_an_unanswered_date_question_keeps_the_run_waiting(self):
        first=self.ready()
        text='Txn Date,Reference,Debit,Credit,Balance,Branch\nOpening balance,,,,500,\n01/10/26,A,1,,499,X\n02/10/26,B,1,,498,X\n'
        run,_=self.launch('statement-entry',file_ids=[self.statement('question.csv',text)],
                          config={'discovery_id':first['config']['discovery_id'],'branch_mapping_file_id':None})
        item=self.learn_layout(run,str(self.layout_children(run)[0]['file_ids'][0]),answer=None)
        self.assertEqual((item['label'],item['target']['actions']),('Choose date order',['dmy','mdy']))
        self.assertIn('01/10/26', item['target']['prompt'])
        self.assertNotIn('2026-10-01', item['target']['prompt'])
        self.assertIn('awaits',self.config(run))
        listed=next(i for i in self.client.get('/api/tenants/mock-tenant/attention').json() if i['id']==str(item['id']))
        self.assertEqual(listed['layout']['actions'],['dmy','mdy'])
        public=self.client.get(self.base+f"/runs/{run['id']}").json()
        self.assertEqual(public['execution']['stage'],'awaiting_input')
        self.assertEqual(public['blockers'][0]['attention_item_id'],str(item['id']))
        with psycopg.connect(URL) as c:
            c.execute('UPDATE worker_wakeup SET acknowledged=generation,lease_until=NULL,dispatch_token=NULL')
        answered=self.client.post(f"/api/tenants/mock-tenant/attention/{item['id']}/profile",headers=self.csrf,json={'action':'mdy'})
        self.assertEqual(answered.status_code,200,answered.text)
        self.assertNotIn('awaits',self.config(run))
        from minkops_platform.worker_hosting import dispatch
        calls=[]
        self.assertTrue(dispatch(URL,lambda:calls.append(True)))
        self.assertEqual(calls,[True])
        again=self.client.post(f"/api/tenants/mock-tenant/attention/{item['id']}/profile",headers=self.csrf,json={'action':'mdy'})
        self.assertEqual(again.status_code,200,again.text)
        self.assertEqual(again.json(),answered.json())
        self.assertEqual(self.client.get(f"/api/tenants/mock-tenant/attention/{item['id']}/decision").json(),answered.json())
        with psycopg.connect(URL,row_factory=dict_row) as c:
            learned=c.execute("SELECT payload FROM client_profiles WHERE kind='statement_layout' AND provenance->>'file'='question.csv' AND status='active'").fetchone()
        self.assertEqual(learned['payload']['columns']['date']['order'],'mdy')

    def test_balances_that_refute_a_layout_never_store_it_and_the_sheet_holds(self):
        from minkops_platform.accounts.worker import process
        first=self.ready()
        text='Posting Date,Reference,Debit,Credit,Balance,Branch\n01/10/26,A,10,,90,X\n15/10/26,B,10,,80,X\n'
        file=self.statement('refuted.csv',text)
        run,_=self.launch('statement-entry',file_ids=[file],config={'discovery_id':first['config']['discovery_id'],'branch_mapping_file_id':None})
        swapped={**self.LAYOUT,'columns':{**self.LAYOUT['columns'],'amount':{'mode':'debit_credit','debit':4,'credit':3}}}
        with psycopg.connect(URL,row_factory=dict_row) as c:
            child=self.layout_children(run)[0]
            process(c,child,executor=lambda *a,**k:{'layouts':[{'source_file_id':file,'sheet':'','header_row':1,**swapped}],'exceptions':[]})
            self.assertIsNone(c.execute("SELECT 1 FROM client_profiles WHERE kind='statement_layout' AND provenance->>'file'='refuted.csv'").fetchone())
        config=self.config(run)
        self.assertNotIn('awaits',config)
        self.assertTrue(config['layouts_attempted'])
        with psycopg.connect(URL,row_factory=dict_row) as c:
            process(c,c.execute('SELECT * FROM account_runs WHERE id=%s',(run['id'],)).fetchone(),executor=lambda *a,**k:{'records':[]})
        held=self.client.get(self.base+f"/runs/{run['id']}").json()['result']['records']
        self.assertEqual([(r['code'],r['status']) for r in held],[('statement_layout_unknown','held')])

    def test_footer_controls_after_the_table_cannot_be_confirmed_over_a_mismatch(self):
        from minkops_platform.accounts.worker import process
        first=self.ready()
        text=('Footer Txn Date,Reference,Debit,Credit,Balance,Branch\n'
              '01/Sep/2026,A,10,,90,Test\n02/Sep/2026,B,,5,95,Test\n'
              'Page Total\nOpening Bal:,100\nWithdrawls:,10\nDeposits:,5\nClosing Bal:,96\n')
        file=self.statement('footer-refuted.csv',text)
        run,_=self.launch('statement-entry',file_ids=[file],config={
            'discovery_id':first['config']['discovery_id'],'branch_mapping_file_id':None})
        spec={**self.LAYOUT,'rows':{'ends_at':[{'column':1,'starts_with':'Page Total'}],
             'summary':[{'kind':kind,'column':1,'starts_with':label,'value_column':2}
                        for kind,label in [('opening','Opening Bal:'),('debit','Withdrawls:'),
                                           ('credit','Deposits:'),('closing','Closing Bal:')]]}}
        with psycopg.connect(URL,row_factory=dict_row) as c:
            process(c,self.layout_children(run)[0],executor=lambda *a,**k:{
                'layouts':[{'source_file_id':file,'sheet':'','header_row':1,**spec}],'exceptions':[]})
            self.assertIsNone(c.execute("SELECT 1 FROM client_profiles WHERE kind='statement_layout' "
                                        "AND provenance->>'file'='footer-refuted.csv'").fetchone())
            self.assertIsNone(c.execute("SELECT 1 FROM attention_items WHERE task_id=%s AND kind='layout' "
                                        "AND status='pending'",(run['task_id'],)).fetchone())

    def test_a_gap_between_consecutive_statements_raises_one_attention_item(self):
        first=self.ready()
        self.assertEqual(first['result']['chain_ends']['statement-company:Bank'],
                         {'opening_cents':100000,'from':'2026-10-01','closing_cents':100600,'to':'2026-10-02'})
        second=self.ready(text='Date,Reference,Debit,Credit,Balance,Branch\n05/10/26,OUT9,10,,1090,Test\n',statuses=('ready',))
        with psycopg.connect(URL,row_factory=dict_row) as c:
            item=c.execute("SELECT label,target FROM attention_items WHERE event_key=%s",
                           (f"statement:{second['id']}:statement-company:Bank:gap",)).fetchone()
        self.assertEqual(item['label'],'Transactions missing')
        self.assertIn('closed at 1006.00 on 2026-10-02',item['target']['reason'])
        self.assertEqual([r['status'] for r in second['result']['records']],['ready'])

    def test_device_poll_does_not_block_approved_statement_intents(self):
        from minkops_platform import desktop
        from minkops_platform.accounts.statements import StatementHandler
        run = self.ready()
        # A poll holds its authentication lock while observing a workflow.
        # Finishing that workflow must still persist its device FK and enqueue
        # its native job; otherwise the two paths form a device/run deadlock.
        with psycopg.connect(URL, row_factory=dict_row) as poll:
            desktop.authenticate(poll, self.device['credential'])
            with psycopg.connect(URL, row_factory=dict_row) as writer:
                writer.execute("SET LOCAL lock_timeout = '250ms'")
                row = writer.execute('SELECT * FROM account_runs WHERE id=%s FOR NO KEY UPDATE', (run['id'],)).fetchone()
                StatementHandler().approve(writer, {'id':row['tenant_id']}, {'id':row['actor_id']}, row, {'action':'write_ready'})
                self.assertEqual(writer.execute('SELECT count(*) FROM account_tally_writes WHERE run_id=%s', (run['id'],)).fetchone()['count'], 2)
                self.assertEqual(writer.execute("SELECT count(*) FROM desktop_jobs WHERE task_id=%s AND operation='tally.statement'", (run['task_id'],)).fetchone()['count'], 1)
                writer.rollback()

    def test_protocol_five_companion_saves_statement_rows_as_verified_v5_vouchers(self):
        run=self.ready()
        approved=self.client.post(self.base+f"/runs/{run['id']}/approve",headers=self.csrf,json={'result':{'action':'write_ready'}})
        self.assertEqual(approved.status_code,200,approved.text)
        for _ in range(2):
            job=self.client.post('/api/desktop/worker/claim',headers=self.worker,json={}).json()
            route=f"/api/desktop/worker/jobs/{job['id']}"
            plan=self.client.get(route+'/plan?claim_token='+job['claim_token'],headers={**self.worker,'X-Minkops-Plan-Version':'5'}).json()
            self.assertEqual((plan['format_version'],plan['fence'],plan['header']['tag'],plan['duplicate']['strategy']),(5,'strict','statement','tag'))
            self.assertIn(plan['family'],('payment','receipt'))
            current={'guid':'a1b2c3d4-0000-4000-8000-000000000007','master_id':'5','date':plan['header']['date'].replace('-',''),
                'voucher_type':plan['voucher_type']['NAME'],'family':plan['family'],'reference':plan['header']['reference'],'number':'',
                'narration':f"[Minkops statement:{plan['remote_id']}] {plan['header']['narration']}",'party_ledger':'','tag':plan['remote_id'],
                'lines':sorted(({'ledger':ln['ledger'],'amount_cents':ln['amount_cents'] if ln['side']=='credit' else -ln['amount_cents']} for ln in plan['lines']),key=lambda e:e['ledger']),
                'allocations':[],'fingerprint':'v5:'+'c'*64}
            receipt={'claim_token':job['claim_token'],'result':{'outcome':'saved','company_guid':'statement-company','current':current}}
            tampered={**receipt,'result':{**receipt['result'],'current':{**current,'tag':None}}}
            self.assertEqual(self.client.post(route+'/finish',headers=self.worker,json=tampered).status_code,422)
            finished=self.client.post(route+'/finish',headers=self.worker,json=receipt)
            self.assertEqual(finished.status_code,200,finished.text)
        updated=self.client.get(self.base+f"/runs/{run['id']}").json()
        self.assertEqual([r['status'] for r in updated['result']['records']],['saved','saved','held'])
        saved=updated['result']['records'][0]['current']
        self.assertEqual((saved['allocation'],saved['fingerprint'][:3],len(saved['entries'])),(None,'v5:',2))

    def test_private_ai_preview_manifest_serial_receipts_and_csv(self):
        run=self.ready()
        csv=self.client.get(self.base+f"/runs/{run['id']}/statement-exceptions.csv")
        self.assertEqual(csv.status_code,200,csv.text)
        self.assertTrue(csv.content.startswith(b'\xef\xbb\xbf'))
        approved=self.client.post(self.base+f"/runs/{run['id']}/approve",headers=self.csrf,json={'result':{'action':'write_ready'}})
        self.assertEqual(approved.status_code,200,approved.text)
        with psycopg.connect(URL) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM account_tally_writes WHERE run_id=%s',(run['id'],)).fetchone()[0],2)
            self.assertEqual(c.execute("SELECT count(*) FROM desktop_jobs WHERE task_id=%s AND operation='tally.statement'",(run['task_id'],)).fetchone()[0],1)
        for _ in range(2):
            job=self.client.post('/api/desktop/worker/claim',headers=self.worker,json={}).json()
            route=f"/api/desktop/worker/jobs/{job['id']}"
            query='/plan?claim_token='+job['claim_token']
            self.assertEqual(self.client.get(route+query,headers={**self.worker,'X-Minkops-Plan-Version':'3'}).status_code,409)
            plan=self.client.get(route+query,headers={**self.worker,'X-Minkops-Plan-Version':'4'}).json()
            data=plan['data']
            current={'guid':'native-'+str(uuid.uuid4()),'fingerprint':'fingerprint','tag':plan['remote_id'],
                'date':data['date'].replace('-',''),'voucher_type':plan['voucher_type']['NAME'],'allocation':None,
                'entries':sorted([{'ledger':'Bank','amount':-data['amount_cents']},{'ledger':'Expense','amount':data['amount_cents']}],key=lambda e:e['ledger'])}
            receipt={'claim_token':job['claim_token'],'result':{'outcome':'saved','company_guid':'statement-company','current':current}}
            current['entries'][0]['amount']+=1
            self.assertEqual(self.client.post(route+'/finish',headers=self.worker,json=receipt).status_code,422)
            current['entries'][0]['amount']-=1
            finished=self.client.post(route+'/finish',headers=self.worker,json=receipt)
            self.assertEqual(finished.status_code,200,finished.text)
            self.assertEqual(self.client.post(route+'/finish',headers=self.worker,json=receipt).status_code,200)
        updated=self.client.get(self.base+f"/runs/{run['id']}").json()
        self.assertEqual([r['status'] for r in updated['result']['records']],['saved','saved','held'])
        pending=self.client.get('/api/tenants/mock-tenant/attention?status=pending').json()
        self.assertEqual(len([a for a in pending if a['task_id']==run['task_id']]),1)
        self.assertEqual(self.client.get(f"/api/tenants/pr-infra/accounts/runs/{run['id']}/statement-exceptions.csv").status_code,404)
        self.assertNotIn('OUT1',self.client.get(self.base+f"/runs/{run['id']}/statement-exceptions.csv").text)

    def test_optional_mapping_is_authorized_and_never_parsed_as_transactions(self):
        run=self.ready(with_mapping=True)
        self.assertEqual(len(run['file_ids']),1)
        self.assertNotIn(run['config']['branch_mapping_file_id'],run['file_ids'])
        self.assertEqual(len(run['result']['records']),3)

    def test_mapping_reuse_unknown_mapping_and_legacy_settings_fail_before_ai(self):
        run=self.ready()
        for changes,status in [({'branch_mapping_file_id':run['file_ids'][0]},422),
            ({'branch_mapping_file_id':str(uuid.uuid4())},404),({'other_side_ledger':'Expense'},422),
            ({'bank_ledgers':{'statement-company':'Bank'}},422)]:
            response=self.client.post(self.base+'/runs',headers=self.csrf,json={'key':'statement-entry','request_key':str(uuid.uuid4()),
                'file_ids':run['file_ids'],'config':{'discovery_id':run['config']['discovery_id'],**changes}})
            self.assertEqual(response.status_code,status,response.text)

    def test_older_discovery_is_rejected_even_if_its_collection_config_differs(self):
        run=self.ready()
        newer=self.tally_discovery('statement-company',voucher_types=('Purchase','Payment','Receipt'))
        with psycopg.connect(URL) as c:
            c.execute('UPDATE discovery_runs SET device_id=%s,config=jsonb_set(config,\'{period,from}\',\'"2026-09-01"\') WHERE id=%s',
                (run['config']['statement_device_id'],newer))
        response=self.client.post(self.base+'/runs',headers=self.csrf,json={'key':'statement-entry','request_key':str(uuid.uuid4()),
            'file_ids':run['file_ids'],'config':{'discovery_id':run['config']['discovery_id']}})
        self.assertEqual(response.status_code,422,response.text)
        self.assertIn('latest',response.text)

    def test_pause_stop_and_wrong_operation_cannot_dispatch_statement_writes(self):
        run=self.ready()
        paused=self.client.post(f"/api/tenants/mock-tenant/tasks/{run['task_id']}/control",headers=self.csrf,json={'action':'pause'})
        self.assertEqual(paused.status_code,200,paused.text)
        self.assertEqual(self.client.post(self.base+f"/runs/{run['id']}/approve",headers=self.csrf,json={'result':{'action':'write_ready'}}).status_code,409)
        self.client.post(f"/api/tenants/mock-tenant/tasks/{run['task_id']}/control",headers=self.csrf,json={'action':'resume'})
        self.client.post(self.base+f"/runs/{run['id']}/approve",headers=self.csrf,json={'result':{'action':'write_ready'}})
        loaded=self.client.get(self.base+f"/runs/{run['id']}").json()
        wrong=self.client.post(self.native+'/jobs',headers=self.csrf,json={'device_id':self.device['id'],'request_key':str(uuid.uuid4()),
            'operation':'tally.save','input':{'run_id':run['id'],'write_id':loaded['tally_writes'][0]['id']}})
        self.assertEqual(wrong.status_code,422,wrong.text)
        stopped=self.client.post(f"/api/tenants/mock-tenant/tasks/{run['task_id']}/control",headers=self.csrf,json={'action':'stop'})
        self.assertEqual(stopped.status_code,200,stopped.text)
        self.assertIsNone(self.client.post('/api/desktop/worker/claim',headers=self.worker,json={}).json())
        loaded=self.client.get(self.base+f"/runs/{run['id']}").json()
        self.assertEqual(loaded['state'],'stopped')
        self.assertTrue(all(r['code']=='run_stopped' for r in loaded['result']['records']))

    def test_stop_during_raw_agent_result_persistence_does_not_require_native_row_state(self):
        run=self.ready()
        # The shared lifecycle persists provider JSON before validating it. Stop
        # may arrive in that interval; raw choices do not have native statuses.
        raw={'records':[{'source_file_id':run['file_ids'][0],'sheet':'','row':3}]}
        with psycopg.connect(URL) as c:
            c.execute("UPDATE account_runs SET state='executing',result=%s WHERE id=%s",(Jsonb(raw),run['id']))
        response=self.client.post(f"/api/tenants/mock-tenant/tasks/{run['task_id']}/control",headers=self.csrf,json={'action':'stop'})
        self.assertEqual(response.status_code,200,response.text)
        loaded=self.client.get(self.base+f"/runs/{run['id']}").json()
        self.assertEqual(loaded['state'],'stopped')
        self.assertEqual(loaded['result']['records'][0]['code'],'run_stopped')
        self.assertFalse(loaded['tally_writes'])

