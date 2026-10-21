"""Employee memory for the Accounts desk: structured entries and plain-text instructions.

Memory is runtime data, kept per client business and per employee and shared
by all of that employee's workflows. Sessions look it up only when they need
it; nothing is loaded into context up front.

- Structured entries are contract-like key-values. They are learnt from facts
  the mirror settles, from one-click answers, and from outcomes that were both
  verified and accepted. Each carries its evidence and the native GUIDs it
  refers to.
- Plain-text instructions are only ever written by people.

Callers own transactions; every change records its actor in memory_events.
"""

from psycopg.types.json import Jsonb

EMPLOYEE = "accounts-desk"
EVIDENCE_LIMIT = 20


def _event(connection, entry, action, actor_id=None, detail=None):
    connection.execute(
        """INSERT INTO memory_events(tenant_id,client_id,entry_id,actor_id,action,detail)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (entry["tenant_id"], entry["client_id"], entry["id"], actor_id, action, Jsonb(detail or {})))


def live(connection, tenant_id, client_id, *, company_id, kind, subject, employee=EMPLOYEE):
    return connection.execute(
        """SELECT * FROM memory_entries WHERE tenant_id=%s AND client_id=%s AND employee_key=%s
           AND company_id IS NOT DISTINCT FROM %s AND kind=%s AND subject=%s AND status<>'retired' FOR UPDATE""",
        (tenant_id, client_id, employee, company_id, kind, subject)).fetchone()


def record(connection, *, tenant_id, client_id, company_id, kind, subject, value, evidence, guids=(),
           status, actor_id=None, employee=EMPLOYEE, overrule_answers=False):
    """Create or update the live entry for a subject with new evidence.

    An entry a person answered is never silently replaced by a derived fact;
    the new evidence is kept on it instead, unless `overrule_answers`.
    """
    entry = live(connection, tenant_id, client_id, company_id=company_id, kind=kind, subject=subject, employee=employee)
    if entry is None:
        entry = connection.execute(
            """INSERT INTO memory_entries(tenant_id,client_id,employee_key,company_id,kind,subject,value,guids,
               evidence,status,confirmed_by,confirmed_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s='confirmed' THEN now() END) RETURNING *""",
            (tenant_id, client_id, employee, company_id, kind, subject, Jsonb(value), list(guids), Jsonb([evidence]),
             status, actor_id if status == "confirmed" else None, status)).fetchone()
        _event(connection, entry, "created", actor_id, {"evidence": evidence.get("kind")})
        return entry
    answered = any(item.get("kind") == "answer" for item in entry["evidence"])
    history = [*entry["evidence"], evidence][-EVIDENCE_LIMIT:]
    if entry["value"] == value or (answered and not overrule_answers):
        return connection.execute("UPDATE memory_entries SET evidence=%s,updated_at=now() WHERE id=%s RETURNING *",
                                  (Jsonb(history), entry["id"])).fetchone()
    updated = connection.execute(
        """UPDATE memory_entries SET value=%s,guids=%s,evidence=%s,status=%s,misses=0,version=version+1,
           confirmed_by=CASE WHEN %s='confirmed' THEN %s END,confirmed_at=CASE WHEN %s='confirmed' THEN now() END,
           updated_at=now() WHERE id=%s RETURNING *""",
        (Jsonb(value), list(guids), Jsonb(history), status, status, actor_id, status, entry["id"])).fetchone()
    _event(connection, updated, "changed", actor_id, {"from": entry["value"], "to": value})
    return updated
