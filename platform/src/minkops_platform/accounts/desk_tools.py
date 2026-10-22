"""The Accounts desk: a run's scope over the client's books, and the lookups that read it.

A run serves one client business. Its launch asks every PC holding the
client's authorised companies to refresh its Tally copy, and its sessions wait
for those refreshes, then pin one mirror version per company (`ready`). Every
tool reads only those companies at those versions, takes a list of subjects,
and answers compactly with names, GUIDs and the facts a proposal needs, never
whole native records. Workflow tools, such as a statement's `propose`, build
on the same Desk.
"""

import json
from datetime import timedelta

from minkops_platform import clients
from minkops_platform.errors import ServiceError
from minkops_platform.lanes import Wait
from minkops_platform.runtime.tools import Tool, ToolError

from . import memory, mirror, settlement, sync
from .voucher_types import base_types
from .vouchers import HoldReason


def prepare(connection, tenant, user, client):
    """The client's authorised companies, after asking each PC that holds them to refresh its Tally copy."""
    companies = clients.companies(connection, tenant, client)
    if not companies:
        raise ServiceError("conflict", "Authorise this client's Tally companies before entering its work.")
    wanted = {c["device_id"] for c in companies}
    devices = connection.execute(
        "SELECT * FROM desktop_devices WHERE id = ANY(%s) AND revoked_at IS NULL AND expires_at > now() ORDER BY id",
        (list(wanted),)).fetchall()
    if len(devices) != len(wanted):
        raise ServiceError("conflict", "A PC holding this client's companies is no longer connected.")
    for device in devices:
        sync.queue(connection, device, user["id"], reason="run")
    return companies, devices


def refreshing(connection, client_id, *, since=None):
    """The blocker of a refresh still running for one of the client's PCs, or None."""
    pending = connection.execute(
        """SELECT j.device_id FROM desktop_jobs j JOIN companies c ON c.device_id=j.device_id
           WHERE c.client_id=%s AND c.status='authorised' AND j.operation='tally.sync'
               AND j.state IN ('queued','executing') AND (%s::timestamptz IS NULL OR j.created_at <= %s)
           ORDER BY j.device_id LIMIT 1""", (client_id, since, since)).fetchone()
    return sync.blocker(pending["device_id"]) if pending else None


def ready(connection, run):
    """Pin the client's mirrors once every PC it uses has refreshed; until then, wait on the next one."""
    blocker = refreshing(connection, run["client_id"], since=run["created_at"])
    if blocker:
        raise Wait(blocker)
    run = connection.execute("SELECT * FROM runs WHERE id=%s FOR UPDATE", (run["id"],)).fetchone()
    if not run["pins"]:
        ids = [c["id"] for c in connection.execute(
            "SELECT id FROM companies WHERE tenant_id=%s AND client_id=%s AND status='authorised'",
            (run["tenant_id"], run["client_id"])).fetchall()]
        pins = mirror.pins(connection, ids)
        if not pins:
            # No copy was ever published: wait for the PC's next refresh to finish.
            device = connection.execute("SELECT device_id FROM companies WHERE id = ANY(%s) ORDER BY device_id LIMIT 1",
                                        (ids,)).fetchone()
            raise Wait(sync.blocker(device["device_id"]))
        run = connection.execute("UPDATE runs SET pins=%s,updated_at=now() WHERE id=%s RETURNING *",
                                 (json.dumps(pins), run["id"])).fetchone()
    return run


def bundle(connection, run):
    """The run's pinned workflow bundle: model, reasoning effort and instructions."""
    return connection.execute("SELECT content FROM run_bundles WHERE tenant_id=%s AND digest=%s",
                              (run["tenant_id"], run["bundle_digest"])).fetchone()["content"]


def reasoning(pinned):
    return {"effort": pinned["reasoning_effort"]} if pinned.get("reasoning_effort") else None

SUBJECTS = {"type": "array", "minItems": 1, "maxItems": 20,
            "items": {"type": "string", "minLength": 1, "maxLength": 200}}
