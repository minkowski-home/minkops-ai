"""The Accounts desk: a run's scope over the client's books, and the lookups that read it.

A run serves one client business. Its launch asks every PC holding the
client's authorised companies to refresh its Tally copy, and its sessions wait
for those refreshes, then pin one mirror version per company (`ready`). Every
tool reads only those companies at those versions, takes a list of subjects,
and answers compactly with names, references and the facts a proposal needs,
never whole native records. Workflow tools, such as a statement's `propose`,
build on the same Desk.

Companies and masters reach a session, and come back from it, as short
references its lookups issue: C1 for a company, L12 for a ledger. Each names
one company or master for the whole item (migration 0031), and a proposal may
cite only references its item was given. Tally numbers a company's masters in
sequence, so a GUID a session guessed or mistyped could name another real
master; a reference no lookup issued names none.
"""

import json
import re
from datetime import UTC, datetime, timedelta

from minkops_platform import attention, clients
from minkops_platform.errors import ServiceError
from minkops_platform.lanes import Wait
from minkops_platform.runtime.tools import Tool, ToolError

from . import memory, mirror, settlement, sync
from . import practice as practices
from .voucher_types import base_types
from .vouchers import HoldReason


def unavailable(connection, tenant_id, client_id):
    """The client's authorised companies on a PC that was disconnected, most recently disconnected first.

    Their books wait for the PC that holds them now to continue them (docs/accounts-desk.md, Replacing a PC), so a
    run cannot enter work addressed to them. Each row names its PC (`device_name`).
    """
    return connection.execute(
        """SELECT c.*, d.name AS device_name FROM companies c
           JOIN desktop_devices d ON d.id=c.device_id AND d.revoked_at IS NOT NULL
           WHERE c.tenant_id=%s AND c.client_id=%s AND c.status='authorised' ORDER BY d.revoked_at DESC, c.name""",
        (tenant_id, client_id)).fetchall()


def prepare(connection, tenant, user, client):
    """The client's authorised companies, after asking each PC that holds them to refresh its Tally copy.

    A run starts with the books that are available; note_unavailable() names the rest once it exists.
    """
    companies = clients.companies(connection, tenant, client)
    if not companies:
        left = unavailable(connection, tenant["id"], client["id"])
        if left:
            raise ServiceError("conflict", f"{client['name']}'s books were on {left[0]['device_name']}, which was "
                                           "disconnected. Connect the PC that holds them now, then continue them from "
                                           "its \"New company found\" card in Attention.")
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


def note_unavailable(connection, run):
    """At a run's launch, one Attention item naming the client's books it cannot enter, and why; none when all are
    available. Work addressed to them holds (Desk.addressee), and is entered in a new run once they are continued."""
    left = unavailable(connection, run["tenant_id"], run["client_id"])
    if not left:
        return None
    names = ", ".join(c["name"] for c in left)
    devices = list(dict.fromkeys(c["device_name"] for c in left))
    pcs, one = ", ".join(devices), len(left) == 1
    return attention.record(connection, run, f"run:{run['id']}:unavailable", names[:200], "Books left out of this run",
                            target={"reason": (
                                f"{names} {'was' if one else 'were'} on {pcs}, which {'was' if len(devices) == 1 else 'were'} "
                                f"disconnected, so this run holds work addressed to {'it' if one else 'them'}. Connect the "
                                f"PC that holds {'it' if one else 'them'} now and continue {'it' if one else 'them'} from "
                                "its \"New company found\" card, then enter that work in a new run.")[:1000]},
                            actor=run["actor_id"])


