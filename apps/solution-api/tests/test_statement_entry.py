import unittest
import uuid
from unittest.mock import Mock, patch

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import test_bill_entry as bills

URL=bills.URL


@unittest.skipUnless(URL,'TEST_DATABASE_URL is required')
class StatementTests(unittest.TestCase):
    setUp=bills.BillEntryTests.setUp
    launch=bills.BillEntryTests.launch
    execute_discovery=bills.BillEntryTests.execute_discovery
    tally_discovery=bills.BillEntryTests.tally_discovery

    def ready(self):
        discovery=self.tally_discovery('statement-company',voucher_types=('Purchase','Payment','Receipt'))
        with psycopg.connect(URL,row_factory=dict_row) as c:
            catalog=c.execute('SELECT catalog FROM discovery_runs WHERE id=%s',(discovery,)).fetchone()['catalog']
            records=catalog['sources'][0]['snapshot']['companies'][0]['masters']['records']
            records.extend({'type':'LEDGER','data':{'NAME':name,'GUID':name+'-guid','ALTERID':'1','PARENT':parent}}
                for name,parent in [('Bank','Bank Accounts'),('Expense','Indirect Expenses')])
            for record in records:
                if record['type']=='VOUCHERTYPE': record['data'].update(GUID=record['data']['NAME']+'-guid',PARENT=record['data']['NAME'])
            c.execute('UPDATE discovery_runs SET catalog=%s WHERE id=%s',(Jsonb(catalog),discovery))
        text='Date,Reference,Debit,Credit,Balance,Branch\nOpening balance,,,,1000,\n01/10/26,OUT1,11,,989,Test\n02/10/26,IN1,,17,1006,Test\n02/10/26,HOLD,3,,1003,Unknown branch\n'
        file=self.client.post(self.base+'/sources',headers=self.csrf,data={'paths':'["statement.csv"]'},
            files=[('files',('statement.csv',text.encode('utf-8-sig')))]).json()['files'][0]['id']
        run,_=self.launch('statement-entry',file_ids=[file],config={'discovery_id':discovery,'bank_ledgers':{'statement-company':'Bank'},'other_side_ledger':'Expense'})
        from minkops_platform.accounts.worker import process
        executor=Mock(side_effect=AssertionError('Bank rows must never reach a model'))
        with patch('minkops_platform.runtime.lifecycle.execute_proposal',side_effect=AssertionError('No hosted path')):
            with psycopg.connect(URL,row_factory=dict_row) as c:
                process(c,c.execute('SELECT * FROM account_runs WHERE id=%s',(run['id'],)).fetchone(),executor=executor)
        executor.assert_not_called()
        loaded=self.client.get(self.base+f"/runs/{run['id']}").json()
        self.assertIsNone(loaded['session_id'])
        self.assertIsNone(loaded['config']['execution_snapshot'])
        self.assertEqual([r['status'] for r in loaded['result']['records']],['ready','ready','held'])
        return loaded

    def test_private_non_ai_preview_manifest_serial_receipts_and_csv(self):
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

