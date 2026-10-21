"""Runs, items, records and decisions: durable scheduling without run JSON.

A run is one launch for one client business. Each item (a bill, a statement
chunk, a layout reading) is scheduled on its own; each record (a bill or a
statement row) is reviewed and decided on its own, and results stream out as
items finish. An item waits on a named blocker and is released by a committed
state change, which wakes workers through the run_items trigger; a released
dependency never depends on a config edit or a sweep. Leases fence every item
transition. Decisions are idempotent per record version.

Callers own transactions. Nothing here reasons about bills or statements.
"""

import hashlib
import importlib
import json
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from .errors import ServiceError
from .run_controls import observe_task

LEASE_SECONDS = 300
ITEM_STATES = ("waiting", "queued", "running", "done", "failed", "cancelled")
RECORD_STATUSES = ("pending", "proposed", "held", "approved", "writing", "saved", "duplicate", "deferred")
# Records that still need their session, a person, the destination, or both.
UNSETTLED = ("pending", "proposed", "held", "approved", "writing")
TASK_STATE = {"preparing": "queued", "running": "executing", "review": "review", "writing": "writing",
              "completed": "completed", "failed": "failed"}


@dataclass(frozen=True)
class ItemSpec:
    kind: str
    source: dict
    waiting_on: dict | None = None