def refreshing(connection, client_id, *, since=None, companies=None):
    """The blocker of a refresh still running for one of the client's PCs, or for the PCs holding these companies,
    or None."""
    pending = connection.execute(
        """SELECT j.device_id FROM desktop_jobs j JOIN companies c ON c.device_id=j.device_id
           JOIN desktop_devices d ON d.id=c.device_id AND d.revoked_at IS NULL
           WHERE c.client_id=%s AND c.status='authorised' AND j.operation='tally.sync'
               AND j.state IN ('queued','executing') AND (%s::timestamptz IS NULL OR j.created_at <= %s)
               AND (%s::uuid[] IS NULL OR c.id = ANY(%s::uuid[]))
           ORDER BY j.device_id LIMIT 1""", (client_id, since, since, companies, companies)).fetchone()
    return sync.blocker(pending["device_id"]) if pending else None


def ready(connection, run):
    """Pin the client's mirrors once every PC it uses has refreshed; until then, wait on the next one.

    A company a recheck asked to read again (`runs.repin`) is pinned to its newly published copy once its PC has no
    refresh left to finish, and leaves the list; until then the item waits on that PC.
    """
    blocker = refreshing(connection, run["client_id"], since=run["created_at"])
    if blocker:
        raise Wait(blocker)
    run = connection.execute("SELECT * FROM runs WHERE id=%s FOR UPDATE", (run["id"],)).fetchone()
    if not run["pins"]:
        ids = [c["id"] for c in connection.execute(
            """SELECT c.id FROM companies c JOIN desktop_devices d ON d.id=c.device_id AND d.revoked_at IS NULL
               WHERE c.tenant_id=%s AND c.client_id=%s AND c.status='authorised'""",
            (run["tenant_id"], run["client_id"])).fetchall()]
        pins = mirror.pins(connection, ids)
        if not pins:
            # No copy was ever published: wait for the PC's next refresh to finish.
            device = connection.execute("SELECT device_id FROM companies WHERE id = ANY(%s) ORDER BY device_id LIMIT 1",
                                        (ids,)).fetchone()
            raise Wait(sync.blocker(device["device_id"]))
        run = connection.execute("UPDATE runs SET pins=%s,updated_at=now() WHERE id=%s RETURNING *",
                                 (json.dumps(pins), run["id"])).fetchone()
    if run["repin"]:
        blocker = refreshing(connection, run["client_id"], companies=run["repin"])
        if blocker:
            raise Wait(blocker)
        # A company with no newer copy on the PC it is on now keeps its pin.
        fresh = mirror.pins(connection, run["repin"])
        run = connection.execute("UPDATE runs SET pins=pins || %s::jsonb, repin='{}', updated_at=now() WHERE id=%s "
                                 "RETURNING *", (json.dumps(fresh), run["id"])).fetchone()
    return run


def recheck(connection, run, actor_id, company_ids):
    """A person's Recheck: the PCs holding these companies read their books afresh, and the run's next session pins
    the copies they publish (`ready`), so a ledger created in Tally after the run read the books is found.

    Proposals already made keep their plans, and the pins they were checked against stay until then; every save is
    verified against Tally as it is. Returns the blocker the rechecked item waits on and the names of the PCs it
    waits for.
    """
    rows = connection.execute(
        """SELECT c.id AS company_id, d.* FROM companies c JOIN desktop_devices d ON d.tenant_id=c.tenant_id
               AND d.id=c.device_id
           WHERE c.tenant_id=%s AND c.client_id=%s AND c.status='authorised' AND c.id = ANY(%s::uuid[])
           ORDER BY d.id, c.id""", (run["tenant_id"], run["client_id"], list(company_ids))).fetchall()
    if not rows:
        raise ServiceError("conflict", "These books are no longer authorised for this client, so they cannot be read "
                                       "again. Start a new run.")
    devices = list({row["id"]: row for row in rows}.values())
    gone = [d["name"] for d in devices if d["revoked_at"] or d["expires_at"] <= datetime.now(UTC)]
    if gone:
        raise ServiceError("conflict", f"{gone[0]} holds these books and is no longer connected. Continue them on the "
                                       "PC that holds them now, then start a new run.")
    for device in devices:
        sync.queue(connection, device, actor_id, reason="recheck", fresh=True)
    connection.execute("UPDATE runs SET repin=ARRAY(SELECT DISTINCT unnest(repin || %s::uuid[])), updated_at=now() "
                       "WHERE id=%s", ([row["company_id"] for row in rows], run["id"]))
    return sync.blocker(devices[0]["id"]), [device["name"] for device in devices]


