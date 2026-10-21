"""Employee memory for the Accounts desk: structured entries and plain-text rules.

Memory is runtime data, kept per client business and per employee and shared
by all of that employee's workflows. Sessions look it up only when they need
it; nothing is loaded into context up front.

- Structured entries are contract-like key-values with the evidence behind
  them and the native GUIDs they name. `practice` entries say how a company
  keeps its books, from the sync's probes or a person's one-click answer.
  `booking` entries say how a supplier's bills are booked, learnt from saves
  that were verified and approved.
- Every sync revalidates them: an edit made in Tally to a voucher an entry was
  learnt from demotes it, and an entry whose GUIDs are missing from three syncs
  in a row retires.
- Rules (plain-text instructions) are only ever written by people. They are
  scoped to a workflow or company, versioned, and cited by ID and version.

Only workspace admins change memory; every change records its actor in
memory_events. Callers own transactions.
"""

from psycopg.types.json import Jsonb

from minkops_platform import clients
from minkops_platform.errors import ServiceError

from . import mirror

EMPLOYEE = "accounts-desk"
EVIDENCE_LIMIT = 20
# What lookups and checks see; a disabled or retired entry is never offered.
LIVE = ("unconfirmed", "confirmed", "demoted")
MISSES = 3
# Sessions read every active rule in one answer, so a client keeps at most this many per employee.
RULES = 30


