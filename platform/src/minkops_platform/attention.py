"""Workflow-agnostic attention items, their audit trail, and the questions a person answers there.

A workflow opens an item for an event that needs a person, such as a gap
between statements, and restates it idempotently by its event key. A question
card is answered once per member: its kind names the module that applies the
answer (QUESTIONS), and a receipt makes a replayed answer return what it did.
"""
import importlib

from psycopg.types.json import Jsonb

from .errors import ServiceError

# Question kinds and the module that shows each card (`question(target)`) and applies its answer
# (`decide(connection, tenant, user, item, action)`).
QUESTIONS = {"layout": "minkops_platform.accounts.statement_layouts",
             "practice": "minkops_platform.accounts.practice"}
PROMPTS = {"layout": "Confirm how to read this statement.", "practice": "Answer how this company keeps its books."}


def audit(connection, item, actor, action, summary, *, detail=None):
    connection.execute(
        """INSERT INTO attention_events(tenant_id,item_id,actor_id,action,summary,detail)
        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
        (item["tenant_id"], item["id"], actor, action, str(summary).replace("\n", " ")[:300], Jsonb(detail or {})),
    )


def record(connection, run, event_key, identifier, title, *, kind="manual", target=None, actor=None, reopen=False):
    """Open the item for an event key, or return the existing one.

    Callers restate holds whenever a run is finalized or re-aggregated; that
    must not undo an operator's Done. `reopen` marks a new event, such as a
    retried save refused again: the item returns to pending with its new
    reason and destination target, because the old resolution no longer holds.
    """
    row = connection.execute(
        """INSERT INTO attention_items(tenant_id,task_id,event_key,identifier,label,kind,target,authorized_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,event_key)
        DO NOTHING RETURNING *""",
        (run["tenant_id"], run["task_id"], event_key, identifier, title, kind, Jsonb(target or {}), actor),
    ).fetchone()
    if row:
        audit(connection, row, actor, "opened", title)
        return row
    row = connection.execute("SELECT * FROM attention_items WHERE tenant_id=%s AND event_key=%s FOR UPDATE",
                             (run["tenant_id"], event_key)).fetchone()
    if reopen and (row["status"] == "done" or row["label"] != title):
        was_done = row["status"] == "done"
        row = connection.execute(
            """UPDATE attention_items SET status='pending',done_by=NULL,done_at=NULL,label=%s,
            target=CASE WHEN %s::jsonb='{}'::jsonb THEN target ELSE %s::jsonb END,updated_at=now()
            WHERE id=%s RETURNING *""",
            (title, Jsonb(target or {}), Jsonb(target or {}), row["id"]),
        ).fetchone()
        audit(connection, row, actor, "reopened" if was_done else "relabelled", title)
    return row


def _scope(visible, workflows):
    """The condition keeping a person to their items, and its parameters: work of the clients they reach
    (`visible`), and of the workflows they run (`workflows`, by key). An item of no workflow, such as a found
    company, reaches everyone, unless it names the workflows it serves, as a practice question does. None reaches
    every client or workflow."""
    clients = None if visible is None else list(visible)
    keys = None if workflows is None else list(workflows)
    return ("""(t.client_id IS NULL OR %s::uuid[] IS NULL OR t.client_id = ANY(%s::uuid[]))
               AND (%s::text[] IS NULL OR w.key = ANY(%s::text[])
                    OR (t.workflow_id IS NULL AND (NOT a.target ? 'workflows' OR a.target->'workflows' ?| %s::text[])))""",
            [clients, clients, keys, keys, keys])


def get(connection, tenant_id, item_id, visible=None, workflows=None):
    """One item; an item outside the person's scope (`_scope`) is indistinguishable from none."""
    condition, parameters = _scope(visible, workflows)
    row = connection.execute(
        f"""SELECT a.* FROM attention_items a JOIN tasks t ON t.tenant_id=a.tenant_id AND t.id=a.task_id
            LEFT JOIN workflows w ON w.id=t.workflow_id AND w.tenant_id=a.tenant_id
            WHERE a.tenant_id=%s AND a.id=%s AND {condition} FOR UPDATE OF a""",
        (tenant_id, item_id, *parameters)).fetchone()
    if not row:
        raise ServiceError("not_found", "Attention item not found.")
    return row


def pending_count(connection, tenant_id, visible=None, workflows=None):
    """How many items await the person, in their scope (`_scope`)."""
    condition, parameters = _scope(visible, workflows)
    return connection.execute(
        f"""SELECT count(*) AS n FROM attention_items a JOIN tasks t ON t.tenant_id=a.tenant_id AND t.id=a.task_id
            LEFT JOIN workflows w ON w.id=t.workflow_id AND w.tenant_id=a.tenant_id
            WHERE a.tenant_id=%s AND a.status='pending' AND {condition}""", (tenant_id, *parameters)).fetchone()["n"]


def listing(connection, tenant_id, *, status="pending", offset=0, group="workflow", sort="newest", visible=None,
            workflows=None):
    """Items by group and order, in the person's scope (`_scope`)."""
    grouping = {"workflow": "workflow", "employee": "employee", "status": "a.status", "client": "client"}[group]
    ordering = "a.identifier" if sort == "name" else "a.updated_at DESC"
    condition, parameters = _scope(visible, workflows)
    rows = connection.execute(
        f"""SELECT a.id,a.task_id,a.identifier,a.label,a.kind,a.status,a.created_at,a.updated_at,a.done_at,a.target,
        a.done_by,a.authorized_by,w.name AS workflow,c.name AS client,
        coalesce((SELECT string_agg(e.name,', ' ORDER BY e.name) FROM employees e
          JOIN workflow_employees we ON we.employee_id=e.id AND we.tenant_id=e.tenant_id
          WHERE we.workflow_id=t.workflow_id AND we.tenant_id=a.tenant_id),'') AS employee
        FROM attention_items a JOIN tasks t ON t.id=a.task_id AND t.tenant_id=a.tenant_id
        LEFT JOIN workflows w ON w.id=t.workflow_id AND w.tenant_id=a.tenant_id
        LEFT JOIN client_businesses c ON c.id=t.client_id AND c.tenant_id=a.tenant_id
        WHERE a.tenant_id=%s AND (%s='all' OR a.status=%s) AND {condition}
        ORDER BY {grouping},{ordering},a.id LIMIT 200 OFFSET %s""",
        (tenant_id, status, status, *parameters, offset)
    ).fetchall()
    for row in rows:
        target = row.pop("target")
        row["reason"] = target.get("reason") or PROMPTS.get(row["kind"]) or row["label"]
        if row["kind"] in QUESTIONS:
            row["question"] = importlib.import_module(QUESTIONS[row["kind"]]).question(target)
        # A card's own details, such as the client a found company continues, are for those who reach every client.
        if visible is None and target.get("card"):
            row["card"] = target["card"]
    return rows


def done(connection, tenant_id, user, item_id, visible=None, workflows=None):
    item = get(connection, tenant_id, item_id, visible, workflows)
    if item["status"] != "done":
        connection.execute("UPDATE attention_items SET status='done',done_by=%s,done_at=now(),updated_at=now() WHERE id=%s",
                           (user["id"], item["id"]))
        audit(connection, item, user["id"], "manual_done", "Marked done by operator.")
    return {"status": "done"}


def decide(connection, tenant, user, item_id, action, visible=None, workflows=None):
    """Answer a question card once per member; the same answer again returns its receipt."""
    # Serialize exact replays before examining the mutable item.
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                       (f"attention-decision:{tenant['id']}:{item_id}",))
    receipt = decision_receipt(connection, tenant["id"], user["id"], item_id, visible, workflows)
    if receipt:
        if receipt["action"] != action:
            raise ServiceError("conflict", "This item already has a different decision from you.")
        return receipt
    item = get(connection, tenant["id"], item_id, visible, workflows)
    if item["kind"] not in QUESTIONS or item["status"] != "pending":
        raise ServiceError("conflict", "This item is no longer awaiting a decision.")
    outcome = importlib.import_module(QUESTIONS[item["kind"]]).decide(connection, tenant, user, item, action)
    return connection.execute(
        """INSERT INTO attention_decision_receipts(tenant_id,item_id,actor_id,action,status)
           VALUES(%s,%s,%s,%s,%s) RETURNING item_id,actor_id,action,status,applied_at""",
        (tenant["id"], item_id, user["id"], action, outcome["status"])).fetchone()


def decision_receipt(connection, tenant_id, actor_id, item_id, visible=None, workflows=None):
    get(connection, tenant_id, item_id, visible, workflows)  # Scope even an absent receipt.
    return connection.execute("""SELECT item_id,actor_id,action,status,applied_at
        FROM attention_decision_receipts WHERE tenant_id=%s AND actor_id=%s AND item_id=%s""",
        (tenant_id, actor_id, item_id)).fetchone()
