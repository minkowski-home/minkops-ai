"""Employee memory for the Accounts desk: structured entries and plain-text rules.

Memory is runtime data, kept per client business and per employee and shared
by all of that employee's workflows. Sessions look it up only when they need
it; nothing is loaded into context up front.

- Structured entries are contract-like key-values with the evidence behind
  them and the native GUIDs they name. `practice` entries say how a company
  keeps its books, from the sync's probes or a person's one-click answer.
  `booking` entries say how a supplier's bills are booked, and `routing`
  entries how a payee's bank rows are, each learnt from saves that were
  verified and approved, or whose treatment a person chose in review.
- Every sync revalidates them: an edit made in Tally to a voucher an entry was
  learnt from demotes it, and an entry whose GUIDs are missing from three syncs
  in a row retires.
- Rules (plain-text instructions) are only ever written by people. They are
  scoped to a workflow or company, versioned, and cited by ID and version.

Only workspace admins change memory; every change records its actor in
memory_events. Callers own transactions.
"""

import hashlib
import json

from psycopg.types.json import Jsonb

from minkops_platform import clients
from minkops_platform.errors import ServiceError

from . import mirror

EMPLOYEE = "accounts-desk"
EVIDENCE_LIMIT = 20
# What lookups and checks see; a disabled or retired entry is never offered.
LIVE = ("confirmed", "demoted")
# Evidence that names the voucher an entry was learnt from: a save a person approved, one whose treatment a person
# chose in review, a voucher a person corrected in Tally, or one they entered there by hand. A later Tally edit to
# that voucher demotes the entry.
VOUCHERED = ("outcome", "choice", "tally_edit", "tally_entry")
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


# How many times the client must have booked something this way before standing approval writes it without a
# person: one earlier booking may be a one-off, two are a practice.
STANDING = 2


def payee_key(name):
    """A payee's name as an entry subject: spacing and case never make two payees."""
    return mirror.normalized(name).replace(":", " ")


def entries(connection, tenant_id, client_id, *, company_ids, kinds=None, subjects=None, statuses=LIVE,
            employee=EMPLOYEE):
    """Entries for these companies and client-wide ones, optionally of some kinds or about some subjects.

    A subject matches an entry's subject, the part of it before its treatment (a supplier's GUID, a payee's
    name), or any GUID the entry names. A payee's name also matches when one contains the other, as narrations
    print names with codes or suffixes around them.
    """
    wanted = None if subjects is None else sorted({*subjects, *(payee_key(subject) for subject in subjects)})
    return connection.execute(
        """SELECT * FROM memory_entries WHERE tenant_id=%s AND client_id=%s AND employee_key=%s
           AND (company_id IS NULL OR company_id = ANY(%s::uuid[])) AND status = ANY(%s)
           AND (%s::text[] IS NULL OR kind = ANY(%s))
           AND (%s::text[] IS NULL OR subject = ANY(%s) OR split_part(subject, ':', 1) = ANY(%s) OR guids && %s
                OR (kind = 'routing' AND EXISTS (
                    SELECT 1 FROM unnest(%s::text[]) AS name WHERE length(name) >= 4 AND length(split_part(subject, ':', 1)) >= 4
                    AND (position(name IN split_part(subject, ':', 1)) > 0
                         OR position(split_part(subject, ':', 1) IN name) > 0))))
           ORDER BY kind, subject, company_id""",
        (tenant_id, client_id, employee, list(company_ids), list(statuses), kinds, kinds, wanted, wanted, wanted,
         wanted, wanted)).fetchall()


def _treatment(guids):
    return hashlib.sha256(json.dumps(guids).encode()).hexdigest()[:16]


def approver(connection, run, record_row):
    """Who approved a record: a person's own decision on it, else the run's Write ready rows or standing approval."""
    row = connection.execute("""SELECT actor_id FROM record_decisions WHERE tenant_id=%s AND record_id=%s
                                AND action<>'nothing' ORDER BY created_at DESC LIMIT 1""",
                             (run["tenant_id"], record_row["id"])).fetchone()
    return row["actor_id"] if row else run["actor_id"]