COMPANY = {"type": "string", "minLength": 1, "maxLength": 100, "description": "The company's GUID."}
FAMILIES = ("payment", "receipt", "contra", "purchase", "journal", "debit note", "credit note", "sales")
# The oldest open bills listed per ledger; the rest are counted.
OPEN_BILLS = 50


class Desk:
    """One item's scope: the run's companies at their pinned versions, with per-company caches."""

    def __init__(self, connection, run):
        rows = connection.execute(
            """SELECT c.*, d.tally_port FROM companies c JOIN desktop_devices d ON d.tenant_id=c.tenant_id AND d.id=c.device_id
               WHERE c.tenant_id=%s AND c.client_id=%s AND c.status='authorised' AND c.id = ANY(%s::uuid[])
               ORDER BY c.name""",
            (run["tenant_id"], run["client_id"], list(run["pins"]))).fetchall()
        self.run = run
        # A company split by year keeps its GUID: each part is told apart by when its books begin.
        self.parts = {}
        for row in rows:
            self.parts.setdefault(row["guid"], []).append({**row, "version": run["pins"][str(row["id"])]})
        for parts in self.parts.values():
            parts.sort(key=lambda part: part["books_from"])
        self.companies = {guid: parts[-1] for guid, parts in self.parts.items()}
        self._groups, self._types, self._views, self._billwise, self._rules = {}, {}, {}, {}, None

    def company(self, guid, on=None):
        """The company with this GUID; for a year split, the part whose books cover `on` (ISO date)."""
        parts = self.parts.get(guid)
        if not parts:
            raise ToolError(f"Company {guid} is not one of this client's companies; use find_company.")
        if on is None:
            return parts[-1]
        covering = [part for part in parts if part["books_from"].isoformat() <= on]
        return covering[-1] if covering else parts[0]

    def part_ids(self, company=None):
        """Every part of one company (its year-split siblings share what memory learnt), or of all of them."""
        groups = [self.parts[company["guid"]]] if company else self.parts.values()
        return [part["id"] for parts in groups for part in parts]

    def rules(self, connection):
        """The client's active rules for this run's workflow and companies, read once per item."""
        if self._rules is None:
            self._rules = memory.instructions(connection, self.run["tenant_id"], self.run["client_id"],
                                              workflow_key=self.run["workflow_key"], company_ids=self.part_ids())
        return self._rules

    def cite(self, connection, ids):
        """The rules a proposal follows, as {id, version, text}; citing anything else is refused."""
        known = {str(rule["id"]): rule for rule in self.rules(connection)}
        for rule_id in ids:
            if rule_id not in known:
                raise HoldReason("classification_uncertain", (
                    f"Rule {rule_id} is not one of this client's active rules for this workflow. Cite only rules "
                    "the rules lookup returns."))
        return [{"id": rule_id, "version": known[rule_id]["version"], "text": known[rule_id]["text"]}
                for rule_id in dict.fromkeys(ids)]

    def until(self, company):
        """The last day this part's books cover before a later part of the same company begins, or None."""
        later = [part for part in self.parts[company["guid"]] if part["books_from"] > company["books_from"]]
        return (later[0]["books_from"] - timedelta(days=1)).isoformat() if later else None

    def view(self, connection, company):
        """The company in the shape the voucher gates read, built once per item."""
        if company["id"] not in self._views:
            view = mirror.company_view(connection, company, company["version"])
            self._views[company["id"]] = {**view, "port": company["tally_port"],
                                          "books_from": company["books_from"].isoformat()}
        return self._views[company["id"]]

    def billwise(self, connection, company):
        """The names of the company's ledgers that keep bill-by-bill balances."""
        if company["id"] not in self._billwise:
            self._billwise[company["id"]] = {
                mirror.text(r["data"].get("@_NAME")) or mirror.text(r["data"].get("NAME"))
                for r in self.view(connection, company)["masters"]["records"]
                if r["type"] == "LEDGER" and mirror.text(r["data"].get("ISBILLWISEON")).casefold() == "yes"}
        return self._billwise[company["id"]]

    def path(self, connection, company, parent):
        """A master's group chain, nearest first: "Sundry Creditors < Current Liabilities"."""
        if company["id"] not in self._groups:
            self._groups[company["id"]] = {
                row["name_key"]: row["parent"] for row in mirror.masters(connection, company["id"], company["version"],
                                                                         types=["GROUP"])}
        groups, chain = self._groups[company["id"]], []
        while parent and len(chain) < 12 and parent not in chain:
            chain.append(parent)
            parent = groups.get(mirror.normalized(parent))
        return " < ".join(chain)

    def voucher_types(self, connection, company):
        if company["id"] not in self._types:
            rows = mirror.masters(connection, company["id"], company["version"], types=["VOUCHERTYPE"])
            bases = base_types([row["data"] for row in rows])
            self._types[company["id"]] = [
                {"name": row["name"], "guid": row["guid"], "family": mirror.normalized(bases.get(row["name"].casefold())),
                 "active": mirror.text(row["data"].get("ISACTIVE")).casefold() != "no"} for row in rows]
        return self._types[company["id"]]

    def ledger(self, connection, company, row):
        data = row["data"]
        yes = lambda field: mirror.text(data.get(field)).casefold() == "yes"  # noqa: E731
        # A ledger's description is the client's own note on what it records.
        return {key: value for key, value in {
            "name": row["name"], "guid": row["guid"], "group": self.path(connection, company, row["parent"]),
            "aliases": row["aliases"] or None, "gstin": row["gstin"],
            "bank_account_ends": row["bank_account"][-4:] if row["bank_account"] else None, "ifsc": row["ifsc"],
            "cost_centres": yes("ISCOSTCENTRESON") or None, "bill_by_bill": yes("ISBILLWISEON") or None,
            "description": mirror.text(data.get("DESCRIPTION"))[:300] or None,
        }.items() if value is not None}