def waiting_note(noun, pcs):
    """What a rechecked record says while its PCs refresh: an offline PC keeps it waiting, and is named."""
    one = len(pcs) == 1
    return (f"Reading this {noun} again once {' and '.join(pcs)} {'has' if one else 'have'} refreshed "
            f"{'its' if one else 'their'} Tally copy.")


def bundle(connection, run):
    """The run's pinned workflow bundle: model, reasoning effort and instructions."""
    return connection.execute("SELECT content FROM run_bundles WHERE tenant_id=%s AND digest=%s",
                              (run["tenant_id"], run["bundle_digest"])).fetchone()["content"]


def reasoning(pinned):
    return {"effort": pinned["reasoning_effort"]} if pinned.get("reasoning_effort") else None

# A chunk's payees are looked up in one call: subjects are cheap mirror searches.
SUBJECTS = {"type": "array", "minItems": 1, "maxItems": 50,
            "items": {"type": "string", "minLength": 1, "maxLength": 200}}
# Each kind's reference prefix, and the lookup that issues it.
REFS = {"company": ("C", "find_company"), "ledger": ("L", "find_ledger"), "stock_item": ("S", "find_stock_item"),
        "godown": ("G", "godowns"), "voucher_type": ("T", "voucher_types"), "cost_centre": ("K", "cost_centres")}
NOUNS = {"stock_item": "stock item", "voucher_type": "voucher type", "cost_centre": "cost centre"}
REFERENCE = r"^[A-Z][1-9][0-9]{0,4}$"
SPOKEN = r"\b[A-Z][1-9][0-9]{0,4}\b"  # a reference as it appears in a sentence


def reference(what):
    return {"type": "string", "pattern": REFERENCE, "description": what}


COMPANY = reference("The company's reference, as the session's header or find_company gives it.")
FAMILIES = ("payment", "receipt", "contra", "purchase", "journal", "debit note", "credit note", "sales")
# The oldest open bills listed per ledger, and the godowns listed per company; the rest are counted.
OPEN_BILLS, GODOWNS = 50, 200


