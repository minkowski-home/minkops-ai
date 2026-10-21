"""Native writes of runs: durable intents, one Tally change at a time per PC.

Approving a record stores its immutable plan as a pending write before
anything is sent. A pending write reserves its destination identity, so no
other run can write the same bank transaction or bill until it is verified or
released. Each PC gets one job at a time, in approval order: `tally.write`
saves a voucher, and `tally.supplier` creates the supplier ledger a person
approved for a bill. The companion fences every import locally and reads back
what it wrote; the run's handler checks that readback against the plan. A
write that was interrupted is never re-sent automatically.
"""

from uuid import uuid4

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from minkops_platform import work
from minkops_platform.errors import ServiceError

from .vouchers import FORMAT

OPERATIONS = ("tally.write", "tally.supplier")


def operation(plan):
    return "tally.supplier" if plan.get("kind") == "supplier" else "tally.write"


def request(connection, run, record, plan, company, *, actor):
    """Store an approved plan as a pending write and dispatch it; False when another write holds its identity."""
    try:
        with connection.transaction():
            connection.execute(
                """INSERT INTO native_writes(tenant_id,run_id,record_id,device_id,company_id,destination_key,identity,plan)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (run["tenant_id"], run["id"], record["id"], company["device_id"], company["id"],
                 plan["destination_key"], plan["identity"]["hash"], Jsonb(plan)))
    except UniqueViolation:
        return False
    dispatch(connection, run["tenant_id"], company["device_id"], actor=actor)
    return True


def dispatch(connection, tenant_id, device_id, *, actor=None):
    """Queue the PC's next pending write unless one is already queued or running there."""
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"writes:{device_id}",))
    if connection.execute("""SELECT 1 FROM desktop_jobs WHERE device_id=%s AND operation = ANY(%s)
                             AND state IN ('queued','executing') LIMIT 1""", (device_id, list(OPERATIONS))).fetchone():
        return None
    write = connection.execute(
        """SELECT w.*, r.task_id, r.actor_id FROM native_writes w JOIN runs r ON r.id=w.run_id
           JOIN tasks t ON t.tenant_id=r.tenant_id AND t.id=r.task_id
           WHERE w.device_id=%s AND w.finished_at IS NULL AND t.control_state='active'
               AND NOT EXISTS (SELECT 1 FROM desktop_jobs j WHERE j.operation = ANY(%s)
                               AND j.input->>'write_id'=w.id::text)
           ORDER BY w.created_at, w.id LIMIT 1""", (device_id, list(OPERATIONS))).fetchone()
    if write is None:
        return None
    payload = {"write_id": str(write["id"])}
    return connection.execute(
        """INSERT INTO desktop_jobs(tenant_id,device_id,actor_id,task_id,operation,input,request_key,request_hash)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (tenant_id, device_id, actor or write["actor_id"], write["task_id"], operation(write["plan"]), Jsonb(payload),
         uuid4(), write["id"].hex)).fetchone()


def _write(connection, device, job, *, lock=False):
    write = connection.execute(
        f"SELECT * FROM native_writes WHERE tenant_id=%s AND id=%s AND device_id=%s{' FOR UPDATE' if lock else ''}",
        (device["tenant_id"], job["input"]["write_id"], device["id"])).fetchone()
    if write is None:
        raise ServiceError("not_found", "Approved Tally write not found for this PC.")
    return write


def plan(connection, device, job, plan_version):
    """The approved voucher, exactly as stored, addressed to the port this PC's Tally serves on now."""
    write = _write(connection, device, job)
    if write["finished_at"]:
        raise ServiceError("conflict", "This Tally write is no longer pending.")
    voucher = write["plan"].get("kind") != "supplier"
    if voucher and (plan_version < FORMAT or write["plan"].get("format_version") != FORMAT):
        raise ServiceError("conflict", "Update Minkops on this PC to the latest version, then retry the save.")
    return {**write["plan"], "port": device["tally_port"]}


def accept(connection, device, job, receipt):
    """Record the companion's receipt through the run's handler, then dispatch the PC's next write."""
    write = _write(connection, device, job, lock=True)
    if write["finished_at"]:
        raise ServiceError("conflict", "This Tally write already has a receipt.")
    if not isinstance(receipt, dict):
        raise ServiceError("invalid", "Invalid Tally write receipt.")
    run = work.get_run(connection, write["tenant_id"], write["run_id"])
    record = work.get_record(connection, write["tenant_id"], write["record_id"], lock=True)
    # The handler verifies the receipt against the plan, and says what came of it.
    result = work.handler_for(run).written(connection, run, record, write, receipt)
    connection.execute("UPDATE native_writes SET outcome=%s,receipt=%s,finished_at=now() WHERE id=%s",
                       (result["outcome"], Jsonb(receipt), write["id"]))
    work.refresh(connection, run["tenant_id"], run["id"], describe=getattr(work.handler_for(run), "describe", None))
    return result


def interrupted(connection, device, job, error):
    """A write that ended without a receipt holds, and is never re-sent automatically.

    Retry save sends the same plan again; the companion's local fence for its
    remote ID then finds the voucher in Tally or holds it as uncertain.
    """
    write = _write(connection, device, job, lock=True)
    if write["finished_at"]:
        return None
    return accept(connection, device, job, {"outcome": "attention", "hold": "save_interrupted",
                                            "message": str(error or "The save was interrupted.")[:300]})


def recover(connection, device):
    """A polling PC is not still running its earlier write: one whose lease lapsed was interrupted."""
    for job in connection.execute(
            """SELECT * FROM desktop_jobs WHERE device_id=%s AND operation = ANY(%s) AND state='executing'
               AND lease_until < now() FOR UPDATE SKIP LOCKED""", (device["id"], list(OPERATIONS))).fetchall():
        interrupted(connection, device, job, "The PC stopped before confirming this save.")
        connection.execute("""UPDATE desktop_jobs SET state='failed', error='Save interrupted.', lease_until=NULL,
                              updated_at=now() WHERE id=%s""", (job["id"],))


def resume(connection, tenant_id, task_id):
    """A resumed task's PCs pick up their pending writes again."""
    for row in connection.execute(
            """SELECT DISTINCT w.device_id FROM native_writes w JOIN runs r ON r.id=w.run_id
               WHERE r.tenant_id=%s AND r.task_id=%s AND w.finished_at IS NULL""", (tenant_id, task_id)).fetchall():
        dispatch(connection, tenant_id, row["device_id"])


def cancel(connection, run):
    """Withdraw a stopped run's writes that no PC has started; an underway one still reports its receipt.

    Returns the records whose writes were withdrawn.
    """
    withdrawn = connection.execute(
        """UPDATE native_writes w SET outcome='cancelled', finished_at=now() WHERE w.run_id=%s AND w.finished_at IS NULL
           AND NOT EXISTS (SELECT 1 FROM desktop_jobs j WHERE j.operation = ANY(%s) AND j.state='executing'
                           AND j.input->>'write_id'=w.id::text) RETURNING w.record_id""",
        (run["id"], list(OPERATIONS))).fetchall()
    connection.execute(
        """UPDATE desktop_jobs SET state='failed', error='The run was stopped.', updated_at=now()
           WHERE operation = ANY(%s) AND state='queued' AND input->>'write_id' IN
               (SELECT id::text FROM native_writes WHERE run_id=%s AND outcome='cancelled')""",
        (list(OPERATIONS), run["id"]))
    return [row["record_id"] for row in withdrawn]
