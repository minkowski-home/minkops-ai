"""Control-plane work stays bounded by metadata, not pinned discovery size."""

import os
import unittest
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is required")
class RuntimeStorageTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row)
        self.addCleanup(self.connection.close)
        self.addCleanup(self.connection.rollback)
        c = self.connection
        self.tenant = c.execute("INSERT INTO tenants(slug,name) VALUES(%s,'Storage') RETURNING id", (uuid4().hex,)).fetchone()["id"]
        self.actor = c.execute("INSERT INTO users(email,name,password_hash) VALUES(%s,'Storage','unused') RETURNING id",
                               (uuid4().hex + "@example.com",)).fetchone()["id"]
        self.task = c.execute("INSERT INTO tasks(tenant_id,title) VALUES(%s,'Storage') RETURNING id", (self.tenant,)).fetchone()["id"]
        c.execute("INSERT INTO workflows(tenant_id,key,name) VALUES(%s,'source-discovery','Storage')", (self.tenant,))

    def insert(self, config):
        return self.connection.execute("""INSERT INTO workflow_runs(tenant_id,task_id,actor_id,workflow_key,
            definition_version,request_key,request_hash,config,file_ids)
            VALUES(%s,%s,%s,'source-discovery','1',%s,'test',%s,'[]') RETURNING *""",
            (self.tenant, self.task, self.actor, uuid4(), Jsonb(config))).fetchone()

    def test_snapshot_is_pinned_once_and_runtime_updates_do_not_rewrite_it(self):
        from minkops_platform.runtime.assets import hydrate

        catalog = {"sources": [{"evidence": "0123456789abcdef" * 10000}]}
        first = self.insert({"source_catalog_snapshot": catalog, "runtime_binding": {"handler": "accounts.discovery"}})
        second = self.insert({"source_catalog_snapshot": catalog})
        self.assertNotIn("source_catalog_snapshot", first["config"])
        self.assertLess(len(str(first["config"])), 1000)
        self.assertEqual(first["config"]["_assets"], second["config"]["_assets"])
        self.assertEqual(hydrate(self.connection, first)["config"]["source_catalog_snapshot"], catalog)
        self.connection.execute("UPDATE workflow_runs SET config=config || '{\"hosted_session_closed\":true}' WHERE id=%s", (first["id"],))
        self.assertEqual(self.connection.execute("SELECT count(*) AS n FROM workflow_run_assets WHERE tenant_id=%s", (self.tenant,)).fetchone()["n"], 1)

    def test_config_adapter_reuses_assets_before_sending_native_evidence_to_postgres(self):
        from minkops_platform.runtime.assets import config_json, hydrate

        value = {'source_catalog_snapshot': {'evidence': 'native' * 50000}, 'stage': 'triage'}
        first = config_json(self.connection, self.tenant, value).obj
        run = self.insert(first)
        hydrate(self.connection, run)
        calls = []
        connection = self.connection
        class Observed:
            def execute(self, query, params):
                calls.append(query)
                return connection.execute(query, params)
        again = config_json(Observed(), self.tenant, run['config']).obj
        self.assertEqual(again['_assets'], first['_assets'])
        self.assertNotIn('source_catalog_snapshot', again)
        self.assertFalse(any('INSERT' in query for query in calls))
        run['config']['source_catalog_snapshot']['evidence'] = 'Changed'
        changed = config_json(self.connection, self.tenant, run['config']).obj
        self.assertNotEqual(changed['_assets'], first['_assets'])
        self.assertEqual(hydrate(self.connection, self.insert(changed))['config']['source_catalog_snapshot'],
                         {'evidence': 'Changed'})

    def test_releasing_a_dependency_wakes_a_drained_worker_transactionally(self):
        profile = str(uuid4())
        run = self.insert({"awaits": {"profile": profile}})
        self.connection.execute("UPDATE worker_wakeup SET acknowledged=generation,lease_until=NULL")
        before = self.connection.execute("SELECT generation FROM worker_wakeup").fetchone()["generation"]
        self.connection.execute("UPDATE workflow_runs SET config=config-'awaits' WHERE id=%s", (run["id"],))
        row = self.connection.execute("SELECT generation,acknowledged FROM worker_wakeup").fetchone()
        self.assertEqual((row["generation"], row["acknowledged"]), (before + 1, before))

    def test_asset_scope_and_immutability_are_enforced_by_storage(self):
        run = self.insert({"source_catalog_snapshot": {"evidence": "Pinned"}})
        asset = run["config"]["_assets"]["source_catalog_snapshot"]
        with self.assertRaises(psycopg.errors.RaiseException), self.connection.transaction():
            self.connection.execute("UPDATE workflow_run_assets SET content='{}' WHERE id=%s", (asset,))
        with self.assertRaises(psycopg.errors.ForeignKeyViolation), self.connection.transaction():
            self.connection.execute("DELETE FROM workflow_run_assets WHERE id=%s", (asset,))
        foreign = self.connection.execute("INSERT INTO tenants(slug,name) VALUES(%s,'Foreign') RETURNING id", (uuid4().hex,)).fetchone()["id"]
        other = self.connection.execute("""INSERT INTO workflow_run_assets(tenant_id,field,sha256,content)
            VALUES(%s,'source_catalog_snapshot','unused','{}') RETURNING id""", (foreign,)).fetchone()["id"]
        with self.assertRaises(psycopg.errors.RaiseException), self.connection.transaction():
            self.insert({"_assets": {"source_catalog_snapshot": str(other)}})

    def test_candidates_are_only_small_identities_and_unknown_dependencies_stay_blocked(self):
        from minkops_platform.runtime.store import WorkflowRunStore

        ready = self.insert({"source_catalog_snapshot": {"large": "x" * 1_000_000}})
        blocked = self.insert({"awaits": {"future_dependency": "requires-consent"}})
        # Other suites intentionally leave queued historical fixtures. Put both
        # of this test's candidates before that history without changing scope.
        self.connection.execute("UPDATE workflow_runs SET updated_at='1900-01-01' WHERE id=ANY(%s::uuid[])",
                                ([ready["id"], blocked["id"]],))
        candidates = WorkflowRunStore().candidates(self.connection)
        self.assertIn(ready["id"], {row["id"] for row in candidates})
        self.assertNotIn(blocked["id"], {row["id"] for row in candidates})
        self.assertTrue(all(set(row) == {"id", "tenant_id", "task_id"} for row in candidates))

    def test_metadata_update_does_not_touch_processing_clock(self):
        run = self.insert({})
        self.connection.execute("UPDATE workflow_runs SET state='executing' WHERE id=%s", (run["id"],))
        self.connection.execute("CREATE TEMP TABLE clock_calls(called boolean)")
        self.connection.execute("""CREATE OR REPLACE FUNCTION refresh_task_processing_clock(scope uuid,task_key uuid)
            RETURNS void LANGUAGE plpgsql AS $$ BEGIN INSERT INTO clock_calls VALUES(true); END $$""")
        self.connection.execute("UPDATE workflow_runs SET config=config || '{\"cleanup_attempt_count\":1}' WHERE id=%s", (run["id"],))
        self.assertEqual(self.connection.execute("SELECT count(*) AS n FROM clock_calls").fetchone()["n"], 0)
        self.connection.execute("UPDATE workflow_runs SET state='review' WHERE id=%s", (run["id"],))
        self.assertEqual(self.connection.execute("SELECT count(*) AS n FROM clock_calls").fetchone()["n"], 1)