class Desk:
    """One item's scope: the run's companies at their pinned versions, with per-company caches.

    A session's desk (Bills, Chunk) has its `item`, to which the references its lookups issue belong.
    """

    item = None

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
        self._groups, self._types, self._views, self._billwise, self._gstins, self._rules = {}, {}, {}, {}, {}, None

    def company(self, guid, on=None):
        """The company with this GUID; for a year split, the part whose books cover `on` (ISO date)."""
        parts = self.parts.get(guid)
        if not parts:
            raise ToolError(f"Company {guid} is not one of this client's companies; use find_company.")
        if on is None:
            return parts[-1]
        covering = [part for part in parts if part["books_from"].isoformat() <= on]
        return covering[-1] if covering else parts[0]

    def issue(self, connection, kind, owner, guids):
        """This item's reference for each of these masters of the company whose GUID is `owner`, or for these
        companies when `kind` is company: {guid: ref}. New ones follow the item's last of their kind.

        References are read and written in the call's own transaction, never cached, so a call that fails
        leaves no reference the session saw but the item does not hold.
        """
        wanted = list(dict.fromkeys(guid for guid in guids if guid))
        if not wanted:
            return {}
        owners = [owner or guid for guid in wanted]  # a company is its own owner
        issued = {row["guid"]: row["ref"] for row in connection.execute(
            """SELECT r.guid, r.ref FROM item_refs r JOIN unnest(%s::text[], %s::text[]) AS w(owner, guid)
               ON r.company_guid=w.owner AND r.guid=w.guid WHERE r.item_id=%s AND r.kind=%s""",
            (owners, wanted, self.item["id"], kind)).fetchall()}
        fresh = [guid for guid in wanted if guid not in issued]
        if fresh:
            last = connection.execute(
                "SELECT coalesce(max(substring(ref FROM 2)::int), 0) AS n FROM item_refs WHERE item_id=%s AND kind=%s",
                (self.item["id"], kind)).fetchone()["n"]
            new = {guid: f"{REFS[kind][0]}{last + n}" for n, guid in enumerate(fresh, 1)}
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO item_refs (tenant_id, item_id, ref, kind, company_guid, guid) VALUES (%s,%s,%s,%s,%s,%s)",
                    [(self.item["tenant_id"], self.item["id"], ref, kind, owner or guid, guid)
                     for guid, ref in new.items()])
            issued.update(new)
        return issued

    def refer(self, connection, company):
        """A company's reference, as the session reads it."""
        return self.issue(connection, "company", None, [company["guid"]])[company["guid"]]

    def resolve(self, connection, kind, refs, company=None):
        """The GUID each reference stands for: {ref: guid}. A reference this item was not given, or one naming
        another kind of master or another company's, is refused with how to find the right one."""
        wanted = list(dict.fromkeys(ref for ref in refs if ref))
        rows = {row["ref"]: row for row in connection.execute(
            "SELECT ref, kind, company_guid, guid FROM item_refs WHERE item_id=%s AND ref = ANY(%s)",
            (self.item["id"], wanted)).fetchall()} if wanted else {}
        noun, lookup = NOUNS.get(kind, kind), REFS[kind][1]
        for ref in wanted:
            row = rows.get(ref)
            if row is None:
                raise ToolError(f"{ref} is not a reference this session was given. Look the {noun} up with {lookup}, "
                                "and use the reference it gives.")
            if row["kind"] != kind:
                raise ToolError(f"{ref} is a {NOUNS.get(row['kind'], row['kind'])}, not a {noun}.")
            if company is not None and row["company_guid"] != company["guid"]:
                raise ToolError(f"{ref} is another company's {noun}. Look it up in this company with {lookup}.")
        return {ref: rows[ref]["guid"] for ref in wanted}

    def spelled(self, connection, text):
        """Text a person reads, each reference this item was given replaced by the name it stands for: a session
        writes an exception's detail by reference, and a reviewer reads names."""
        found = set(re.findall(SPOKEN, text or ""))
        if not found or self.item is None:
            return text
        names = {}
        for row in connection.execute("SELECT ref, kind, company_guid, guid FROM item_refs WHERE item_id=%s AND ref = ANY(%s)",
                                      (self.item["id"], list(found))).fetchall():
            company = self.companies.get(row["company_guid"])
            if company is None:
                continue
            if row["kind"] == "company":
                names[row["ref"]] = company["name"]
                continue
            data = next((r["data"] for r in self.view(connection, company)["masters"]["records"]
                         if mirror.text(r["data"].get("GUID")) == row["guid"]), None)
            if data is not None:
                names[row["ref"]] = mirror.text(data.get("@_NAME")) or mirror.text(data.get("NAME"))
        return re.sub(SPOKEN, lambda match: names.get(match.group(0)) or match.group(0), text)

    def company_of(self, connection, ref, on=None):
        """The company a reference names; for a year split, the part whose books cover `on` (ISO date)."""
        return self.company(self.resolve(connection, "company", [ref])[ref], on=on)

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

    def addressee(self, connection, gstin, chosen):
        """Another of the client's companies registered under this GSTIN, or None.

        One in this run, or one whose books wait on a disconnected PC (`unavailable` set, read at its last published
        version), so a bill addressed to it is never entered into a company it only resembles. A year split's parts
        are one company.
        """
        for parts in self.parts.values():
            for part in parts:
                if part["guid"] != chosen["guid"] and gstin in self.gstins(connection, part):
                    return part
        left = unavailable(connection, self.run["tenant_id"], self.run["client_id"])
        versions = mirror.pins(connection, [c["id"] for c in left])
        for company in left:
            version = versions.get(str(company["id"]))
            if version is not None and company["guid"] != chosen["guid"] \
                    and gstin in self.gstins(connection, {**company, "version": version}):
                return {**company, "version": version, "unavailable": True}
        return None

    def until(self, company):
        """The last day this part's books cover before a later part of the same company begins, or None."""
        later = [part for part in self.parts[company["guid"]] if part["books_from"] > company["books_from"]]
        return (later[0]["books_from"] - timedelta(days=1)).isoformat() if later else None

    def view(self, connection, company):
        """The company in the shape the voucher gates read, built once per item, with the practices they enforce."""
        if company["id"] not in self._views:
            view = mirror.company_view(connection, company, company["version"])
            self._views[company["id"]] = {**view, "port": company["tally_port"],
                                          "books_from": company["books_from"].isoformat(),
                                          "practices": {probe: practices.settled(connection, company, probe)
                                                        for probe in practices.ENFORCED}}
        return self._views[company["id"]]

    def category(self, connection, company, centre):
        """The GUID of the cost category a cost centre belongs to, or None: a session cites the centre alone."""
        records = self.view(connection, company)["masters"]["records"]
        named = next((mirror.normalized(mirror.text(r["data"].get("CATEGORY"))) for r in records
                      if r["type"] == "COSTCENTRE" and mirror.text(r["data"].get("GUID")) == centre), None)
        guids = [mirror.text(r["data"].get("GUID")) for r in records if r["type"] == "COSTCATEGORY" and named
                 and mirror.normalized(mirror.text(r["data"].get("@_NAME")) or mirror.text(r["data"].get("NAME"))) == named]
        return guids[0] if len(guids) == 1 else None

    def gstins(self, connection, company):
        """Every GSTIN the company is registered under, across its tax units."""
        if company["id"] not in self._gstins:
            self._gstins[company["id"]] = sorted({
                row["gstin"] for row in mirror.masters(connection, company["id"], company["version"],
                                                       types=["TAXUNIT", "COMPANY"]) if row["gstin"]})
        return self._gstins[company["id"]]

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
        """The company's voucher types with their GUIDs, families and whether each is active (server-side)."""
        if company["id"] not in self._types:
            rows = mirror.masters(connection, company["id"], company["version"], types=["VOUCHERTYPE"])
            bases = base_types([row["data"] for row in rows])
            self._types[company["id"]] = [
                {"name": row["name"], "guid": row["guid"], "family": mirror.normalized(bases.get(row["name"].casefold())),
                 "active": mirror.text(row["data"].get("ISACTIVE")).casefold() != "no"} for row in rows]
        return self._types[company["id"]]

    def ledger(self, connection, company, row, ref):
        data = row["data"]
        yes = lambda field: mirror.text(data.get(field)).casefold() == "yes"  # noqa: E731
        # A GST duty ledger as Tally marks it: its head, and the rate it is set to.
        duty = mirror.text(data.get("GSTDUTYHEAD")) if mirror.text(data.get("TAXTYPE")).casefold() == "gst" else ""
        rate = mirror.text(data.get("RATEOFTAXCALCULATION"))
        # A ledger's description is the client's own note on what it records.
        return {key: value for key, value in {
            "name": row["name"], "ref": ref, "group": self.path(connection, company, row["parent"]),
            "aliases": row["aliases"] or None, "gstin": row["gstin"],
            "bank_account_ends": row["bank_account"][-4:] if row["bank_account"] else None, "ifsc": row["ifsc"],
            "cost_centres": yes("ISCOSTCENTRESON") or None, "bill_by_bill": yes("ISBILLWISEON") or None,
            "gst_duty": (f"{duty} at {rate}%" if duty and rate not in ("", "0") else duty) or None,
            "supply": mirror.text(data.get("GSTTYPEOFSUPPLY")).casefold() or None,
            "description": mirror.text(data.get("DESCRIPTION"))[:300] or None,
        }.items() if value is not None}


