"""Workflow-agnostic attention and auditable decisions. Destinations own manual edits.

Only server-owned targets become desktop plans. A refresh never writes and an
unchanged destination never establishes human review. Domain adapters attach
exact identifiers and resolution evidence, not free-form automation commands.
"""
from uuid import uuid4
from psycopg.types.json import Jsonb
from .errors import ServiceError


def label(reason):
    value = str(reason).lower()
    for words, title in [
        (("locked company",), "Company mismatch"),
        (("company", "buyer"), "Unknown company"),
        (("changed", "stale"), "Source changed"),
        (("supplier", "vendor", "ledger"), "Missing supplier"),
        (("handwrit", "unclear", "confidence"), "Needs review"),
        (("inventory", "allocation"), "Manual entry needed"),
    ]:
        if any(word in value for word in words):
            return title
    return "Needs attention"


def resolved(item, observation):
    if observation.get("valid") is not True:
        return False
    target, current = item["target"], observation.get("current") or {}
    if item["kind"] == "supplier":
        return target.get("vendor") in observation.get("ledgers", [])
    if item["kind"] == "bill" and not target.get("baseline"):
        return bool(current)
    baseline = target.get("baseline") or {}
    return item["kind"] in ("bill", "review") and bool(baseline.get("fingerprint")) and (
        current.get("guid") == baseline.get("guid")
        and bool(current.get("fingerprint"))
        and current["fingerprint"] != baseline["fingerprint"]
    )


def audit(connection, item, actor, action, summary):
    connection.execute(
        "INSERT INTO attention_events(tenant_id,item_id,actor_id,action,summary) VALUES (%s,%s,%s,%s,%s)",
        (item["tenant_id"], item["id"], actor, action, str(summary).replace("\n", " ")[:300]),
    )


def record(connection, run, event_key, identifier, title, *, kind="manual", target=None, actor=None):
    row = connection.execute(
        """INSERT INTO attention_items(tenant_id,task_id,event_key,identifier,label,kind,target,authorized_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,event_key)
        DO NOTHING RETURNING *""",
        (run["tenant_id"], run["task_id"], event_key, identifier, title, kind, Jsonb(target or {}), actor),
    ).fetchone()
    if row:
        audit(connection, row, actor, "opened", title)
    else:
        row = connection.execute("SELECT * FROM attention_items WHERE tenant_id=%s AND event_key=%s",
                                 (run["tenant_id"], event_key)).fetchone()
    return row


def get(connection, tenant_id, item_id):
    row = connection.execute("SELECT * FROM attention_items WHERE tenant_id=%s AND id=%s FOR UPDATE",
                             (tenant_id, item_id)).fetchone()
    if not row:
        raise ServiceError("not_found", "Attention item not found.")
    return row


def listing(connection, tenant_id, *, status="pending", offset=0, group="workflow", sort="newest"):
    grouping = {"workflow": "workflow", "employee": "employee", "status": "a.status"}[group]
    ordering = "a.identifier" if sort == "name" else "a.updated_at DESC"
    return connection.execute(
        f"""SELECT a.id,a.task_id,a.identifier,a.label,a.status,a.created_at,a.updated_at,a.done_at,
        a.done_by,a.authorized_by,w.name AS workflow,
        coalesce((SELECT string_agg(e.name,', ' ORDER BY e.name) FROM employees e
          JOIN workflow_employees we ON we.employee_id=e.id AND we.tenant_id=e.tenant_id
          WHERE we.workflow_id=t.workflow_id AND we.tenant_id=a.tenant_id),'') AS employee
        FROM attention_items a JOIN tasks t ON t.id=a.task_id AND t.tenant_id=a.tenant_id
        LEFT JOIN workflows w ON w.id=t.workflow_id AND w.tenant_id=a.tenant_id
        WHERE a.tenant_id=%s AND (%s='all' OR a.status=%s)
        ORDER BY {grouping},{ordering},a.id LIMIT 200 OFFSET %s""", (tenant_id, status, status, offset)
    ).fetchall()