def record(connection, *, tenant_id, client_id, company_id, kind, subject, value, evidence, guids=(),
           status, actor_id=None, employee=EMPLOYEE, overrule_answers=False, use=False):
    """Create or update the live entry for a subject with new evidence.

    An entry a person answered is never silently replaced by a derived fact;
    the new evidence is kept on it instead, unless `overrule_answers`. A
    confirmed outcome that agrees with a demoted entry confirms it: one
    approval confirms what a bill relied on. A disabled entry only gathers
    evidence until an admin enables it.
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
        confirm = entry["value"] == value and status == "confirmed" and entry["status"] == "demoted"
        updated = connection.execute(
            """UPDATE memory_entries SET evidence=%s, uses=uses+%s, updated_at=now(),
               status=CASE WHEN %s THEN 'confirmed' ELSE status END, misses=CASE WHEN %s THEN 0 ELSE misses END,
               confirmed_by=CASE WHEN %s THEN %s::uuid ELSE confirmed_by END,
               confirmed_at=CASE WHEN %s THEN now() ELSE confirmed_at END WHERE id=%s RETURNING *""",
            (Jsonb(history), int(use and entry["value"] == value), confirm, confirm, confirm, actor_id, confirm,
             entry["id"])).fetchone()
        if confirm:
            _event(connection, updated, "confirmed", actor_id)
        return updated
    updated = connection.execute(
        """UPDATE memory_entries SET value=%s,guids=%s,evidence=%s,status=%s,misses=0,uses=%s,version=version+1,
           confirmed_by=CASE WHEN %s='confirmed' THEN %s::uuid END,confirmed_at=CASE WHEN %s='confirmed' THEN now() END,
           updated_at=now() WHERE id=%s RETURNING *""",
        (Jsonb(value), list(guids), Jsonb(history), status, int(use), status, actor_id, status, entry["id"])).fetchone()
    _event(connection, updated, "changed", actor_id, {"from": entry["value"], "to": value})
    return updated


def learn_booking(connection, run, record_row, plan, voucher_guid, *, actor_id):
    """A verified save a person approved becomes one way this supplier's bills are booked.

    A booking is the treatment the approval bound (vouchers.Bill.booking): the
    voucher type, the expense ledgers and whether the bill was booked item-wise,
    not the taxes or round-off a bill happened to print. Each distinct booking
    of a supplier is its own entry, its GUIDs the supplier's, the voucher type's
    and the ledgers'. A treatment a person chose in review is evidence of kind
    `choice`, naming them.
    """
    references, party = plan["references"]["ledgers"], plan["header"]["party_ledger"]
    booking = record_row["proposal"].get("booking") or {}
    expense, items = booking.get("ledgers"), booking.get("items", False)
    guid = (references.get(party) or {}).get("GUID")
    if not guid or not expense:
        return None
    treatment = [plan["voucher_type"]["GUID"], *sorted(references[name]["GUID"] for name in expense)]
    return record(connection, tenant_id=run["tenant_id"], client_id=run["client_id"], company_id=record_row["company_id"],
                  kind="booking", subject=f"{guid}:{_treatment([*treatment, 'items'] if items else treatment)}",
                  value={"supplier": party, "voucher_type": plan["voucher_type"]["NAME"], "ledgers": expense,
                         **({"items": True} if items else {})},
                  guids=[guid, *treatment], evidence=_evidence(run, record_row, voucher_guid),
                  status="confirmed", actor_id=actor_id, use=True)


def learn_routing(connection, run, record_row, plan, voucher_guid, *, actor_id):
    """A verified bank row a person approved becomes one way rows with its payee are booked.

    The payee is the counterparty the row's narration names; the treatment is
    the counter ledger and voucher type, one entry for each way a payee's rows
    are booked. A treatment a person chose in review is evidence of kind
    `choice`, naming them.
    """
    proposal = record_row["proposal"] or {}
    payee = (proposal.get("selection") or {}).get("payee")
    counter = ((proposal.get("resolved") or {}).get("data") or {}).get("counter_ledger")
    references = plan["references"]["ledgers"]
    if not payee or counter not in references:
        return None
    treatment = [references[counter]["GUID"], plan["voucher_type"]["GUID"]]
    return record(connection, tenant_id=run["tenant_id"], client_id=run["client_id"],
                  company_id=record_row["company_id"], kind="routing",
                  subject=f"{payee_key(payee)}:{_treatment(treatment)}",
                  value={"payee": payee, "counter_ledger": counter, "voucher_type": plan["voucher_type"]["NAME"]},
                  guids=treatment, evidence=_evidence(run, record_row, voucher_guid),
                  status="confirmed", actor_id=actor_id, use=True)


def _evidence(run, record_row, voucher_guid):
    """What a verified save teaches from: the voucher, and who chose its treatment when a person did."""
    chosen = (record_row["proposal"] or {}).get("chosen")
    return {"kind": "choice" if chosen else "outcome", "voucher": voucher_guid, "run": str(run["id"]),
            "record": str(record_row["id"]), **({"actor": chosen["by"]} if chosen else {})}


def revalidate(connection, company, version):
    """After a sync: an edit made in Tally to a voucher an entry was learnt from demotes it, and an entry whose
    GUIDs are missing from three syncs in a row retires.

    The edit also teaches, once per alteration, how the voucher is booked now (`_corrected`): a person who
    corrects Minkops's save in Tally has shown the treatment. A deleted or cancelled voucher only demotes.
    """
    rows = connection.execute(
        "SELECT * FROM memory_entries WHERE company_id=%s AND status = ANY(%s) FOR UPDATE",
        (company["id"], list(LIVE))).fetchall()
    if not rows:
        return
    named = sorted({guid for row in rows for guid in row["guids"]})
    names = {row["guid"]: row["name"] for row in mirror.masters(connection, company["id"], version["version"],
                                                                 guids=named)}
    learnt = sorted({item["voucher"] for row in rows if row["kind"] in LEDGERS for item in row["evidence"]
                     if item.get("kind") in VOUCHERED and item.get("voucher")})
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
        edited = vouchers.get((changed or {}).get("voucher"))
        if edited is not None and not edited["cancelled"]:
            _corrected(connection, company, version["version"], entry, edited)


# Where each kind of entry lists the ledgers its vouchers must still post to, by GUID.
LEDGERS = {"booking": slice(2, None), "routing": slice(0, 1)}


def _rebooked(entry, vouchers, names):
    """How a voucher this entry was learnt from now differs in Tally, or None when none does: deleted or cancelled,
    posted to other ledgers, or, for a booking, moved to another supplier.

    Entries name their ledgers by GUID, so a ledger renamed in Tally is still the
    same treatment.
    """
    if entry["kind"] not in LEDGERS:
        return None
    ledgers = entry["guids"][LEDGERS[entry["kind"]]]
    wanted = {names.get(guid) for guid in ledgers} if all(guid in names for guid in ledgers) else (
        set(entry["value"].get("ledgers") or [entry["value"].get("counter_ledger")]))
    for item in entry["evidence"]:
        if item.get("kind") not in VOUCHERED or not item.get("voucher"):
            continue
        voucher = vouchers.get(item["voucher"])
        if voucher is None or voucher["cancelled"]:
            return {"voucher": item["voucher"], "now": "deleted or cancelled"}
        if not wanted <= set(voucher["ledgers"]):
            return {"voucher": item["voucher"], "now": sorted(voucher["ledgers"])}
        # Moved to another supplier: Tally names another party, and the voucher no longer posts to this one.
        supplier = names.get(entry["guids"][0]) if entry["kind"] == "booking" else None
        if supplier and voucher["party_ledger"] and mirror.normalized(supplier) != mirror.normalized(
                voucher["party_ledger"]) and supplier not in voucher["ledgers"]:
            return {"voucher": item["voucher"], "now": {"supplier": voucher["party_ledger"]}}
    return None


# Words that name a round-off ledger, which a bill's treatment leaves out with its taxes.
ROUNDING = {"round", "rounding", "roundoff"}


def treatment(connection, company, version, voucher, *, payee=None):
    """How a voucher in the books is booked, as an entry keeps it: {kind, subject, value, guids}; None when the
    books do not settle it.

    With `payee`, a bank row's routing: its other side (the voucher's ledgers less its bank and cash ones, which must
    leave exactly one) and its voucher type. Otherwise a bill's booking: its supplier, voucher type and expense heads
    (the ledgers under purchase, expense and asset groups, less a round-off), item-wise when it carries stock.
    """
    found = {mirror.normalized(row["name"]): row for row in mirror.named(
        connection, company["id"], version, "LEDGER", list(voucher["ledgers"]))}
    types = mirror.named(connection, company["id"], version, "VOUCHERTYPE", [voucher["voucher_type"]])
    if len(types) != 1 or len(found) != len(voucher["ledgers"]):
        return None
    kind = types[0]
    groups = {row["name_key"]: row["parent"] for row in mirror.masters(connection, company["id"], version,
                                                                      types=["GROUP"])}
    if payee is not None:
        others = [row for row in found.values() if not mirror.under(row["parent"], ("Bank Accounts", "Cash-in-Hand"),
                                                                     groups)]
        if len(others) != 1 or len(payee_key(payee)) < 4:
            return None
        guids = [others[0]["guid"], kind["guid"]]
        return {"kind": "routing", "subject": f"{payee_key(payee)}:{_treatment(guids)}", "guids": guids,
                "value": {"payee": payee, "counter_ledger": others[0]["name"], "voucher_type": kind["name"]}}
    party = found.get(mirror.normalized(voucher["party_ledger"]))
    expense = sorted((row for row in found.values() if row is not party
                      and mirror.under(row["parent"], mirror.EXPENSE_GROUPS, groups)
                      and not ROUNDING & set(mirror.words(row["name"]))), key=lambda row: row["name"])
    if party is None or not expense:
        return None
    items = bool(mirror.stock_lines(voucher["data"]))
    booked = [kind["guid"], *sorted(row["guid"] for row in expense)]
    return {"kind": "booking", "subject": f"{party['guid']}:{_treatment([*booked, 'items'] if items else booked)}",
            "guids": [party["guid"], *booked],
            "value": {"supplier": party["name"], "voucher_type": kind["name"],
                      "ledgers": [row["name"] for row in expense], **({"items": True} if items else {})}}


def learn_treatment(connection, company, found, evidence, *, actor_id=None):
    """A treatment the books show (`treatment`), confirmed with the voucher that shows it as evidence."""
    return record(connection, tenant_id=company["tenant_id"], client_id=company["client_id"],
                  company_id=company["id"], kind=found["kind"], subject=found["subject"], value=found["value"],
                  guids=found["guids"], evidence=evidence, status="confirmed", actor_id=actor_id, use=True)


def taught(connection, company, voucher, *, edit=False):
    """Whether a voucher already taught the client's memory: any evidence naming it, so one voucher never counts twice;
    for an `edit`, this alteration of it."""
    named = {"kind": "tally_edit", "voucher": voucher["guid"], "alter_id": voucher["alter_id"]} if edit else {
        "voucher": voucher["guid"]}
    return connection.execute(
        "SELECT 1 FROM memory_entries WHERE tenant_id=%s AND client_id=%s AND evidence @> %s LIMIT 1",
        (company["tenant_id"], company["client_id"], Jsonb([named]))).fetchone() is not None


def _corrected(connection, company, version, entry, voucher):
    """A voucher an entry was learnt from, edited in Tally: once per alteration, its treatment now is learnt.

    A bill whose supplier changed teaches what its printed supplier name stands for instead (`recognise`), from
    the bill the entry was learnt from; its booking under the other supplier is not this supplier's.
    """
    if taught(connection, company, voucher, edit=True):
        return
    evidence = {"kind": "tally_edit", "voucher": voucher["guid"], "alter_id": voucher["alter_id"]}
    if entry["kind"] == "routing":
        found = treatment(connection, company, version, voucher, payee=entry["value"]["payee"])
        if found:
            learn_treatment(connection, company, found, evidence)
        return
    party = mirror.named(connection, company["id"], version, "LEDGER", [voucher["party_ledger"]])
    if len(party) == 1 and party[0]["guid"] != entry["guids"][0]:
        source = next((item for item in reversed(entry["evidence"]) if item.get("record")), None)
        row = source and connection.execute("SELECT proposal FROM run_records WHERE tenant_id=%s AND id=%s",
                                            (company["tenant_id"], source["record"])).fetchone()
        printed = printed_supplier(((row or {}).get("proposal") or {}).get("bill") or {})
        if printed:
            recognise(connection, company, name=printed["name"], gstin=printed["gstin"], ledger=party[0],
                      evidence=evidence)
        return
    found = treatment(connection, company, version, voucher)
    if found:
        learn_treatment(connection, company, found, evidence)


# --- supplier recognition -------------------------------------------------------------

def printed_supplier(bill):
    """The supplier's name and GSTIN as a bill prints them, when its session quoted the name in its own evidence;
    None otherwise. Only such a name is learnt as a supplier's: a session's paraphrase never is."""
    document = bill.get("document") or {}
    name = (document.get("supplier_name") or "").strip()
    quoted = [item.get("quote") or "" for item in bill.get("evidence") or [] if item.get("field") == "supplier_name"]
    if not name or not any(mirror.normalized(name) in mirror.normalized(quote) for quote in quoted):
        return None
    return {"name": name, "gstin": (document.get("supplier_gstin") or "").strip().upper() or None}


def recognise(connection, company, *, name, gstin, ledger, evidence, actor_id=None):
    """The supplier ledger a printed name stands for in a company (`supplier_name`), which find_ledger lists first.

    `ledger` is the ledger's mirror row. A printed GSTIN the ledger does not hold is a conflict, and nothing is
    learnt. A different ledger for a name already learnt demotes that entry instead of replacing it; choosing a
    ledger again for a demoted name confirms that one. Recognition finds a supplier; it never books a bill.
    """
    held = {value for value in [ledger.get("gstin")] if value}
    subject = payee_key(name)
    if len(subject) < 3 or (gstin and held and gstin not in held):
        return None
    entry = live(connection, company["tenant_id"], company["client_id"], company_id=company["id"],
                 kind="supplier_name", subject=subject)
    if entry and entry["status"] == "confirmed" and entry["guids"] != [ledger["guid"]]:
        connection.execute("UPDATE memory_entries SET status='demoted',updated_at=now() WHERE id=%s", (entry["id"],))
        _event(connection, entry, "demoted", actor_id, {"other": ledger["name"]})
        return None
    return record(connection, tenant_id=company["tenant_id"], client_id=company["client_id"], company_id=company["id"],
                  kind="supplier_name", subject=subject, value={"name": name, "ledger": ledger["name"]},
                  guids=[ledger["guid"]], evidence={**evidence, **({"gstin": gstin} if gstin else {})},
                  status="confirmed", actor_id=actor_id)


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
    """A booking names its supplier by GUID first: shown by the ledger's name in the company's latest books."""
    labels = {}
    for row in rows:
        if row["kind"] == "routing":
            labels[row["id"]] = row["value"]["payee"]
        elif row["kind"] == "booking" and row["company_id"] and row["guids"]:
            latest = mirror.latest(connection, row["company_id"])
            found = latest and mirror.masters(connection, row["company_id"], latest["version"], guids=row["guids"][:1])
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