def entries(data):
    """A voucher's ledger lines as {ledger, debit|credit} in rupees."""
    return [{"ledger": ledger, ("debit" if cents < 0 else "credit"): f"{abs(cents) / 100:.2f}"}
            for ledger, cents in mirror.ledger_lines(data)]


def items(data):
    """A voucher's first stock lines, when it was booked item-wise: item, billed quantity, amount, ledgers, godowns."""
    return [{key: value for key, value in {
        "item": line["item"], "quantity": line["quantity"] or None,
        "amount": None if line["cents"] is None else f"{abs(line['cents']) / 100:.2f}",
        "ledgers": line["ledgers"] or None, "godowns": line["godowns"] or None}.items() if value is not None}
        for line in mirror.stock_lines(data)[:5]]


def voucher(row):
    return {key: value for key, value in {
        "date": row["date"].isoformat(), "type": row["voucher_type"], "number": row["number"] or None,
        "reference": row["reference"] or None, "narration": row["narration"][:200] or None,
        "entries": entries(row["data"]), "items": items(row["data"]) or None}.items() if value is not None}


def find_company(call, arguments):
    desk, subjects = call.state, arguments.get("subjects") or []
    parts = [part for parts in desk.parts.values() for part in parts]
    refs = desk.issue(call.connection, "company", None, [part["guid"] for part in parts])
    out = []
    for company in parts:
        gstins = desk.gstins(call.connection, company)
        named = mirror.normalized(company["name"])
        matches = [s for s in subjects if s.strip().upper() in gstins
                   or all(word in named for word in mirror.normalized(s).split())]
        # A year split's parts share one reference: a bill's date picks the part.
        out.append({"ref": refs[company["guid"]], "name": company["name"], "books_from": company["books_from"].isoformat(),
                    "gstins": gstins, **({"matches": matches} if subjects else {})})
    return {"companies": out}


