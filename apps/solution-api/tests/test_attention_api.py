"""Shared attention transport, native evidence, and one-click bill decisions."""
import copy
import unittest
import uuid
import psycopg
from psycopg.rows import dict_row
from fastapi.testclient import TestClient
from minkops_api.main import app
import test_bill_entry as fixtures

URL = fixtures.URL

@unittest.skipUnless(URL, "TEST_DATABASE_URL required")
class AttentionTests(unittest.TestCase):
    for _method in ("setUp", "launch", "upload_bill", "process", "tally_discovery", "tally_result", "approve", "tally_job", "current"):
        locals()[_method] = getattr(fixtures.BillEntryTests, _method)

    def ready(self, findings=None):
        did=self.tally_discovery("company-attention")
        bill=self.upload_bill("attention.pdf")
        run,_=self.launch("bill-entry",file_ids=[bill],config={"output_mode":"tally_in_place","discovery_id":did})
        result=self.tally_result(run,bill)
        result["records"][0]["findings"]=findings or []
        self.process(run,result)
        return run,bill,result

    def decision(self,run,bill,action):
        return self.client.post(f"/api/tenants/mock-tenant/attention/bills/{run['id']}/{bill}",headers=self.csrf,json={"action":action})

    def test_do_nothing_records_identifier_and_never_queues_save(self):
        run,bill,_=self.ready(["Unclear handwriting"])
        response=self.decision(run,bill,"nothing")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["tally_writes"],[])
        items=self.client.get("/api/tenants/mock-tenant/attention").json()
        item=next(i for i in items if i["task_id"]==run["task_id"])
        self.assertEqual(item["identifier"],"attention.pdf")
        self.assertNotIn("target",item)
        self.assertNotIn("events",item)
        with psycopg.connect(URL,row_factory=dict_row) as c:
            event=c.execute("SELECT * FROM attention_events WHERE item_id=%s AND action='deferred'",(item["id"],)).fetchone()
            self.assertIsNotNone(event["actor_id"])

    def test_guess_writes_but_review_remains_until_external_edit(self):
        run,bill,_=self.ready(["Unclear handwriting"])
        with psycopg.connect(URL,row_factory=dict_row) as c:
            from minkops_platform.accounts.attention import flag
            saved_run=c.execute('SELECT * FROM account_runs WHERE id=%s',(run['id'],)).fetchone()
            flag(c,saved_run,saved_run['result']['records'][0])
        response=self.decision(run,bill,"guess")
        self.assertEqual(response.status_code,200,response.text)
        claim,route,plan=self.tally_job(response.json())
        current=self.current(plan)
        receipt=self.client.post(route+"/finish",headers=self.worker,json={"claim_token":claim["claim_token"],"result":{"outcome":"saved","current":current}})
        self.assertEqual(receipt.status_code,200,receipt.text)
        with psycopg.connect(URL,row_factory=dict_row) as c:
            item=c.execute("SELECT * FROM attention_items WHERE task_id=%s AND kind='review'",(run["task_id"],)).fetchone()
            self.assertEqual(item["status"],"pending")
            self.assertEqual(item["target"]["baseline"],current)
            self.assertEqual(c.execute("SELECT status FROM attention_items WHERE task_id=%s AND kind='bill'",(run['task_id'],)).fetchone()['status'],'done')
        base="/api/tenants/mock-tenant/attention"
        for changed,expected in [(False,"pending"),(True,"done")]:
            requested=self.client.post(base+f"/{item['id']}/refresh",headers=self.csrf)
            self.assertEqual(requested.status_code,200,requested.text)
            job=self.client.post("/api/desktop/worker/claim",headers=self.worker,json={}).json()
            observed=copy.deepcopy(current)
            if changed: observed["fingerprint"]="b"*64
            result=self.client.post(f"/api/desktop/worker/jobs/{job['id']}/finish",headers=self.worker,
                json={"claim_token":job["claim_token"],"result":{"company_guid":"company-attention","ledgers":[],"current":observed}})
            self.assertEqual(result.status_code,200,result.text)
            with psycopg.connect(URL) as c:
                self.assertEqual(c.execute("SELECT status FROM attention_items WHERE id=%s",(item["id"],)).fetchone()[0],expected)

    def test_accounting_edits_and_prompt_input_rejected(self):
        run,bill,result=self.ready()
        result["records"][0]["data"]["total"]=999
        response=self.client.post(self.base+f"/runs/{run['id']}/approve",headers=self.csrf,json={"result":result,"acknowledge_findings":True})
        self.assertEqual(response.status_code,422,response.text)

    def test_refresh_is_deduplicated_and_rejects_wrong_native_identity(self):
        run,bill,_=self.ready()
        self.decision(run,bill,'nothing')
        with psycopg.connect(URL,row_factory=dict_row) as c:
            item=c.execute('SELECT * FROM attention_items WHERE task_id=%s',(run['task_id'],)).fetchone()
        route=f"/api/tenants/mock-tenant/attention/{item['id']}/refresh"
        self.assertEqual(self.client.post(route,headers=self.csrf).json()['queued'],1)
        self.assertEqual(self.client.post(route,headers=self.csrf).json()['queued'],0)
        job=self.client.post('/api/desktop/worker/claim',headers=self.worker,json={}).json()
        response=self.client.post(f"/api/desktop/worker/jobs/{job['id']}/finish",headers=self.worker,
            json={'claim_token':job['claim_token'],'result':{'company_guid':'wrong','ledgers':[],'current':None}})
        self.assertEqual(response.status_code,422,response.text)
        with psycopg.connect(URL) as c:
            self.assertEqual(c.execute('SELECT status FROM attention_items WHERE id=%s',(item['id'],)).fetchone()[0],'pending')

    def test_excel_refresh_uses_business_keys_and_requires_a_valid_external_edit(self):
        import base64
        from io import BytesIO
        from openpyxl import load_workbook
        from test_accounts_excel import workbook, catalog
        from minkops_platform.accounts.attention import check_observation
        from minkops_platform.attention import resolved
        item={'kind':'review','target':{'tool':'excel','mapping':catalog()['sheets'][0],
            'keys':{'Invoice':'A-1','Vendor':'Acme'},'baseline':None}}
        observe=lambda content:check_observation(item,{'content':base64.b64encode(content).decode()})
        baseline=observe(workbook())
        self.assertTrue(baseline['valid'])
        item['target']['baseline']=baseline['current']
        self.assertFalse(resolved(item,observe(workbook())))
        book=load_workbook(BytesIO(workbook()));book['Bills']['C3']=42
        content=BytesIO();book.save(content)
        self.assertTrue(resolved(item,observe(content.getvalue())))
        book['Bills']['A3']='different-bill';content=BytesIO();book.save(content)
        self.assertFalse(resolved(item,observe(content.getvalue())))
        self.assertFalse(observe(b'broken workbook')['valid'])

    def test_native_save_failure_retains_attention_without_replaying_a_write(self):
        run,bill,_=self.ready()
        approved=self.decision(run,bill,'guess').json()
        claim,route,_=self.tally_job(approved)
        response=self.client.post(route+'/finish',headers=self.worker,
            json={'claim_token':claim['claim_token'],'error':'Import acknowledgement lost'})
        self.assertEqual(response.status_code,200,response.text)
        item=next(i for i in self.client.get('/api/tenants/mock-tenant/attention').json() if i['task_id']==run['task_id'])
        self.assertEqual(item['identifier'],'attention.pdf')
        self.assertEqual(item['status'],'pending')
        self.assertIn(item['label'],['Save interrupted','Review in Tally'])
        self.assertIsNone(self.client.post('/api/desktop/worker/claim',headers=self.worker,json={}).json())

    def test_member_can_override_run_config_but_not_saved_workflow_or_employee_config(self):
        import json
        from minkops_api.auth import digest
        from test_accounts_excel import workbook
        with psycopg.connect(URL,row_factory=dict_row) as c:
            tenant=c.execute("SELECT id FROM tenants WHERE slug='mock-tenant'").fetchone()['id']
            member=c.execute("INSERT INTO users(name,email,password_hash,email_verified_at) VALUES ('Member',%s,'unused',now()) RETURNING id",
                (f'{uuid.uuid4()}@test.invalid',)).fetchone()['id']
            c.execute("INSERT INTO memberships VALUES (%s,%s,'member',now())",(tenant,member))
            token=str(uuid.uuid4())
            c.execute("INSERT INTO sessions(user_id,token_hash,expires_at) VALUES (%s,%s,now()+interval '1 hour')",(member,digest(token)))
            workflow=c.execute("SELECT * FROM workflows WHERE tenant_id=%s AND key='source-discovery'",(tenant,)).fetchone()
            employee=c.execute('SELECT * FROM employees WHERE tenant_id=%s LIMIT 1',(tenant,)).fetchone()
        client=TestClient(app);client.cookies.set('minkops_session',token)
        csrf={'x-csrf-token':client.get('/api/auth/me').json()['csrf_token']}
        uploaded=client.post(self.base+'/sources',headers=csrf,data={'label':'Member files','writable':'true','paths':json.dumps(['own.xlsx'])},
            files=[('files',('own.xlsx',workbook()))])
        self.assertEqual(uploaded.status_code,200,uploaded.text)
        response=client.post(self.base+'/runs',headers=csrf,json={'key':'source-discovery','request_key':str(uuid.uuid4()),
            'file_ids':[uploaded.json()['files'][0]['id']],'config':{'max_files':8}})
        self.assertEqual(response.status_code,202,response.text)
        self.assertEqual(response.json()['config']['max_files'],8)
        for kind,row in [('workflows',workflow),('employees',employee)]:
            rejected=client.patch(f"/api/tenants/mock-tenant/{kind}/{row['id']}",headers=csrf,json={'config_values':row['config_values']})
            self.assertEqual(rejected.status_code,403,rejected.text)
        with psycopg.connect(URL) as c:
            self.assertEqual(c.execute('SELECT config_values FROM workflows WHERE id=%s',(workflow['id'],)).fetchone()[0],workflow['config_values'])

    def test_other_member_can_mark_done_with_audit_but_other_tenant_cannot(self):
        run,bill,_=self.ready()
        self.decision(run,bill,"nothing")
        with psycopg.connect(URL,row_factory=dict_row) as c:
            item=c.execute("SELECT * FROM attention_items WHERE task_id=%s",(run["task_id"],)).fetchone()
            member=c.execute("INSERT INTO users(name,email,password_hash,email_verified_at) VALUES ('Member',%s,'unused',now()) RETURNING id",(f"{uuid.uuid4()}@test.invalid",)).fetchone()["id"]
            c.execute("INSERT INTO memberships VALUES (%s,%s,'member',now())",(item["tenant_id"],member))
            from minkops_api.auth import digest
            token=str(uuid.uuid4())
            c.execute("INSERT INTO sessions(user_id,token_hash,expires_at) VALUES (%s,%s,now()+interval '1 hour')",(member,digest(token)))
        client=TestClient(app);client.cookies.set("minkops_session",token)
        csrf={"x-csrf-token":client.get("/api/auth/me").json()["csrf_token"]}
        self.assertEqual(client.post(f"/api/tenants/mock-tenant/attention/{item['id']}/done",headers=csrf).status_code,200)
        self.assertEqual(self.client.post(f"/api/tenants/pr-infra/attention/{item['id']}/done",headers=self.csrf).status_code,404)
        with psycopg.connect(URL) as c:
            self.assertEqual(c.execute("SELECT done_by FROM attention_items WHERE id=%s",(item["id"],)).fetchone()[0],member)

    def test_supplier_creation_authorizes_fixed_native_plan_then_continues(self):
        run,bill,result=self.ready()
        with psycopg.connect(URL,row_factory=dict_row) as c:
            result["records"][0]["data"].update(vendor="New supplier",tax=0,tax_ledger=None,total=100)
            result["records"][0]["evidence"].append({"field":"vendor","page":1,"quote":"New supplier"})
            from minkops_platform.accounts.bills import capture_tally_findings
            config=c.execute("SELECT config FROM account_runs WHERE id=%s",(run["id"],)).fetchone()["config"]
            capture_tally_findings(result,config["tally_target"])
            from psycopg.types.json import Jsonb
            c.execute("UPDATE account_runs SET result=%s WHERE id=%s",(Jsonb(result),run["id"]))
        response=self.decision(run,bill,"supplier")
        self.assertEqual(response.status_code,200,response.text)
        job=self.client.post("/api/desktop/worker/claim",headers=self.worker,json={}).json()
        self.assertEqual(job["operation"],"attention.supplier")
        master={"NAME":"New supplier","GUID":"supplier-guid","PARENT":"Sundry Creditors","ALTERID":"1"}
        response=self.client.post(f"/api/desktop/worker/jobs/{job['id']}/finish",headers=self.worker,
            json={"claim_token":job["claim_token"],"result":{"company_guid":"company-attention","ledgers":[master],"current":None}})
        self.assertEqual(response.status_code,200,response.text)
        updated=self.client.get(self.base+f"/runs/{run['id']}").json()
        self.assertEqual(updated["state"],"writing")
        _,_,plan=self.tally_job(updated)
        self.assertEqual(plan["data"]["vendor"],"New supplier")
