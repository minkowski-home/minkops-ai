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

from . import mirror, sync
from .voucher_types import base_types


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
        self._groups, self._types, self._views = {}, {}, {}

    def company(self, guid, on=None):
        """The company with this GUID; for a year split, the part whose books cover `on` (ISO date)."""
        parts = self.parts.get(guid)
        if not parts:
            raise ToolError(f"Company {guid} is not one of this client's companies; use find_company.")
        if on is None:
            return parts[-1]
        covering = [part for part in parts if part["books_from"].isoformat() <= on]
        return covering[-1] if covering else parts[0]

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
        return {key: value for key, value in {
            "name": row["name"], "guid": row["guid"], "group": self.path(connection, company, row["parent"]),
            "aliases": row["aliases"] or None, "gstin": row["gstin"],
            "bank_account_ends": row["bank_account"][-4:] if row["bank_account"] else None, "ifsc": row["ifsc"],
            "cost_centres": yes("ISCOSTCENTRESON") or None, "bill_by_bill": yes("ISBILLWISEON") or None,
        }.items() if value is not None}


def entries(data):
    """A voucher's ledger lines as {ledger, debit|credit} in rupees."""
    return [{"ledger": ledger, ("debit" if cents < 0 else "credit"): f"{abs(cents) / 100:.2f}"}
            for ledger, cents in mirror.ledger_lines(data)]


def voucher(row):
    return {key: value for key, value in {
        "date": row["date"].isoformat(), "type": row["voucher_type"], "number": row["number"] or None,
        "reference": row["reference"] or None, "narration": row["narration"][:200] or None,
        "entries": entries(row["data"])}.items() if value is not None}


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
    desk = call.state
    company = desk.company(arguments["company"])
    rows = mirror.ledger_history(call.connection, company["id"], company["version"], arguments["ledgers"],
                                 limit=arguments.get("limit", 8))
    return {"vouchers": [voucher(row) for row in rows]}


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
         "how the client booked such transactions before.",
         schema({"company": COMPANY, "ledgers": SUBJECTS, "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                ["company", "ledgers"]), party_history),
    Tool("cost_centres", "Cost centres of a company matching each subject, with their categories.",
         schema({"company": COMPANY, "subjects": SUBJECTS}, ["company", "subjects"]), cost_centres),
)}