def _ledgers(call, company, subjects):
    """The rows of these ledgers, named by reference (resolved here) or by exact name, and the subjects that
    named none."""
    refs = [s for s in subjects if re.fullmatch(REFERENCE, s)]
    guids = call.state.resolve(call.connection, "ledger", refs, company)
    wanted = [guids.get(s, s) for s in subjects]
    found = mirror.named(call.connection, company["id"], company["version"], "LEDGER", wanted)
    known = {row["guid"] for row in found} | {row["name_key"] for row in found}
    return found, [s for s, w in zip(subjects, wanted, strict=True) if w not in known and mirror.normalized(w) not in known]


def find_ledger(call, arguments):
    """Without a company, every company in scope is searched: which one owns this bank account or supplier."""
    desk, connection = call.state, call.connection
    scope = [desk.company_of(connection, arguments["company"])] if arguments.get("company") else list(desk.companies.values())
    found = [(subject, company, row) for subject in arguments["subjects"] for company in scope
             for row in mirror.search_masters(connection, company["id"], company["version"], ["LEDGER"], subject)]
    refs = {company["guid"]: desk.issue(connection, "ledger", company["guid"],
                                        [row["guid"] for _, owner, row in found if owner["guid"] == company["guid"]])
            for company in scope}
    named = {} if arguments.get("company") else desk.issue(connection, "company", None, [c["guid"] for c in scope])
    return {"results": [{"subject": subject, "ledgers": [
        {**desk.ledger(connection, company, row, refs[company["guid"]][row["guid"]]),
         **({"company": company["name"], "company_ref": named[company["guid"]]} if named else {})}
        for asked, company, row in found if asked == subject]} for subject in arguments["subjects"]]}