def entries(data):
    """A voucher's ledger lines as {ledger, debit|credit} in rupees."""
    return [{"ledger": ledger, ("debit" if cents < 0 else "credit"): f"{abs(cents) / 100:.2f}"}
            for ledger, cents in mirror.ledger_lines(data)]


def items(data):
    """A voucher's first stock lines, when it was booked item-wise: item, billed quantity, amount and ledgers."""
    return [{key: value for key, value in {
        "item": item, "quantity": quantity or None, "amount": None if cents is None else f"{abs(cents) / 100:.2f}",
        "ledgers": ledgers or None}.items() if value is not None}
        for item, quantity, cents, ledgers in mirror.stock_lines(data)[:5]]


def voucher(row):
    return {key: value for key, value in {
        "date": row["date"].isoformat(), "type": row["voucher_type"], "number": row["number"] or None,
        "reference": row["reference"] or None, "narration": row["narration"][:200] or None,
        "entries": entries(row["data"]), "items": items(row["data"]) or None}.items() if value is not None}


def find_company(call, arguments):
    desk, subjects = call.state, arguments.get("subjects") or []
    out = []
    for company in (part for parts in desk.parts.values() for part in parts):
        gstins = sorted({row["gstin"] for row in mirror.masters(call.connection, company["id"], company["version"],
                                                                 types=["TAXUNIT", "COMPANY"]) if row["gstin"]})
        named = mirror.normalized(company["name"])
        matches = [s for s in subjects if s.strip().upper() in gstins
                   or all(word in named for word in mirror.normalized(s).split())]
        out.append({"guid": company["guid"], "name": company["name"], "books_from": company["books_from"].isoformat(),
                    "gstins": gstins, **({"matches": matches} if subjects else {})})
    return {"companies": out}


