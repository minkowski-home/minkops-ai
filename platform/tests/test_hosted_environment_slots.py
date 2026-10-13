"""PostgreSQL ownership and recovery gates for reusable batch compute."""

import os
from contextlib import ExitStack
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from unittest.mock import MagicMock
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


@skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is required")
class EnvironmentSlotTests(TestCase):
    def setUp(self):
        self.url = os.environ["TEST_DATABASE_URL"]
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            self.tenant = c.execute("SELECT id FROM tenants WHERE slug='mock-tenant'").fetchone()["id"]
            self.actor = c.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
            c.execute("""INSERT INTO workflows(tenant_id,key,name,description,config_schema,config_values)
                VALUES(%s,'test','Test','Test','{}','{}') ON CONFLICT DO NOTHING""", (self.tenant,))
            self.task = c.execute("INSERT INTO tasks(tenant_id,title) VALUES(%s,'Warm environment test') RETURNING id", (self.tenant,)).fetchone()["id"]
            self.parent = self.insert(c)

    def insert(self, c, parent=None, actor=None):
        return c.execute("""INSERT INTO workflow_runs(tenant_id,task_id,actor_id,workflow_key,
            definition_version,request_key,request_hash,config,file_ids,parent_run_id)
            VALUES(%s,%s,%s,'test','1',%s,'test','{}','[]',%s) RETURNING *""",
            (self.tenant, self.task, actor or self.actor, uuid4(), parent)).fetchone()

    def child(self):
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            return self.insert(c, self.parent["id"])

    def test_four_exclusive_slots_and_reuse_only_after_session_cleanup(self):
        from minkops_platform.runtime.environments import acquire

        runs = [self.child() for _ in range(5)]
        with ExitStack() as stack:
            claims = []
            for run in runs:
                c = stack.enter_context(psycopg.connect(self.url, row_factory=dict_row))
                claims.append(stack.enter_context(acquire(c, run)))
            self.assertTrue(all(claims[:4]))
            self.assertIsNone(claims[4])  # Isolated fallback; no fifth shared slot.
            self.assertEqual(len({claim.slot for claim in claims[:4]}), 4)
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            c.execute("UPDATE workflow_runs SET state='review',config=config || '{\"hosted_session_closed\":true}' WHERE id=%s", (runs[0]["id"],))
            c.commit()
            with acquire(c, runs[4]) as lease:
                self.assertEqual(lease.slot, claims[0].slot)
                self.assertNotEqual(lease.workspace["root"], claims[0].workspace["root"])

    def test_foreign_operator_cannot_reuse_parent_workspace(self):
        from minkops_platform.runtime.environments import acquire

        with psycopg.connect(self.url, row_factory=dict_row) as c:
            other = c.execute("INSERT INTO users(email,name,password_hash) VALUES(%s,'Other','test') RETURNING id",
                              (str(uuid4()) + "@example.test",)).fetchone()["id"]
            run = self.insert(c, self.parent["id"], actor=other)
            c.commit()
            with self.assertRaisesRegex(ValueError, "scope"):
                with acquire(c, run):
                    pass

    def complete(self, c, run, *, state="review"):
        c.execute("UPDATE workflow_runs SET state=%s,config=config || '{\"hosted_session_closed\":true}' WHERE id=%s",
                  (state, run["id"]))
        c.commit()

    def test_new_worker_reuses_compute_and_persists_paths_before_attach(self):
        from minkops_platform.runtime.environments import acquire

        first, second = self.child(), self.child()
        provider = MagicMock()
        provider.post.return_value = {"id": "environment"}
        provider.beta.agents.environments.retrieve.return_value.status = "ready"
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            with acquire(c, first) as lease:
                self.assertEqual(lease.prepare(provider, {"type": "openai_hosted"}), "environment")
                saved = c.execute("SELECT config FROM workflow_runs WHERE id=%s", (first["id"],)).fetchone()["config"]
                self.assertEqual(saved["hosted_workspace"]["environment_id"], "environment")
            self.complete(c, first)
        # A process-local cache would lose reuse on this new connection.
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            with acquire(c, second) as lease:
                self.assertEqual(lease.prepare(provider, {}), "environment")
        provider.post.assert_called_once()

    def test_limits_failed_runs_and_changed_grants_rotate_compute(self):
        from minkops_platform.runtime.environments import acquire

        for reason in ("limit", "failed", "grants"):
            first, second = self.child(), self.child()
            with psycopg.connect(self.url, row_factory=dict_row) as c:
                with acquire(c, first) as lease:
                    c.execute("UPDATE hosted_environment_slots SET environment_id='old',attachments=%s WHERE group_run_id=%s AND slot=%s",
                              (128 if reason == "limit" else 1, self.parent["id"], lease.slot))
                    c.commit()
                self.complete(c, first, state="failed" if reason == "failed" else "review")
                if reason == "grants":
                    second["config"]["authorized_bindings"] = [{"resource_id": "different"}]
                with acquire(c, second) as lease:
                    self.assertIsNone(lease.row["environment_id"])
                    self.assertEqual(lease.row["attachments"], 0)
                self.complete(c, second)

    def test_expired_compute_replaced_before_submitting_input(self):
        from minkops_platform.runtime.environments import acquire

        first, second = self.child(), self.child()
        provider = MagicMock()
        provider.post.return_value = {"id": "replacement"}
        provider.beta.agents.environments.retrieve.side_effect = [SimpleNamespace(status="disconnected"),
                                                                 SimpleNamespace(status="ready")]
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            with acquire(c, first) as lease:
                c.execute("UPDATE hosted_environment_slots SET environment_id='expired' WHERE group_run_id=%s AND slot=%s",
                          (self.parent["id"], lease.slot))
                c.commit()
            self.complete(c, first)
            with acquire(c, second) as lease:
                self.assertEqual(lease.prepare(provider, {}), "replacement")
        provider.beta.agents.sessions.create.assert_not_called()

    def test_recovery_and_standalone_runs_never_claim_pool_slots(self):
        from minkops_platform.runtime.environments import acquire

        with psycopg.connect(self.url, row_factory=dict_row) as c:
            with acquire(c, self.parent) as lease:
                self.assertIsNone(lease)
            child = self.child()
            child["session_id"] = "saved"
            with acquire(c, child) as lease:
                self.assertIsNone(lease)

    def test_inherited_cleanup_receipt_cannot_release_a_new_child(self):
        from minkops_platform.runtime.environments import acquire

        run = self.child()
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            c.execute("UPDATE workflow_runs SET config='{\"hosted_session_closed\":true}' WHERE id=%s", (run["id"],))
            c.commit()
            with acquire(c, run):
                saved = c.execute("SELECT config FROM workflow_runs WHERE id=%s", (run["id"],)).fetchone()["config"]
                self.assertFalse(saved["hosted_session_closed"])

    def test_retry_children_do_not_inherit_parent_provider_receipts(self):
        from minkops_platform.accounts.batch import create_child

        self.parent["config"].update({"hosted_workspace": {"root": "old"},
            "hosted_session_closed": True, "cleanup_attempt_count": 9, "cleanup_attempt_at": "old"})
        with psycopg.connect(self.url, row_factory=dict_row) as c:
            child = create_child(c, self.parent, str(uuid4()))
            for key in ("hosted_workspace", "hosted_session_closed", "cleanup_attempt_count", "cleanup_attempt_at"):
                self.assertNotIn(key, child["config"])
                self.assertIn(key, self.parent["config"])
