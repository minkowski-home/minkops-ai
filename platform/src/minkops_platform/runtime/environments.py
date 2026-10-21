"""Four durable compute slots per batch; conversations remain per-run.

The advisory lock covers provisioning, uploads and the complete proposal. A
slot's busy run survives worker crashes, and must have confirmed session cleanup
before reuse. Uncertain sessions are never replaced or replayed by this module.
"""

import time
from contextlib import contextmanager

from openai import NotFoundError
from psycopg.types.json import Jsonb

from .diagnostics import record, stage

SLOTS = 4
ATTACHMENT_LIMIT = 128
# What one hosted session accepts: the inputs plus complete discovery context.
# Launch checks refuse a larger scope instead of sampling masters or history.
SESSION_FILE_LIMIT = 45
SESSION_BYTE_LIMIT = 8_000_000


def exceeds_session(files, extra_bytes=0):
    """Whether these inputs, plus any inline payload, overflow one hosted session."""
    return (len(files) > SESSION_FILE_LIMIT
            or sum(len(f["content"]) for f in files) + extra_bytes > SESSION_BYTE_LIMIT)


class Lease:
    def __init__(self, connection, run, row):
        self.connection, self.run, self.row = connection, run, row
        self.slot = row["slot"]
        output = run["config"].get("execution_snapshot", {}).get("execution", {}).get(
            "result_path", "/workspace/outputs/result.json")
        self.workspace = {
            "root": f"/workspace/runs/{run['id']}",
            "result_path": f"/workspace/outputs/{run['id']}/" + output.removeprefix("/workspace/outputs/"),
        }

    def check_start(self):
        from minkops_platform.errors import ServiceError
        from minkops_platform.run_controls import control_state

        # Serialize submission with Stop until the first event saves recovery IDs.
        # Pause allows the already underway operation to finish, as before.
        self.connection.execute("SELECT id FROM workflow_runs WHERE tenant_id=%s AND id=%s FOR NO KEY UPDATE",
                                (self.run["tenant_id"], self.run["id"]))
        if control_state(self.connection, self.run["tenant_id"], self.run["task_id"]) == "stopped":
            raise ServiceError("conflict", "This task is stopped. Start a new run to continue.")

    def prepare(self, client, environment):
        """Only provision compute; no model input is sent until IDs are durable."""
        env_id = self.row["environment_id"]
        with stage(self.connection, self.run, "environment", "Prepare batch hosted environment",
                   details={"slot": self.slot, "existing_environment": bool(env_id)}):
            if env_id:
                try:
                    if client.beta.agents.environments.retrieve(env_id).status != "ready":
                        env_id = None
                except NotFoundError:
                    env_id = None
            reused = bool(env_id)
            if not env_id:
                # SDK 3.19 exposes file/retrieve helpers but not standalone create.
                created = client.post("/agents/environments", body={"environment": environment},
                                      cast_to=dict, options={"headers": {"OpenAI-Beta": "agents=v1"}})
                env_id = created["id"]
                self.connection.execute("""UPDATE hosted_environment_slots SET environment_id=%s,
                    attachments=0 WHERE tenant_id=%s AND group_run_id=%s AND slot=%s""",
                    (env_id, self.run["tenant_id"], self.run["parent_run_id"], self.slot))
                self.connection.commit()
                deadline = time.monotonic() + 180
                while (status := client.beta.agents.environments.retrieve(env_id).status) != "ready":
                    if status != "pending":
                        raise ValueError("Hosted environment could not start. Retry explicitly.")
                    if time.monotonic() >= deadline:
                        raise ValueError("Hosted environment did not become ready. Retry explicitly.")
                    time.sleep(2)
            self.workspace["environment_id"] = env_id
            self.connection.execute("""UPDATE workflow_runs SET config=config || %s
                WHERE tenant_id=%s AND id=%s""", (Jsonb({"hosted_workspace": self.workspace}),
                self.run["tenant_id"], self.run["id"]))
            # Count before attaching: an ambiguous creation cannot silently consume
            # an unrecorded attachment or be retried on another environment.
            self.connection.execute("""UPDATE hosted_environment_slots SET attachments=attachments+1
                WHERE tenant_id=%s AND group_run_id=%s AND slot=%s""",
                (self.run["tenant_id"], self.run["parent_run_id"], self.slot))
            self.connection.commit()
            self.run["config"]["hosted_workspace"] = dict(self.workspace)
            record(self.connection, self.run, "environment.bound", "Bound run to hosted workspace",
                   details={"environment_id": env_id, "slot": self.slot, "reused": reused})
            return env_id


@contextmanager
def acquire(connection, run):
    """Standalone/recovering runs use their existing adapter path unchanged."""
    parent_id = run.get("parent_run_id")
    if not parent_id or run.get("session_id"):
        yield None
        return
    parent = connection.execute("SELECT actor_id,task_id,workflow_key,definition_version FROM workflow_runs WHERE tenant_id=%s AND id=%s",
                                (run["tenant_id"], parent_id)).fetchone()
    if not parent or any(parent[key] != run[key] for key in (
        "actor_id", "task_id", "workflow_key", "definition_version")):
        raise ValueError("Hosted environment scope differs from the parent workflow.")
    from .assets import profile_identity
    profile = profile_identity(run["config"])
    connection.commit()
    for slot in range(SLOTS):
        lock = f"hosted:{run['tenant_id']}:{parent_id}:{slot}"
        held = connection.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS held",
                                  (lock,)).fetchone()["held"]
        connection.commit()
        if not held:
            continue
        try:
            row = connection.execute("""SELECT s.*, r.state, r.session_closed AS closed
                FROM hosted_environment_slots s JOIN workflow_runs r
                ON (r.tenant_id,r.id)=(s.tenant_id,s.busy_run_id)
                WHERE s.tenant_id=%s AND s.group_run_id=%s AND s.slot=%s""",
                (run["tenant_id"], parent_id, slot)).fetchone()
            if row and not row["closed"]:
                continue
            # Errors and changed resource grants retire the previous workspace.
            reusable = row and row["state"] != "failed" and row["profile_hash"] == profile and row["attachments"] < ATTACHMENT_LIMIT
            row = connection.execute("""INSERT INTO hosted_environment_slots
                (tenant_id,group_run_id,slot,profile_hash,environment_id,attachments,busy_run_id)
                VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,group_run_id,slot)
                DO UPDATE SET profile_hash=excluded.profile_hash,environment_id=excluded.environment_id,
                    attachments=excluded.attachments,busy_run_id=excluded.busy_run_id RETURNING *""",
                (run["tenant_id"], parent_id, slot, profile, row["environment_id"] if reusable else None,
                 row["attachments"] if reusable else 0, run["id"])).fetchone()
            connection.execute("""UPDATE workflow_runs SET config=(config - 'hosted_workspace') ||
                '{"hosted_session_closed":false}'::jsonb WHERE tenant_id=%s AND id=%s""",
                (run["tenant_id"], run["id"]))
            run["config"].pop("hosted_workspace", None)
            run["config"]["hosted_session_closed"] = False
            connection.commit()
            yield Lease(connection, run, row)
            return
        finally:
            connection.rollback()
            connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (lock,))
            connection.commit()
    # Pending cleanup never blocks unrelated bills or permits shared concurrent use.
    yield None