def find_ledger(call, arguments):
    """Without a company, every company in scope is searched: which one owns this bank account or supplier."""
    desk = call.state
    scope = [desk.company(arguments["company"])] if arguments.get("company") else list(desk.companies.values())
    results = []
    for subject in arguments["subjects"]:
        ledgers = []
        for company in scope:
            for row in mirror.search_masters(call.connection, company["id"], company["version"], ["LEDGER"], subject):
                found = desk.ledger(call.connection, company, row)
                ledgers.append(found if arguments.get("company") else {**found, "company": company["name"],
                                                                        "company_guid": company["guid"]})
        results.append({"subject": subject, "ledgers": ledgers})
    return {"results": results}


def voucher_types(call, arguments):
    desk = call.state
    company, families = desk.company(arguments["company"]), set(arguments["families"])
    return {"voucher_types": [{"name": t["name"], "guid": t["guid"], "family": t["family"]}
                              for t in desk.voucher_types(call.connection, company)
                              if t["active"] and t["family"] in families]}


def party_history(call, arguments):
    """Ledgers are named by GUID, as find_ledger gives them, or by name; one that is no ledger is reported."""
    desk = call.state
    company = desk.company(arguments["company"])
    subjects = arguments["ledgers"]
    found = mirror.named(call.connection, company["id"], company["version"], "LEDGER", subjects)
    known = {row["guid"] for row in found} | {row["name_key"] for row in found}
    unknown = [s for s in subjects if s not in known and mirror.normalized(s) not in known]
    rows = mirror.ledger_history(call.connection, company["id"], company["version"], [row["name"] for row in found],
                                 limit=arguments.get("limit", 8)) if found else []
    return {"vouchers": [voucher(row) for row in rows], **({"unknown_ledgers": unknown} if unknown else {})}


def open_bills(call, arguments):
    """Each ledger's open bills, as party_history names ledgers; one that keeps no bills says so."""
    desk = call.state
    company = desk.company(arguments["company"])
    found = mirror.named(call.connection, company["id"], company["version"], "LEDGER", arguments["ledgers"])
    known = {row["guid"] for row in found} | {row["name_key"] for row in found}
    unknown = [s for s in arguments["ledgers"] if s not in known and mirror.normalized(s) not in known]
    results = []
    for row in found:
        if row["name"] not in desk.billwise(call.connection, company):
            results.append({"ledger": row["name"], "bill_by_bill": False})
            continue
        bills = settlement.open_bills(call.connection, desk.run, company, row["name"])
        results.append({"ledger": row["name"], "bill_by_bill": True, "bills": [{key: value for key, value in {
            "name": bill["name"], "date": bill["date"].isoformat(), "open": f"{abs(bill['balance_cents']) / 100:.2f}",
            "balance": "credit" if bill["balance_cents"] > 0 else "debit", "advance": bill["advance"] or None,
        }.items() if value is not None} for bill in bills[:OPEN_BILLS]],
            **({"more": len(bills) - OPEN_BILLS} if len(bills) > OPEN_BILLS else {})})
    return {"ledgers": results, **({"unknown_ledgers": unknown} if unknown else {})}


def remembered(call, arguments):
    desk = call.state
    company = desk.company(arguments["company"])
    rows = memory.entries(call.connection, desk.run["tenant_id"], desk.run["client_id"],
                          company_ids=desk.part_ids(company), kinds=arguments.get("kinds"),
                          subjects=arguments["subjects"])
    return {"entries": [{"kind": row["kind"], "subject": row["subject"], "value": row["value"], "status": row["status"],
                         "uses": row["uses"]} for row in rows]}


def rules(call, arguments):
    """Every active rule in scope: their text alone cannot say which matter, so none is filtered out."""
    desk = call.state
    names = {part["id"]: part["name"] for parts in desk.parts.values() for part in parts}
    return {"rules": [{"id": str(rule["id"]), "version": rule["version"], "text": rule["text"],
                       **({"company": names[rule["company_id"]]} if rule["company_id"] else {})}
                      for rule in desk.rules(call.connection)]}