def find_stock_item(call, arguments):
    """A company's stock items matching each subject: every word of a name or alias, or an HSN code."""
    desk = call.state
    company = desk.company_of(call.connection, arguments["company"])
    found = [(subject, mirror.search_masters(call.connection, company["id"], company["version"], ["STOCKITEM"], subject))
             for subject in arguments["subjects"]]
    refs = desk.issue(call.connection, "stock_item", company["guid"], [row["guid"] for _, rows in found for row in rows])
    return {"results": [{"subject": subject, "items": [{key: value for key, value in {
        "name": row["name"], "ref": refs[row["guid"]], "unit": mirror.text(row["data"].get("BASEUNITS")) or None,
        "group": row["parent"], "hsn": row["hsn"], "aliases": row["aliases"] or None,
        "batches": mirror.text(row["data"].get("ISBATCHWISEON")).casefold() == "yes" or None,
    }.items() if value is not None} for row in rows]} for subject, rows in found]}


def godowns(call, arguments):
    desk = call.state
    company = desk.company_of(call.connection, arguments["company"])
    rows = mirror.masters(call.connection, company["id"], company["version"], types=["GODOWN"])
    listed = rows[:GODOWNS]
    refs = desk.issue(call.connection, "godown", company["guid"], [row["guid"] for row in listed])
    return {"godowns": [{"name": row["name"], "ref": refs[row["guid"]], "under": row["parent"]} for row in listed],
            **({"more": len(rows) - GODOWNS} if len(rows) > GODOWNS else {})}


def voucher_types(call, arguments):
    desk = call.state
    company, families = desk.company_of(call.connection, arguments["company"]), set(arguments["families"])
    types = [t for t in desk.voucher_types(call.connection, company) if t["active"] and t["family"] in families]
    refs = desk.issue(call.connection, "voucher_type", company["guid"], [t["guid"] for t in types])
    return {"voucher_types": [{"name": t["name"], "ref": refs[t["guid"]], "family": t["family"]} for t in types]}


def party_history(call, arguments):
    """Ledgers are named by reference, as find_ledger gives them, or by name; one that is no ledger is reported."""
    company = call.state.company_of(call.connection, arguments["company"])
    found, unknown = _ledgers(call, company, arguments["ledgers"])
    rows = mirror.ledger_history(call.connection, company["id"], company["version"], [row["name"] for row in found],
                                 limit=arguments.get("limit", 8)) if found else []
    return {"vouchers": [voucher(row) for row in rows], **({"unknown_ledgers": unknown} if unknown else {})}


def open_bills(call, arguments):
    """Each ledger's open bills, as party_history names ledgers; one that keeps no bills says so."""
    desk = call.state
    company = desk.company_of(call.connection, arguments["company"])
    found, unknown = _ledgers(call, company, arguments["ledgers"])
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
    """A supplier is asked about by its ledger's reference, which memory keys by GUID; a booking answers with
    that reference, never the GUID."""
    desk = call.state
    company = desk.company_of(call.connection, arguments["company"])
    refs = [s for s in arguments["subjects"] if re.fullmatch(REFERENCE, s)]
    guids = desk.resolve(call.connection, "ledger", refs, company)
    rows = memory.entries(call.connection, desk.run["tenant_id"], desk.run["client_id"],
                          company_ids=desk.part_ids(company), kinds=arguments.get("kinds"),
                          subjects=[guids.get(s, s) for s in arguments["subjects"]])
    suppliers = desk.issue(call.connection, "ledger", company["guid"],
                           [row["subject"].split(":")[0] for row in rows if row["kind"] == "booking"])
    return {"entries": [{"kind": row["kind"], "status": row["status"], "uses": row["uses"], "value": row["value"],
                         "subject": suppliers[row["subject"].split(":")[0]] if row["kind"] == "booking" else row["subject"]}
                        for row in rows]}