def _event(connection, row, action, actor_id=None, detail=None, *, instruction=False):
    connection.execute(
        """INSERT INTO memory_events(tenant_id,client_id,entry_id,instruction_id,actor_id,action,detail)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (row["tenant_id"], row["client_id"], None if instruction else row["id"], row["id"] if instruction else None,
         actor_id, action, Jsonb(detail or {})))


# --- structured entries -------------------------------------------------------

def live(connection, tenant_id, client_id, *, company_id, kind, subject, employee=EMPLOYEE):
    return connection.execute(
        """SELECT * FROM memory_entries WHERE tenant_id=%s AND client_id=%s AND employee_key=%s
           AND company_id IS NOT DISTINCT FROM %s AND kind=%s AND subject=%s AND status<>'retired' FOR UPDATE""",
        (tenant_id, client_id, employee, company_id, kind, subject)).fetchone()


def entries(connection, tenant_id, client_id, *, company_ids, kinds=None, subjects=None, statuses=LIVE,
            employee=EMPLOYEE):
    """Entries for these companies and client-wide ones, optionally of some kinds or about some subjects."""
    return connection.execute(
        """SELECT * FROM memory_entries WHERE tenant_id=%s AND client_id=%s AND employee_key=%s
           AND (company_id IS NULL OR company_id = ANY(%s::uuid[])) AND status = ANY(%s)
           AND (%s::text[] IS NULL OR kind = ANY(%s)) AND (%s::text[] IS NULL OR subject = ANY(%s) OR guids && %s)
           ORDER BY kind, subject, company_id""",
        (tenant_id, client_id, employee, list(company_ids), list(statuses), kinds, kinds, subjects, subjects,
         subjects)).fetchall()


def record(connection, *, tenant_id, client_id, company_id, kind, subject, value, evidence, guids=(),
           status, actor_id=None, employee=EMPLOYEE, overrule_answers=False, use=False):
    """Create or update the live entry for a subject with new evidence.

    An entry a person answered is never silently replaced by a derived fact;
    the new evidence is kept on it instead, unless `overrule_answers`. A
    confirmed outcome that agrees with a demoted or unconfirmed entry confirms
    it: one approval confirms what a bill relied on. A disabled entry only
    gathers evidence until an admin enables it.
    """
    entry = live(connection, tenant_id, client_id, company_id=company_id, kind=kind, subject=subject, employee=employee)
    if entry is None:
        entry = connection.execute(
            """INSERT INTO memory_entries(tenant_id,client_id,employee_key,company_id,kind,subject,value,guids,
               evidence,status,uses,confirmed_by,confirmed_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s='confirmed' THEN now() END) RETURNING *""",
            (tenant_id, client_id, employee, company_id, kind, subject, Jsonb(value), list(guids), Jsonb([evidence]),
             status, int(use), actor_id if status == "confirmed" else None, status)).fetchone()
        _event(connection, entry, "created", actor_id, {"evidence": evidence.get("kind")})
        return entry
    answered = any(item.get("kind") == "answer" for item in entry["evidence"])
    history = [*entry["evidence"], evidence][-EVIDENCE_LIMIT:]
    disabled = entry["status"] == "disabled"
    if entry["value"] == value or (answered and not overrule_answers) or disabled:
        confirm = entry["value"] == value and status == "confirmed" and entry["status"] in ("unconfirmed", "demoted")
        updated = connection.execute(
            """UPDATE memory_entries SET evidence=%s, uses=uses+%s, updated_at=now(),
               status=CASE WHEN %s THEN 'confirmed' ELSE status END, misses=CASE WHEN %s THEN 0 ELSE misses END,
               confirmed_by=CASE WHEN %s THEN %s ELSE confirmed_by END,
               confirmed_at=CASE WHEN %s THEN now() ELSE confirmed_at END WHERE id=%s RETURNING *""",
            (Jsonb(history), int(use and entry["value"] == value), confirm, confirm, confirm, actor_id, confirm,
             entry["id"])).fetchone()
        if confirm:
            _event(connection, updated, "confirmed", actor_id)
        return updated
    updated = connection.execute(
        """UPDATE memory_entries SET value=%s,guids=%s,evidence=%s,status=%s,misses=0,uses=%s,version=version+1,
           confirmed_by=CASE WHEN %s='confirmed' THEN %s END,confirmed_at=CASE WHEN %s='confirmed' THEN now() END,
           updated_at=now() WHERE id=%s RETURNING *""",
        (Jsonb(value), list(guids), Jsonb(history), status, int(use), status, actor_id, status, entry["id"])).fetchone()
    _event(connection, updated, "changed", actor_id, {"from": entry["value"], "to": value})
    return updated


def learn_booking(connection, run, record_row, plan, voucher_guid, *, actor_id, guessed):
    """A verified save a person approved becomes how this supplier's bills are booked.

    A best guess is kept unconfirmed: it stays under review until a person
    approves a bill booked the same way.
    """
    references, party = plan["references"]["ledgers"], plan["header"]["party_ledger"]
    lines = sorted({line["ledger"] for line in plan["lines"]} - {party})
    guid = (references.get(party) or {}).get("GUID")
    if not guid:
        return None
    return record(connection, tenant_id=run["tenant_id"], client_id=run["client_id"],
                  company_id=record_row["company_id"], kind="booking", subject=guid,
                  value={"voucher_type": plan["voucher_type"]["NAME"], "ledgers": lines},
                  guids=[guid, plan["voucher_type"]["GUID"], *(references[name]["GUID"] for name in lines)],
                  evidence={"kind": "outcome", "voucher": voucher_guid, "run": str(run["id"]),
                            "record": str(record_row["id"])},
                  status="unconfirmed" if guessed else "confirmed", actor_id=actor_id, use=True)


def revalidate(connection, company, version):
    """After a sync: an edit made in Tally to a voucher an entry was learnt from demotes it, and an entry whose
    GUIDs are missing from three syncs in a row retires."""
    rows = connection.execute(
        "SELECT * FROM memory_entries WHERE company_id=%s AND status = ANY(%s) FOR UPDATE",
        (company["id"], list(LIVE))).fetchall()
    if not rows:
        return
    named = sorted({guid for row in rows for guid in row["guids"]})
    names = {row["guid"]: row["name"] for row in mirror.masters(connection, company["id"], version["version"],
                                                                 guids=named)}
    learnt = sorted({item["voucher"] for row in rows if row["kind"] == "booking" for item in row["evidence"]
                     if item.get("kind") == "outcome" and item.get("voucher")})
    vouchers = {row["guid"]: row for row in mirror.vouchers(connection, company["id"], version["version"], guids=learnt)}
    for entry in rows:
        missing = [guid for guid in entry["guids"] if guid not in names]
        misses = entry["misses"] + 1 if missing else 0
        if misses >= MISSES:
            connection.execute("UPDATE memory_entries SET status='retired',misses=%s,updated_at=now() WHERE id=%s",
                               (misses, entry["id"]))
            _event(connection, entry, "retired", detail={"missing": missing})
            continue
        if misses != entry["misses"]:
            connection.execute("UPDATE memory_entries SET misses=%s,updated_at=now() WHERE id=%s",
                               (misses, entry["id"]))
        changed = _rebooked(entry, vouchers, names)
        if changed and entry["status"] != "demoted":
            connection.execute("UPDATE memory_entries SET status='demoted',updated_at=now() WHERE id=%s",
                               (entry["id"],))
            _event(connection, entry, "demoted", detail=changed)


def _rebooked(entry, vouchers, names):
    """How a voucher this booking was learnt from now differs in Tally, or None when none does.

    A booking names its supplier, voucher type and then its ledgers by GUID, so a
    ledger renamed in Tally is still the same booking.
    """
    if entry["kind"] != "booking":
        return None
    wanted = {names.get(guid) for guid in entry["guids"][2:]} if all(
        guid in names for guid in entry["guids"][2:]) else set(entry["value"]["ledgers"])
    for item in entry["evidence"]:
        if item.get("kind") != "outcome" or not item.get("voucher"):
            continue
        voucher = vouchers.get(item["voucher"])
        if voucher is None or voucher["cancelled"]:
            return {"voucher": item["voucher"], "now": "deleted or cancelled"}
        if not wanted <= set(voucher["ledgers"]):
            return {"voucher": item["voucher"], "now": sorted(voucher["ledgers"])}
    return None


# --- rules ------------------------------------------------------------------------

def instructions(connection, tenant_id, client_id, *, workflow_key, company_ids, employee=EMPLOYEE):
    """The active rules for a workflow's run over these companies: client-wide ones and theirs."""
    return connection.execute(
        """SELECT * FROM memory_instructions WHERE tenant_id=%s AND client_id=%s AND employee_key=%s
           AND status='active' AND (workflow_key IS NULL OR workflow_key=%s)
           AND (company_id IS NULL OR company_id = ANY(%s::uuid[])) ORDER BY created_at, id""",
        (tenant_id, client_id, employee, workflow_key, list(company_ids))).fetchall()


def _version(connection, row, actor_id):
    connection.execute(
        """INSERT INTO memory_instruction_versions(tenant_id,instruction_id,version,text,workflow_key,company_id,
           status,actor_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (row["tenant_id"], row["id"], row["version"], row["text"], row["workflow_key"], row["company_id"],
         row["status"], actor_id))


def _room(connection, tenant_id, client_id, employee):
    """Refuse another active rule once a client has as many as a session reads at once."""
    if connection.execute(
            """SELECT count(*) AS n FROM memory_instructions WHERE tenant_id=%s AND client_id=%s AND employee_key=%s
               AND status='active'""", (tenant_id, client_id, employee)).fetchone()["n"] >= RULES:
        raise ServiceError("conflict", f"This client already has {RULES} active rules. Disable or delete one first.")


def _store(connection, tenant_id, client_id, *, employee, text, workflow_key, company_id, actor_id, instruction_id=None):
    text = " ".join(str(text or "").split())
    if not 1 <= len(text) <= 2000:
        raise ServiceError("invalid", "Write the rule in 1 to 2,000 characters.")
    if instruction_id is None:
        _room(connection, tenant_id, client_id, employee)
        row = connection.execute(
            """INSERT INTO memory_instructions(tenant_id,client_id,employee_key,workflow_key,company_id,text,
               created_by,updated_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (tenant_id, client_id, employee, workflow_key, company_id, text, actor_id, actor_id)).fetchone()
        action = "rule_created"
    else:
        row = connection.execute(
            """UPDATE memory_instructions SET text=%s,workflow_key=%s,company_id=%s,version=version+1,updated_by=%s,
               updated_at=now() WHERE tenant_id=%s AND client_id=%s AND employee_key=%s AND id=%s RETURNING *""",
            (text, workflow_key, company_id, actor_id, tenant_id, client_id, employee, instruction_id)).fetchone()
        if row is None:
            raise ServiceError("not_found", "Rule not found.")
        action = "rule_changed"
    _version(connection, row, actor_id)
    _event(connection, row, action, actor_id, {"version": row["version"]}, instruction=True)
    return row


def seed(connection, tenant_id, client_id, seeds, *, employee=EMPLOYEE):
    """Write the rules a client agreed at installation, each once: an admin's later edit or deletion stands."""
    for item in seeds:
        if connection.execute(
                """SELECT 1 FROM memory_events WHERE tenant_id=%s AND client_id=%s AND action='rule_seeded'
                   AND detail->>'seed'=%s""", (tenant_id, client_id, item["key"])).fetchone():
            continue
        row = _store(connection, tenant_id, client_id, employee=employee, text=item["text"],
                     workflow_key=item.get("workflow"), company_id=None, actor_id=None)
        _event(connection, row, "rule_seeded", None, {"seed": item["key"]}, instruction=True)


# --- the admin page ----------------------------------------------------------------

def _admin(user, member):
    if not clients.is_admin(user, member):
        raise ServiceError("forbidden", "Only workspace admins can change memory.")


def _company(connection, tenant, client, company_id):
    if company_id is None:
        return None
    row = connection.execute("SELECT id FROM companies WHERE tenant_id=%s AND client_id=%s AND id=%s",
                             (tenant["id"], client["id"], company_id)).fetchone()
    if row is None:
        raise ServiceError("invalid", "Choose one of this client's companies.")
    return row["id"]


def page(connection, tenant, user, member, slug, employee=EMPLOYEE):
    """A client's memory for one employee: entries with their evidence, and the rules people wrote."""
    client = clients.require(connection, tenant, user, member, slug)
    names = {row["id"]: row["name"] for row in clients.companies(connection, tenant, client)}
    rows = entries(connection, tenant["id"], client["id"], company_ids=list(names),
                   statuses=(*LIVE, "disabled"), employee=employee)
    labels = _labels(connection, rows)
    return {
        "can_edit": clients.is_admin(user, member),
        "entries": [{"id": str(row["id"]), "kind": row["kind"], "subject": labels.get(row["id"], row["subject"]),
                     "value": row["value"], "status": row["status"], "uses": row["uses"], "misses": row["misses"],
                     "company": names.get(row["company_id"]), "evidence": row["evidence"][-5:],
                     "updated_at": row["updated_at"].isoformat()} for row in rows],
        "rules": [{"id": str(row["id"]), "version": row["version"], "text": row["text"], "status": row["status"],
                   "workflow": row["workflow_key"], "company": names.get(row["company_id"]),
                   "company_id": str(row["company_id"]) if row["company_id"] else None,
                   "updated_at": row["updated_at"].isoformat()}
                  for row in connection.execute(
                      """SELECT * FROM memory_instructions WHERE tenant_id=%s AND client_id=%s AND employee_key=%s
                         ORDER BY created_at, id""", (tenant["id"], client["id"], employee)).fetchall()],
    }


def _labels(connection, rows):
    """A booking's subject is its supplier's GUID: shown by the ledger's name in the company's latest books."""
    labels = {}
    for row in rows:
        if row["kind"] == "booking" and row["company_id"]:
            latest = mirror.latest(connection, row["company_id"])
            found = latest and mirror.masters(connection, row["company_id"], latest["version"], guids=[row["subject"]])
            if found:
                labels[row["id"]] = found[0]["name"]
    return labels


def set_entry(connection, tenant, user, member, slug, entry_id, status, employee=EMPLOYEE):
    """Disable, enable or delete (retire) one entry; a retired entry stays only as history."""
    _admin(user, member)
    if status not in ("disabled", "confirmed", "retired"):
        raise ServiceError("invalid", "Choose disabled, confirmed or retired.")
    client = clients.require(connection, tenant, user, member, slug)
    row = connection.execute(
        """UPDATE memory_entries SET status=%s,updated_at=now(),
           confirmed_by=CASE WHEN %s='confirmed' THEN %s ELSE confirmed_by END,
           confirmed_at=CASE WHEN %s='confirmed' THEN now() ELSE confirmed_at END
           WHERE tenant_id=%s AND client_id=%s AND employee_key=%s AND id=%s AND status<>'retired' RETURNING *""",
        (status, status, user["id"], status, tenant["id"], client["id"], employee, entry_id)).fetchone()
    if row is None:
        raise ServiceError("not_found", "Memory entry not found.")
    _event(connection, row, {"disabled": "disabled", "confirmed": "enabled", "retired": "deleted"}[status], user["id"])
    return {"id": str(row["id"]), "status": row["status"]}


def write_instruction(connection, tenant, user, member, slug, *, text, workflow_key=None, company_id=None,
                      instruction_id=None, employee=EMPLOYEE):
    """Write a new rule, or a new version of one."""
    _admin(user, member)
    client = clients.require(connection, tenant, user, member, slug)
    return _store(connection, tenant["id"], client["id"], employee=employee, text=text, workflow_key=workflow_key,
                  company_id=_company(connection, tenant, client, company_id), actor_id=user["id"],
                  instruction_id=instruction_id)


def set_instruction(connection, tenant, user, member, slug, instruction_id, *, status, employee=EMPLOYEE):
    _admin(user, member)
    if status not in ("active", "disabled"):
        raise ServiceError("invalid", "Choose active or disabled.")
    client = clients.require(connection, tenant, user, member, slug)
    if status == "active":
        _room(connection, tenant["id"], client["id"], employee)
    row = connection.execute(
        """UPDATE memory_instructions SET status=%s,version=version+1,updated_by=%s,updated_at=now()
           WHERE tenant_id=%s AND client_id=%s AND employee_key=%s AND id=%s AND status<>%s RETURNING *""",
        (status, user["id"], tenant["id"], client["id"], employee, instruction_id, status)).fetchone()
    if row is not None:
        _version(connection, row, user["id"])
        _event(connection, row, f"rule_{status}", user["id"], {"version": row["version"]}, instruction=True)
    return {"id": str(instruction_id), "status": status}


def delete_instruction(connection, tenant, user, member, slug, instruction_id, employee=EMPLOYEE):
    """Delete a rule and its versions; the proposals that cited it keep the text they followed."""
    _admin(user, member)
    client = clients.require(connection, tenant, user, member, slug)
    row = connection.execute(
        """DELETE FROM memory_instructions WHERE tenant_id=%s AND client_id=%s AND employee_key=%s AND id=%s
           RETURNING *""", (tenant["id"], client["id"], employee, instruction_id)).fetchone()
    if row is None:
        raise ServiceError("not_found", "Rule not found.")
    _event(connection, row, "rule_deleted", user["id"], {"text": row["text"]}, instruction=True)
    return {"id": str(instruction_id), "status": "deleted"}
