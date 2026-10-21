"""The Accounts lookup tools: read-only views of a client's books at a run's pins.

A run pins one mirror version per authorised company of its client business.
Every tool reads only those companies at those versions, takes a list of
subjects, and answers compactly with names, GUIDs and the facts a proposal
needs, never whole native records. Workflow tools, such as a statement's
`propose`, build on the same Desk.
"""

from minkops_platform.runtime.tools import Tool, ToolError

from . import mirror
from .voucher_types import base_types

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
        self.companies = {row["guid"]: {**row, "version": run["pins"][str(row["id"])]} for row in rows}
        self._groups, self._types, self._views = {}, {}, {}

    def company(self, guid):
        found = self.companies.get(guid)
        if found is None:
            raise ToolError(f"Company {guid} is not one of this client's companies; use find_company.")
        return found

    def view(self, connection, company):
        """The company in the shape validated_plan reads, built once per item."""
        if company["guid"] not in self._views:
            view = mirror.company_view(connection, company, company["version"])
            self._views[company["guid"]] = {**view, "port": company["tally_port"]}
        return self._views[company["guid"]]

    def path(self, connection, company, parent):
        """A master's group chain, nearest first: "Sundry Creditors < Current Liabilities"."""
        if company["guid"] not in self._groups:
            self._groups[company["guid"]] = {
                row["name_key"]: row["parent"] for row in mirror.masters(connection, company["id"], company["version"],
                                                                         types=["GROUP"])}
        groups, chain = self._groups[company["guid"]], []
        while parent and len(chain) < 12 and parent not in chain:
            chain.append(parent)
            parent = groups.get(mirror.normalized(parent))
        return " < ".join(chain)

    def voucher_types(self, connection, company):
        if company["guid"] not in self._types:
            rows = mirror.masters(connection, company["id"], company["version"], types=["VOUCHERTYPE"])
            bases = base_types([row["data"] for row in rows])
            self._types[company["guid"]] = [
                {"name": row["name"], "guid": row["guid"], "family": mirror.normalized(bases.get(row["name"].casefold())),
                 "active": mirror.text(row["data"].get("ISACTIVE")).casefold() != "no"} for row in rows]
        return self._types[company["guid"]]

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
    for company in desk.companies.values():
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