def rules(call, arguments):
    """Every active rule in scope: their text alone cannot say which matter, so none is filtered out."""
    desk = call.state
    names = {part["id"]: part["name"] for parts in desk.parts.values() for part in parts}
    return {"rules": [{"id": str(rule["id"]), "version": rule["version"], "text": rule["text"],
                       **({"company": names[rule["company_id"]]} if rule["company_id"] else {})}
                      for rule in desk.rules(call.connection)]}


def practice(call, arguments):
    desk = call.state
    parts = desk.part_ids(desk.company_of(call.connection, arguments["company"]))
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
    company = desk.company_of(call.connection, arguments["company"])
    found = [(subject, mirror.search_masters(call.connection, company["id"], company["version"], ["COSTCENTRE"], subject))
             for subject in arguments["subjects"]]
    refs = desk.issue(call.connection, "cost_centre", company["guid"], [row["guid"] for _, rows in found for row in rows])
    return {"results": [{"subject": subject, "cost_centres": [
        {"name": row["name"], "ref": refs[row["guid"]], "category": mirror.text(row["data"].get("CATEGORY")) or None}
        for row in rows]} for subject, rows in found]}


def schema(properties, required):
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


TOOLS = {tool.name: tool for tool in (
    Tool("find_company", "The client's companies in scope, with their GSTINs. Subjects (names or GSTINs) are "
         "marked where they match.", schema({"subjects": {**SUBJECTS, "minItems": 0}}, []), find_company),
    Tool("find_ledger", "Ledgers matching each subject: a name or alias (every word must appear, whatever punctuation "
         "separates them; a number as a whole word), a GSTIN, or a bank "
         "account number; a masked number matches by its last digits. Give a company to search only it; without one, "
         "every company is searched and each ledger names its company.",
         schema({"company": COMPANY, "subjects": SUBJECTS}, ["subjects"]), find_ledger),
    Tool("voucher_types", "A company's active voucher types of the given families.",
         schema({"company": COMPANY, "families": {"type": "array", "minItems": 1, "uniqueItems": True,
                                                  "items": {"enum": list(FAMILIES)}}},
                ["company", "families"]), voucher_types),
    Tool("party_history", "The newest vouchers posting to any of these ledgers in a company, cancelled ones excluded: "
         "how the client booked such transactions before, with the stock items of any booked item-wise. Give ledger "
         "references as find_ledger returns them, or exact ledger names.",
         schema({"company": COMPANY, "ledgers": SUBJECTS, "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                ["company", "ledgers"]), party_history),
    Tool("open_bills", "The open bills of ledgers that keep bill-by-bill balances, oldest first, less what this "
         "run's other rows already settle. A credit balance is owed to the party, and a payment settles it; a debit "
         "balance is owed by the party or was paid ahead, and a receipt settles it. Give ledger references or exact "
         "names.",
         schema({"company": COMPANY, "ledgers": {**SUBJECTS, "maxItems": 5}}, ["company", "ledgers"]), open_bills),
    Tool("find_stock_item", "A company's stock items matching each subject: every word of a name or alias, or an "
         "HSN code. Each names the unit its quantities are counted in; `batches` means Tally tracks its batches.",
         schema({"company": COMPANY, "subjects": SUBJECTS}, ["company", "subjects"]), find_stock_item),
    Tool("godowns", "A company's godowns, the stores its stock is kept in.", schema({"company": COMPANY}, ["company"]),
         godowns),
    Tool("cost_centres", "Cost centres of a company matching each subject, with their categories.",
         schema({"company": COMPANY, "subjects": SUBJECTS}, ["company", "subjects"]), cost_centres),
    Tool("memory", "What Minkops learnt about these subjects in a company, from saves a person approved: how a "
         "supplier's bills were booked (subject: the supplier ledger's reference), how a payee's bank rows were booked "
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