def practice(call, arguments):
    desk = call.state
    parts = desk.part_ids(desk.company(arguments["company"]))
    rows = memory.entries(call.connection, desk.run["tenant_id"], desk.run["client_id"], company_ids=parts,
                          kinds=["practice"], statuses=("confirmed",))
    questions = call.connection.execute(
        "SELECT probe, prompt FROM practice_questions WHERE company_id = ANY(%s) AND status='open' ORDER BY probe",
        (parts,)).fetchall()
    return {"practices": [{"subject": row["subject"], "value": row["value"], "settled_by": "answer" if any(
                item.get("kind") == "answer" for item in row["evidence"]) else "books"} for row in rows],
            "open_questions": [{"subject": row["probe"], "prompt": row["prompt"]} for row in questions]}


def cost_centres(call, arguments):
    desk = call.state
    company = desk.company(arguments["company"])
    return {"results": [
        {"subject": subject, "cost_centres": [
            {"name": row["name"], "guid": row["guid"], "category": mirror.text(row["data"].get("CATEGORY")) or None}
            for row in mirror.search_masters(call.connection, company["id"], company["version"], ["COSTCENTRE"],
                                             subject)]}
        for subject in arguments["subjects"]]}


def schema(properties, required):
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


TOOLS = {tool.name: tool for tool in (
    Tool("find_company", "The client's companies in scope, with their GSTINs. Subjects (names or GSTINs) are "
         "marked where they match.", schema({"subjects": {**SUBJECTS, "minItems": 0}}, []), find_company),
    Tool("find_ledger", "Ledgers matching each subject: a name or alias (every word must appear), a GSTIN, or a bank "
         "account number; a masked number matches by its last digits. Give a company to search only it; without one, "
         "every company is searched and each ledger names its company.",
         schema({"company": COMPANY, "subjects": SUBJECTS}, ["subjects"]), find_ledger),
    Tool("voucher_types", "A company's active voucher types of the given families.",
         schema({"company": COMPANY, "families": {"type": "array", "minItems": 1, "uniqueItems": True,
                                                  "items": {"enum": list(FAMILIES)}}},
                ["company", "families"]), voucher_types),
    Tool("party_history", "The newest vouchers posting to any of these ledgers in a company, cancelled ones excluded: "
         "how the client booked such transactions before, with the stock items of any booked item-wise. Give ledger "
         "GUIDs as find_ledger returns them, or exact ledger names.",
         schema({"company": COMPANY, "ledgers": SUBJECTS, "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                ["company", "ledgers"]), party_history),
    Tool("open_bills", "The open bills of ledgers that keep bill-by-bill balances, oldest first, less what this "
         "run's other rows already settle. A credit balance is owed to the party, and a payment settles it; a debit "
         "balance is owed by the party or was paid ahead, and a receipt settles it. Give ledger GUIDs or exact names.",
         schema({"company": COMPANY, "ledgers": {**SUBJECTS, "maxItems": 5}}, ["company", "ledgers"]), open_bills),
    Tool("cost_centres", "Cost centres of a company matching each subject, with their categories.",
         schema({"company": COMPANY, "subjects": SUBJECTS}, ["company", "subjects"]), cost_centres),
    Tool("memory", "What Minkops learnt about these subjects in a company, from saves a person approved: how a "
         "supplier's bills were booked (subject: the supplier ledger's GUID), how a payee's bank rows were booked "
         "(subject: the payee's name), and how the company keeps its books (subject: a practice name). A demoted "
         "entry was changed in Tally since it was learnt; an unconfirmed one was a best guess.",
         schema({"company": COMPANY, "subjects": SUBJECTS, "kinds": {
             "type": "array", "minItems": 1, "uniqueItems": True, "items": {"enum": ["booking", "routing", "practice"]}}},
             ["company", "subjects"]), remembered),
    Tool("rules", "Every rule people wrote for this client's work in this workflow, each with its ID and version. "
         "Read them before choosing treatment; a proposal that follows a rule cites its ID.", schema({}, []), rules),
    Tool("practice", "How a company keeps its books, as its history or a person's answer settled it, and the "
         "practice questions still open.", schema({"company": COMPANY}, ["company"]), practice),
)}