def digest(content):
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def launch(connection, *, tenant_id, client_id, workflow, handler, definition_version, bundle, actor_id,
           request_key, request_hash, config, title, items):
    """Create the task, pinned bundle, run and items together; items start queued or waiting.

    `handler` is the installed binding's handler key, which the caller read
    from trusted installation state.
    """
    if not items:
        raise ServiceError("invalid", "Select at least one input.")
    bundle_digest = digest(bundle)
    connection.execute(
        "INSERT INTO run_bundles(tenant_id,digest,content) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
        (tenant_id, bundle_digest, Jsonb(bundle)))
    task = connection.execute(
        "INSERT INTO tasks(tenant_id,workflow_id,client_id,title,summary) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (tenant_id, workflow["id"], client_id, title, "Queued.")).fetchone()
    waiting = any(spec.waiting_on for spec in items)
    run = connection.execute(
        """INSERT INTO runs(tenant_id,client_id,task_id,workflow_id,workflow_key,handler,definition_version,
           bundle_digest,actor_id,request_key,request_hash,config,state)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (tenant_id, client_id, task["id"], workflow["id"], workflow["key"], handler,
         definition_version, bundle_digest, actor_id, request_key, request_hash, Jsonb(config),
         "preparing" if waiting else "running")).fetchone()
    add_items(connection, run, items)
    observe_task(connection, tenant_id=tenant_id, task_id=task["id"], run_id=run["id"], state="queued",
                 summary="Getting ready." if waiting else "Queued.", progress=0, event_prefix="run")
    return run


def add_items(connection, run, items):
    """Append items to a run, queued or waiting; their ordinals follow the run's last item.

    The run row is locked first: two items settling at once both add items.
    """
    connection.execute("SELECT 1 FROM runs WHERE id=%s FOR UPDATE", (run["id"],))
    start = connection.execute("SELECT coalesce(max(ordinal)+1,0) AS next FROM run_items WHERE run_id=%s",
                               (run["id"],)).fetchone()["next"]
    return connection.execute(
        """INSERT INTO run_items(tenant_id,run_id,task_id,ordinal,kind,source,state,waiting_on,queued_at)
           SELECT %s,%s,%s,%s+n-1,kind,source,state,waiting_on,CASE WHEN state='queued' THEN now() END
           FROM unnest(%s::text[],%s::jsonb[],%s::text[],%s::jsonb[]) WITH ORDINALITY
               AS item(kind,source,state,waiting_on,n)
           RETURNING *""",
        (run["tenant_id"], run["id"], run["task_id"], start, [spec.kind for spec in items],
         [Jsonb(spec.source) for spec in items], ["waiting" if spec.waiting_on else "queued" for spec in items],
         [Jsonb(spec.waiting_on) if spec.waiting_on else None for spec in items])).fetchall()


# The closed registry of workflow handlers: pinned handler keys to fixed module
# paths in this codebase. Keys come from installed definitions, never requests.
HANDLER_MODULES = {"desk.bill": "minkops_platform.accounts.bill_entry",
                   "desk.statement": "minkops_platform.accounts.statement_entry"}


def handler_for(run):
    module = HANDLER_MODULES.get(run["handler"])
    if module is None:
        raise ServiceError("conflict", "This workflow is not available in this version of Minkops.")
    return importlib.import_module(module).HANDLER


def find_by_request(connection, tenant_id, request_key):
    return connection.execute("SELECT * FROM runs WHERE tenant_id=%s AND request_key=%s",
                              (tenant_id, request_key)).fetchone()


def get_run(connection, tenant_id, run_id):
    row = connection.execute("SELECT * FROM runs WHERE tenant_id=%s AND id=%s", (tenant_id, run_id)).fetchone()
    if not row:
        raise ServiceError("not_found", "Run not found.")
    return row


# --- items ------------------------------------------------------------------

_CLAIM = """
WITH next AS (
    SELECT i.id, i.state AS previous FROM run_items i
    JOIN tasks t ON t.tenant_id=i.tenant_id AND t.id=i.task_id
    WHERE {where} AND t.control_state='active'
        AND (%(kinds)s::text[] IS NULL OR i.kind = ANY(%(kinds)s))
        AND (%(tenant)s::uuid IS NULL OR i.tenant_id=%(tenant)s::uuid)
    ORDER BY {order} FOR UPDATE OF i SKIP LOCKED LIMIT 1)
UPDATE run_items i SET state='running', lease_token=gen_random_uuid(),
    lease_until=now()+make_interval(secs=>%(lease)s),
    attempt=CASE WHEN next.previous='queued' THEN i.attempt+1 ELSE i.attempt END,
    started_at=coalesce(i.started_at,now()), updated_at=now()
FROM next WHERE i.id=next.id RETURNING i.*, next.previous='running' AS reclaimed"""


def claim(connection, *, kinds=None, tenant_id=None, lease_seconds=LEASE_SECONDS):
    """Lease the next runnable item, optionally of these kinds, or take over an expired lease.

    A reclaimed item keeps its saved provider session for the new lane to
    reattach; it is the same attempt, not a new paid one. Paused and stopped
    tasks are never claimed, and a retry waits until its time comes.
    """
    parameters = {"kinds": list(kinds) if kinds else None, "tenant": tenant_id, "lease": lease_seconds}
    for where, order in (("i.state='queued' AND i.queued_at <= now()", "i.queued_at, i.id"),
                         ("i.state='running' AND i.lease_until < now()", "i.lease_until, i.id")):
        row = connection.execute(_CLAIM.format(where=where, order=order), parameters).fetchone()
        if row:
            return row
    return None


def runnable(connection, tenant_id=None):
    """Whether any item is queued for an active task, or running anywhere, so a drain must not end."""
    return connection.execute(
        """SELECT EXISTS (SELECT 1 FROM run_items i JOIN tasks t ON t.tenant_id=i.tenant_id AND t.id=i.task_id
               WHERE ((i.state='queued' AND t.control_state='active') OR i.state='running')
                   AND (%s::uuid IS NULL OR i.tenant_id=%s::uuid)) AS runnable""",
        (tenant_id, tenant_id)).fetchone()["runnable"]


def _fenced(connection, item_id, token, assignments, values=()):
    row = connection.execute(
        f"UPDATE run_items SET {assignments}, updated_at=now() WHERE id=%s AND lease_token=%s AND state='running' RETURNING id",
        (*values, item_id, token)).fetchone()
    return row is not None


def renew(connection, item_id, token, lease_seconds=LEASE_SECONDS):
    return _fenced(connection, item_id, token, "lease_until=now()+make_interval(secs=>%s)", (lease_seconds,))


def renew_all(connection, held, lease_seconds=LEASE_SECONDS):
    """Extend every lease still held, as {item_id: its task's control state}; a missing item lost its fence."""
    if not held:
        return {}
    rows = connection.execute(
        """UPDATE run_items i SET lease_until=now()+make_interval(secs=>%s)
           FROM unnest(%s::uuid[], %s::uuid[]) AS held(id, token), tasks t
           WHERE i.id=held.id AND i.lease_token=held.token AND i.state='running'
               AND t.tenant_id=i.tenant_id AND t.id=i.task_id
           RETURNING i.id, t.control_state""",
        (lease_seconds, [item_id for item_id, _ in held], [token for _, token in held])).fetchall()
    return {row["id"]: row["control_state"] for row in rows}


def request_session(connection, item_id, token):
    """Record, before asking the provider, that this attempt may now have a session; its Unix time or None."""
    row = connection.execute(
        """UPDATE run_items SET session_requested_at=coalesce(session_requested_at,now()), updated_at=now()
           WHERE id=%s AND lease_token=%s AND state='running'
           RETURNING extract(epoch FROM session_requested_at)::float8 AS at""", (item_id, token)).fetchone()
    return row["at"] if row else None


def save_session(connection, item_id, token, session_id, turn_id):
    """Persist provider IDs as soon as they exist, so a restart reattaches instead of resubmitting."""
    return _fenced(connection, item_id, token, "session_id=coalesce(%s,session_id), turn_id=coalesce(%s,turn_id)",
                   (session_id, turn_id))


def finish(connection, item_id, token, state, *, error_code=None, error=None, usage=None):
    if state not in ("done", "failed", "cancelled"):
        raise ValueError("An item finishes done, failed or cancelled.")
    return _fenced(connection, item_id, token,
                   "state=%s, error_code=%s, error=%s, usage=coalesce(%s,usage), finished_at=now(), "
                   "lease_token=NULL, lease_until=NULL",
                   (state, error_code, (error or "")[:400] or None, Jsonb(usage) if usage else None))


def retry(connection, item_id, token, *, delay, error_code, error):
    """Queue a new attempt with a fresh session after `delay` seconds, keeping why the last one failed."""
    return _fenced(connection, item_id, token,
                   "state='queued', queued_at=now()+make_interval(secs=>%s), session_id=NULL, turn_id=NULL, "
                   "session_requested_at=NULL, session_closed=false, error_code=%s, error=%s, "
                   "lease_token=NULL, lease_until=NULL",
                   (delay, error_code, (error or "")[:400] or None))


def wait(connection, item_id, token, waiting_on):
    """Park a running item on a named blocker; it keeps its session for later."""
    return _fenced(connection, item_id, token, "state='waiting', waiting_on=%s, lease_token=NULL, lease_until=NULL",
                   (Jsonb(waiting_on),))


def hand_off(connection, held):
    """Expire these leases now so a successor resumes each item and its session at once."""
    if held:
        connection.execute(
            """UPDATE run_items i SET lease_until=now() FROM unnest(%s::uuid[], %s::uuid[]) AS held(id, token)
               WHERE i.id=held.id AND i.lease_token=held.token AND i.state='running'""",
            ([item_id for item_id, _ in held], [token for _, token in held]))


def unclosed(connection, *, tenant_id=None, limit=20):
    """Finished items whose provider session is still open, oldest first, with seconds since they finished."""
    return connection.execute(
        """SELECT id, session_id, turn_id, usage, extract(epoch FROM now()-finished_at)::float8 AS age
           FROM run_items WHERE state IN ('done','failed','cancelled') AND session_id IS NOT NULL
               AND NOT session_closed AND (%s::uuid IS NULL OR tenant_id=%s::uuid)
           ORDER BY finished_at LIMIT %s""", (tenant_id, tenant_id, limit)).fetchall()


def closed(connection, item_id, session_id, usage):
    """Record that the session was deleted at the provider, keeping its usage if the item had none."""
    connection.execute("UPDATE run_items SET session_closed=true, usage=coalesce(usage,%s) WHERE id=%s AND session_id=%s",
                       (Jsonb(usage) if usage else None, item_id, session_id))


def release(connection, tenant_id, blocker):
    """Queue every item waiting on this blocker. The trigger wakes workers on commit."""
    return connection.execute(
        """UPDATE run_items SET state='queued', waiting_on=NULL, queued_at=now(), updated_at=now()
           WHERE tenant_id=%s AND state='waiting' AND waiting_on @> %s""",
        (tenant_id, Jsonb(blocker))).rowcount


def requeue_item(connection, tenant_id, item_id):
    """An explicit Recheck: a new attempt for a finished item, never a replay of a live one."""
    row = connection.execute(
        """UPDATE run_items SET state='queued', queued_at=now(), session_id=NULL, turn_id=NULL, session_closed=false,
           session_requested_at=NULL, error_code=NULL, error=NULL, finished_at=NULL, updated_at=now()
           WHERE tenant_id=%s AND id=%s AND state IN ('done','failed') RETURNING *""",
        (tenant_id, item_id)).fetchone()
    if not row:
        raise ServiceError("conflict", "This input is still being processed.")
    return row


def cancel(connection, tenant_id, run_id):
    """Stop: unstarted items are cancelled; a running one stops at its next fence check."""
    return connection.execute(
        """UPDATE run_items SET state='cancelled', waiting_on=NULL, updated_at=now()
           WHERE tenant_id=%s AND run_id=%s AND state IN ('waiting','queued')""", (tenant_id, run_id)).rowcount


# --- records ----------------------------------------------------------------

_RECORD_FIELDS = ("kind", "source", "company_id", "facts", "proposal", "checks", "status", "hold_codes",
                  "review_reasons", "plan", "current")
_JSON_FIELDS = {"source", "facts", "proposal", "checks", "plan", "current"}


def _value(field, value):
    return Jsonb(value) if field in _JSON_FIELDS and value is not None else value


def add_records(connection, item, records):
    """Append an item's records; positions continue after any it already has."""
    start = connection.execute("SELECT coalesce(max(position)+1,0) AS next FROM run_records WHERE item_id=%s",
                               (item["id"],)).fetchone()["next"]
    rows = []
    for offset, record in enumerate(records):
        unknown = set(record) - set(_RECORD_FIELDS)
        if unknown:
            raise ValueError(f"Unknown record fields: {sorted(unknown)}")
        fields = [field for field in _RECORD_FIELDS if field in record]
        rows.append(connection.execute(
            f"""INSERT INTO run_records(tenant_id,run_id,item_id,position,{','.join(fields)})
                VALUES (%s,%s,%s,%s,{','.join(['%s'] * len(fields))}) RETURNING *""",
            (item["tenant_id"], item["run_id"], item["id"], start + offset,
             *(_value(field, record[field]) for field in fields))).fetchone())
    return rows


def get_record(connection, tenant_id, record_id, *, lock=False):
    row = connection.execute("SELECT * FROM run_records WHERE tenant_id=%s AND id=%s" + (" FOR UPDATE" if lock else ""),
                             (tenant_id, record_id)).fetchone()
    if not row:
        raise ServiceError("not_found", "Record not found.")
    return row


def update_record(connection, record, **changes):
    """Apply changes to the version the caller read; any concurrent change conflicts."""
    unknown = set(changes) - set(_RECORD_FIELDS)
    if unknown:
        raise ValueError(f"Unknown record fields: {sorted(unknown)}")
    assignments = ", ".join(f"{field}=%s" for field in changes)
    row = connection.execute(
        f"""UPDATE run_records SET {assignments}{',' if changes else ''} version=version+1, updated_at=now()
            WHERE id=%s AND version=%s RETURNING *""",
        (*(_value(field, value) for field, value in changes.items()), record["id"], record["version"])).fetchone()
    if not row:
        raise ServiceError("conflict", "This item changed while it was being updated. Review its current state.")
    record.clear()
    record.update(row)
    return row


def decide(connection, *, tenant_id, record_id, version, actor_id, action, apply, detail=None):
    """One decision per record version, safe to repeat after a lost response.

    The same actor repeating the same action on the same version gets the
    stored receipt (`replayed`). A different action or actor on a decided
    version conflicts and is answered with the receipt that won; a version
    that has since changed is stale. `apply(record)` performs the domain
    effect, updating the record through update_record, and returns the receipt.
    """
    detail = detail or {}
    record = get_record(connection, tenant_id, record_id, lock=True)
    existing = connection.execute(
        "SELECT * FROM record_decisions WHERE tenant_id=%s AND record_id=%s AND record_version=%s",
        (tenant_id, record_id, version)).fetchone()
    if existing:
        if (str(existing["actor_id"]), existing["action"], existing["detail"]) == (str(actor_id), action, detail):
            return {**existing["receipt"], "replayed": True}
        raise ServiceError("conflict", "This item was already decided.", {"receipt": existing["receipt"]})
    if record["version"] != version:
        raise ServiceError("conflict", "This item changed since it was shown. Review its current state.",
                           {"version": record["version"], "status": record["status"]})
    receipt = {**apply(record), "record_id": str(record_id), "decided_version": version, "action": action}
    connection.execute(
        """INSERT INTO record_decisions(tenant_id,record_id,record_version,actor_id,action,detail,receipt)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (tenant_id, record_id, version, actor_id, action, Jsonb(detail), Jsonb(receipt)))
    return {**receipt, "replayed": False}


# --- status -----------------------------------------------------------------

def status(connection, tenant_id, run_id):
    """What a poll needs, bounded regardless of how many rows a run has."""
    run = get_run(connection, tenant_id, run_id)
    items = dict.fromkeys(ITEM_STATES, 0)
    for row in connection.execute("SELECT state,count(*) AS n FROM run_items WHERE run_id=%s GROUP BY state", (run_id,)):
        items[row["state"]] = row["n"]
    records = dict.fromkeys(RECORD_STATUSES, 0)
    reviewing = 0
    for row in connection.execute(
            """SELECT status,count(*) AS n,count(*) FILTER (WHERE review_reasons<>'{}') AS review
               FROM run_records WHERE run_id=%s GROUP BY status""", (run_id,)):
        records[row["status"]] = row["n"]
        reviewing += row["review"]
    blockers = connection.execute(
        """SELECT waiting_on->>'kind' AS kind, waiting_on->>'ref' AS ref, count(*) AS items
           FROM run_items WHERE run_id=%s AND state='waiting' GROUP BY 1,2 ORDER BY 3 DESC LIMIT 20""",
        (run_id,)).fetchall()
    activity = connection.execute(
        """SELECT greatest(r.updated_at, (SELECT max(updated_at) FROM run_items WHERE run_id=r.id),
               (SELECT max(updated_at) FROM run_records WHERE run_id=r.id)) AS at FROM runs r WHERE r.id=%s""",
        (run_id,)).fetchone()["at"]
    control = connection.execute("SELECT control_state FROM tasks WHERE tenant_id=%s AND id=%s",
                                 (tenant_id, run["task_id"])).fetchone()["control_state"]
    return {"run": {key: run[key] for key in ("id", "task_id", "workflow_key", "state", "created_at", "updated_at")}
            | {"control_state": control}, "items": items, "records": {**records, "review_required": reviewing},
            "blockers": blockers, "activity": activity.isoformat() if activity else None}


def records_page(connection, tenant_id, run_id, *, summarize, after=None, limit=100):
    """A page of record summaries in run order; `next` continues after the last one."""
    limit = max(1, min(int(limit), 200))
    get_run(connection, tenant_id, run_id)
    cursor = after.split(":") if after else None
    rows = connection.execute(
        f"""SELECT r.*, i.ordinal FROM run_records r JOIN run_items i ON i.id=r.item_id
            WHERE r.run_id=%s {"AND (i.ordinal, r.position) > (%s, %s)" if cursor else ""}
            ORDER BY i.ordinal, r.position LIMIT %s""",
        (run_id, *(int(part) for part in cursor or ()), limit + 1)).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    return {"records": [summarize(row) for row in rows],
            "next": f"{rows[-1]['ordinal']}:{rows[-1]['position']}" if more else None}


def refresh(connection, tenant_id, run_id, *, describe=None):
    """Derive the run's state from its items and records and publish it on the task."""
    counts = status(connection, tenant_id, run_id)
    items, records = counts["items"], counts["records"]
    active = items["queued"] + items["running"]
    if active or items["waiting"]:
        waiting_only_on_sync = not active and all(b["kind"] == "sync" for b in counts["blockers"])
        started = any(records[s] for s in RECORD_STATUSES if s != "pending")
        state = "preparing" if waiting_only_on_sync and not started else "running"
    elif records["writing"]:
        state = "writing"
    elif any(records[s] for s in ("proposed", "held", "approved")):
        state = "review"
    elif items["failed"] and not any(records.values()):
        state = "failed"
    else:
        state = "completed"
    run = get_run(connection, tenant_id, run_id)
    summary, progress = (describe or _describe)(state, items, records)
    if state != run["state"]:
        connection.execute("UPDATE runs SET state=%s,updated_at=now() WHERE id=%s", (state, run_id))
    task = connection.execute("SELECT control_state,status,summary,progress FROM tasks WHERE tenant_id=%s AND id=%s",
                              (tenant_id, run["task_id"])).fetchone()
    from .run_controls import TASK_STATUS
    # Publish only a change: an unchanged poll or receipt writes no timeline event.
    if task["control_state"] != "stopped" and (task["status"], task["summary"], task["progress"]) != (
            TASK_STATUS[TASK_STATE[state]], summary, progress):
        observe_task(connection, tenant_id=tenant_id, task_id=run["task_id"], run_id=run_id,
                     state=TASK_STATE[state], summary=summary, progress=progress, event_prefix="run")
    return state


def _describe(state, items, records):
    total = sum(items.values()) - items["cancelled"]
    finished = items["done"] + items["failed"]
    settled = records["saved"] + records["duplicate"] + records["deferred"]
    if state in ("preparing", "running"):
        return (f"{finished} of {total} inputs read." if state == "running" else "Getting ready."), \
            min(60, 60 * finished // max(total, 1))
    if state == "writing":
        return "Saving approved entries and checking them in Tally.", 85
    if state == "review":
        return f"{records['proposed'] + records['approved']} ready to save; {records['held']} need attention.", 70
    if state == "failed":
        return "The inputs could not be processed. Recheck them or start a new run.", 100
    return f"{settled} entries settled.", 100