def done(connection, tenant_id, user, item_id):
    item = get(connection, tenant_id, item_id)
    if item["status"] != "done":
        connection.execute("UPDATE attention_items SET status='done',done_by=%s,done_at=now(),updated_at=now() WHERE id=%s",
                           (user["id"], item["id"]))
        audit(connection, item, user["id"], "manual_done", "Marked done by operator.")
    return {"status": "done"}


def enqueue(connection, item, user, operation="attention.refresh"):
    if item["status"] == "done" or not item["target"].get("device_id"):
        return False
    # A tenant member may request a read on an already granted PC; this does
    # not extend that PC's resource grants or impersonate its original owner.
    device = connection.execute("SELECT * FROM desktop_devices WHERE tenant_id=%s AND id=%s AND revoked_at IS NULL AND expires_at>now()",
                                (item["tenant_id"], item["target"]["device_id"])).fetchone()
    if not device:
        return False
    if connection.execute("SELECT id FROM desktop_jobs WHERE tenant_id=%s AND operation=%s AND input->>'item_id'=%s AND state IN ('queued','executing')",
                          (item["tenant_id"], operation, str(item["id"]))).fetchone():
        return False
    payload = {"item_id": str(item["id"])}
    connection.execute("""INSERT INTO desktop_jobs(tenant_id,device_id,actor_id,task_id,operation,input,request_key,request_hash)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (item["tenant_id"], device["id"], user["id"], item["task_id"], operation, Jsonb(payload), uuid4(), str(item["id"])))
    audit(connection, item, user["id"], operation, "External check requested." if operation.endswith("refresh") else "Supplier creation authorized.")
    connection.execute("UPDATE attention_items SET updated_at=now() WHERE id=%s", (item["id"],))
    return True


def refresh(connection, tenant_id, user, item_id=None):
    rows = [get(connection, tenant_id, item_id)] if item_id else connection.execute(
        """SELECT a.* FROM attention_items a WHERE tenant_id=%s AND status='pending' AND target ? 'device_id'
        AND NOT EXISTS (SELECT 1 FROM desktop_jobs j WHERE j.tenant_id=a.tenant_id AND j.input->>'item_id'=a.id::text
            AND (j.state='queued' OR (j.state='executing' AND j.lease_until>now())))
        ORDER BY updated_at,id LIMIT 200 FOR UPDATE""",
        (tenant_id,)).fetchall()
    return {"queued": sum(enqueue(connection, item, user) for item in rows)}


def plan(connection, device, job):
    item = get(connection, device["tenant_id"], job["input"]["item_id"])
    if str(item["target"].get("device_id")) != str(device["id"]) or item["status"] != "pending":
        raise ServiceError("conflict", "Attention item no longer pending on this PC.")
    return item["target"]


def accept(connection, device, job, observation, error=None):
    item = get(connection, device["tenant_id"], job["input"]["item_id"])
    if str(item["target"].get("device_id")) != str(device["id"]):
        raise ServiceError("forbidden", "Wrong attention PC.")
    from .accounts.attention import check_observation, supplier_created
    if error:
        audit(connection, item, job["actor_id"], "failed", error)
        return {"resolved": False}
    verified = check_observation(item, observation)
    if item["kind"] == "supplier" and item["authorized_by"]:
        supplier_created(connection, item, job, verified)
    completed = resolved(item, verified)
    if completed and item["status"] != "done":
        connection.execute("UPDATE attention_items SET status='done',done_by=%s,done_at=now(),updated_at=now() WHERE id=%s",
                           (job["actor_id"], item["id"]))
    audit(connection, item, job["actor_id"], "verified_done" if completed else "still_pending",
          "External resolution verified." if completed else "No verified resolution found.")
    return {"resolved": completed}
