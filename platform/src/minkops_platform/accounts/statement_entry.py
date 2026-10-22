"""Statement entry on runs: layouts proven by balances, rows routed in tool sessions.

At launch every sheet is read through its learned layout (statement_layouts).
A sheet in a format not seen before becomes a `layout` item: one session
declares how to read it, and Minkops proves the reading against the running
balances before keeping it. Proven rows become records, chunked into `chunk`
items of up to CHUNK rows. Each chunk is routed in its own session through the
desk lookups, and `propose` checks every row as it arrives (validated_plan); a
row to a ledger that keeps bill-by-bill balances also settles its open bills
(settlement). When the last item settles, transfer legs are paired, rows
repeated across overlapping files are reconciled, and a gap from the previous
statement of the same bank ledger is reported. Approved rows become native
writes (writes.py).

Facts are immutable: a proposal chooses accounting identities, never amounts,
dates or references, and a source failure found by the reader cannot be
cleared by a proposal.
"""

import hashlib
import json
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from pathlib import Path
from uuid import UUID

from jsonschema import ValidationError

from minkops_connectors.statement import normalized, read_tables
from minkops_platform import attention, profiles, work
from minkops_platform.errors import ServiceError
from minkops_platform.files import files_for
from minkops_platform.lanes import Session, Wait
from minkops_platform.run_controls import control_state, require_active, resolve_request
from minkops_platform.runtime.tools import Tool, ToolError
from minkops_platform.workflows import resolve_run_config

from . import desk_tools, memory, mirror, settlement, statement_layouts, sync, writes
from .desk_tools import COMPANY, SUBJECTS, Desk, schema
from .holds import ACTIONS, STATEMENT, hold
from .holds import actions as hold_actions
from .statement_routing import validated_plan
from .vouchers import narration_token, observed_statement, rupees, statement_voucher

CHUNK = 100
# A proposal and at most two resubmissions, per row and per layout.
ATTEMPTS = 3
MAX_BYTES = 30_000_000
ROW, SHEET = "statement_row", "statement_sheet"
EXCEPTIONS = ("company_unresolved", "ledger_unresolved", "classification_uncertain", "branch_unresolved",
              "unsupported_structure")
# Holds a later proposal may replace: what a session concluded, never what the reader found.
REPROPOSABLE = {*EXCEPTIONS, "statement_interpretation"}
# Native refusals the companion names; any other unverified save holds as statement_save_held.
SAVE_HOLDS = {"possible_existing", "uncertain_import", "destination_changed", "company_not_open", "no_company",
              "duplicate_company", "not_running", "port_closed", "busy", "too_many", "invalid_response", "rejected"}
# A statement row offers these of its holds' actions; a best-guess write needs a plan the checks accepted.
OFFERED = ("nothing", "retry", "retry_save", "settle")


# --- launch ---------------------------------------------------------------------------

def launch(connection, *, tenant, user, client, workflow, definition, body):
    """Read every sheet, queue the client's PCs to refresh, and create the run, its items and rows."""
    file_ids = [str(file_id) for file_id in body["file_ids"]]
    if not file_ids or len(file_ids) != len(set(file_ids)):
        raise ServiceError("invalid", "Select each statement file once.")
    try:
        config = resolve_run_config(definition, workflow["config_values"], body.get("config") or {})
    except (ValidationError, ValueError) as error:
        raise ServiceError("invalid", "These statement settings are not valid.") from error
    mapping = config.get("branch_mapping_file_id")
    if mapping in file_ids:
        raise ServiceError("invalid", "Select the branch mapping separately from the statements.")
    request = {"workflow": workflow["key"], "file_ids": file_ids, "config": body.get("config") or {}}
    fingerprint, previous = resolve_request(connection, tenant["id"], body["request_key"], request,
                                            work.find_by_request)
    if previous:
        return previous
    files = files_for(connection, tenant["id"], [*file_ids, *([mapping] if mapping else [])])
    if any(not f["current"] for f in files):
        raise ServiceError("conflict", "Refresh the changed files first.")
    if any(Path(f["path"]).suffix.lower() not in (".csv", ".xlsx") for f in files):
        raise ServiceError("invalid", "Statements and mappings must be CSV or XLSX. Convert legacy XLS files in Excel.")
    if sum(len(f["content"]) for f in files) > MAX_BYTES:
        raise ServiceError("invalid", "Select at most 30 MB of statements.")
    _, devices = desk_tools.prepare(connection, tenant, user, client)
    statements = [f for f in files if str(f["id"]) in file_ids]
    entries = statement_layouts.resolve(connection, tenant["id"], statement_layouts.sheets(statements))
    today, counters, refuted = date.today(), {}, set()
    specs, rows = [], []
    for entry in entries:
        source = {"file_id": str(entry["file"]["id"]), "sheet": entry["sheet"]}
        profile = entry.get("profile")
        if "error" in entry or not profile or profile["status"] != "active" or profile["id"] in refuted:
            specs.append(work.ItemSpec("layout", source))
            rows.append(None)
            continue
        read, proof, details = statement_layouts.read(entry, profile["payload"], entry["header_index"], today=today,
                                                      occurrences=counters.setdefault(source["file_id"], Counter()))
        if statement_layouts.refuted(read, proof):
            # A new statement disproves a saved reading: learn this format again, once.
            profiles.invalidate(connection, profile, "A new statement refuted the saved balance-chain reading.")
            refuted.add(profile["id"])
            specs.append(work.ItemSpec("layout", {**source, "changed": True}))
            rows.append(None)
            continue
        for chunk in _chunks(read, source, details, profile["payload"], entry["file"]["path"]):
            specs.append(work.ItemSpec("chunk", chunk["source"], waiting_on=sync.blocker(devices[0]["id"])))
            rows.append(chunk["rows"])
    config["files"] = [{"id": str(f["id"]), "path": f["path"][:200]} for f in statements]
    run = work.launch(connection, tenant_id=tenant["id"], client_id=client["id"], workflow=workflow,
                      handler="desk.statement", definition_version=definition.metadata["version"],
                      bundle=definition.session_bundle, actor_id=user["id"], request_key=body["request_key"],
                      request_hash=fingerprint, config=config,
                      title=work.title("Statement entry", [Path(f["path"]).name for f in statements]), items=specs)
    items = connection.execute("SELECT * FROM run_items WHERE run_id=%s ORDER BY ordinal", (run["id"],)).fetchall()
    for item, chunk in zip(items, rows, strict=True):
        if chunk:
            work.add_records(connection, item, chunk)
    return run


def _chunks(rows, source, details, layout, path):
    """Records for a sheet's rows, CHUNK at a time; the reader's holds are fixed facts."""
    hint = (layout["columns"].get("routing_hint") or {}).get("label")
    records = [_record(row, source, path) for row in rows]
    for start in range(0, len(records), CHUNK):
        part = records[start:start + CHUNK]
        yield {"rows": part, "source": {**source, "rows": [part[0]["source"]["row"], part[-1]["source"]["row"]],
                                        "details": details, **({"hint": hint} if hint else {})}}


def _record(row, source, path):
    code = row.get("code")
    facts = {key: row.get(key) for key in ("date", "amount_cents", "balance_cents", "reference", "narration",
                                            "account", "branch", "identity", "sheet", "row")}
    if code and "date" not in row:
        facts = {"sheet": row.get("sheet"), "row": row.get("row")}  # a summary or closing finding
    return {"kind": ROW, "source": {**source, "row": row["row"]}, "facts": {**facts, "file": path[:200]},
            "status": "held" if code else "pending", "hold_codes": [code] if code else [],
            "review_reasons": [row["reason"][:300]] if code else []}


# --- sessions -------------------------------------------------------------------------

def _sheet(connection, run, source):
    """The item's sheet read again from its file, or None when the file has no such sheet."""
    file = files_for(connection, run["tenant_id"], [source["file_id"]])[0]
    found = [e for e in statement_layouts.sheets([file]) if e["sheet"] == source["sheet"] or "error" in e]
    return found[0] if found else None


class Layout:
    """A layout session's state: the sheet it reads."""

    def __init__(self, run, item, entry):
        self.run, self.item, self.entry = run, item, entry


class Chunk(Desk):
    """A chunk session's state: the desk, plus the chunk and the run's optional mapping."""

    def __init__(self, connection, run, item):
        super().__init__(connection, run)
        self.item, self._mapping = item, None

    def mapping(self, connection):
        if self._mapping is None:
            file = files_for(connection, self.run["tenant_id"], [self.run["config"]["branch_mapping_file_id"]])[0]
            self._mapping = read_tables(bytes(file["content"]), Path(file["path"]).suffix.lower())
        return self._mapping


def session(connection, run, item):
    if item["kind"] == "layout":
        return _layout_session(connection, run, item)
    return _chunk_session(connection, run, item)


def _layout_session(connection, run, item):
    entry = _sheet(connection, run, item["source"])
    if entry is None or "error" in entry or _sheet_record(connection, item):
        return None
    profile = statement_layouts.resolve(connection, run["tenant_id"], [entry])[0].get("profile")
    if profile and profile["status"] == "active":
        return None
    if profile:
        raise Wait(statement_layouts.blocker(profile["id"]))
    bundle = desk_tools.bundle(connection, run)
    preview = json.dumps(statement_layouts.preview_sheet(entry), ensure_ascii=False)
    return Session(model=bundle["model"], instructions=bundle["stages"]["layout"], reasoning=desk_tools.reasoning(bundle),
                   content=[{"type": "input_text", "text": preview}], tools=LAYOUT_TOOLS,
                   state=Layout(run, item, entry))


def _chunk_session(connection, run, item):
    run = desk_tools.ready(connection, run)
    rows = connection.execute(
        "SELECT * FROM run_records WHERE item_id=%s AND kind=%s AND status='pending' ORDER BY position",
        (item["id"], ROW)).fetchall()
    if not rows:
        return None
    state = Chunk(connection, run, item)
    source, bundle = item["source"], desk_tools.bundle(connection, run)
    lines = [json.dumps({key: value for key, value in {
        "ref": str(row["id"]), "date": row["facts"]["date"], "amount": _rupees(row["facts"]["amount_cents"]),
        "balance": _rupees(row["facts"]["balance_cents"]), "reference": row["facts"]["reference"] or None,
        "narration": row["facts"]["narration"] or None, "hint": row["facts"]["branch"] or None,
        "account": row["facts"]["account"] or None}.items() if value is not None}, ensure_ascii=False) for row in rows]
    companies = "; ".join(f"{c['name']} ({guid})" for guid, c in state.companies.items())
    header = {"statement": rows[0]["facts"]["file"], "sheet": source["sheet"], "account_details": source["details"],
              "routing_hint_column": source.get("hint"), "companies": companies,
              "mapping": bool(run["config"].get("branch_mapping_file_id"))}
    text = (json.dumps(header, ensure_ascii=False) + f"\n{len(rows)} rows follow, one per line; `ref` identifies each "
            "row in propose.\n" + "\n".join(lines))
    tools = {**desk_tools.TOOLS, **CHUNK_TOOLS}
    if not run["config"].get("branch_mapping_file_id"):
        tools.pop("mapping")
    return Session(model=bundle["model"], instructions=bundle["instructions"], reasoning=desk_tools.reasoning(bundle),
                   content=[{"type": "input_text", "text": text}], tools=tools, state=state)


def _rupees(cents):
    return None if cents is None else f"{cents / 100:.2f}"


# --- tools ------------------------------------------------------------------------------

def _row_of(connection, run, ref, *, item=None, lock=False):
    parsed = _uuid(ref)
    if parsed is None:
        raise ToolError(f"{ref} is not a row ref.")
    row = connection.execute(
        f"""SELECT * FROM run_records WHERE run_id=%s AND id=%s AND kind=%s
            {"AND item_id=%s" if item else ""}{" FOR UPDATE" if lock else ""}""",
        (run["id"], parsed, ROW, *([item["id"]] if item else []))).fetchone()
    if row is None:
        raise ToolError(f"{ref} is not a row of this {'chunk' if item else 'run'}.")
    return row


def _proposable(record):
    return record["status"] in ("pending", "proposed") or (
        record["status"] == "held" and set(record["hold_codes"]) <= REPROPOSABLE)


def _mirrors(proposal, other):
    """Why two contra legs do not describe one transfer, or None when they do."""
    mine, theirs = proposal["resolved"], other["proposal"]["resolved"]
    if theirs["company_guid"] != mine["company_guid"]:
        return "the two legs are booked in different companies"
    if theirs["data"]["amount_cents"] != -mine["data"]["amount_cents"]:
        return "the two legs are not equal and opposite amounts"
    if (theirs["data"]["bank_ledger"], theirs["data"]["counter_ledger"]) != (
            mine["data"]["counter_ledger"], mine["data"]["bank_ledger"]):
        return "each leg's counter ledger must be the other leg's bank ledger"
    if abs((date.fromisoformat(theirs["data"]["date"]) - date.fromisoformat(mine["data"]["date"])).days) > 3:
        return "the two legs are more than three days apart"
    return None


def propose(call, arguments):
    state, connection, run = call.state, call.connection, call.run
    accepted, held, rejected = [], [], []
    # Every row of the call is locked before a bill is settled, so a person deciding one of them never deadlocks
    # with this call over the run's settlement lock.
    refs = sorted({ref for entry in arguments["rows"] if (ref := _uuid(entry["ref"]))})
    connection.execute("SELECT 1 FROM run_records WHERE run_id=%s AND item_id=%s AND id = ANY(%s) ORDER BY id FOR UPDATE",
                       (run["id"], state.item["id"], refs))
    for entry in arguments["rows"]:
        ref = entry["ref"]
        try:
            record = _row_of(connection, run, ref, item=state.item, lock=True)
        except ToolError as refusal:
            rejected.append({"ref": ref, "reason": str(refusal)})
            continue
        submissions = (record["checks"] or {}).get("submissions", 0)
        if not _proposable(record):
            reason = (hold(record["hold_codes"][0]).reason_for(STATEMENT) if record["status"] == "held"
                      else "This row is already decided.")
            rejected.append({"ref": ref, "reason": f"This row cannot take a proposal: {reason}"})
            continue
        if submissions >= ATTEMPTS:
            rejected.append({"ref": ref, "reason": "No more resubmissions for this row; it waits for review."})
            continue
        if "exception" in entry:
            work.update_record(connection, record, status="held", hold_codes=[entry["exception"]["code"]],
                               review_reasons=[entry["exception"]["detail"][:300]], company_id=None,
                               proposal={"exception": entry["exception"]}, checks={"submissions": submissions + 1})
            held.append(ref)
            continue
        try:
            company = state.company(entry["company_guid"])
            cited = state.cite(connection, entry.get("rules", []))
            resolved = validated_plan(record["facts"], [state.view(connection, company)], entry)
            proposal = {"selection": entry, "resolved": resolved, **({"rules": cited} if cited else {})}
            try:
                proposal["resolved"] = _settled(connection, state, company, record, resolved, entry.get("bills"))
            except settlement.Unresolved as unresolved:
                # Recorded for a person's one click; the row's own work is done, so it is not a rejection.
                work.update_record(connection, record, status="held", company_id=company["id"],
                                   hold_codes=["bill_unresolved"], review_reasons=[unresolved.reason],
                                   proposal={**proposal, "settlement": {"choices": unresolved.choices}},
                                   checks={"submissions": submissions + 1})
                accepted.append(ref)
                continue
            if entry.get("pair"):
                if resolved["family"] != "contra" or entry["pair"] == ref:
                    raise ValueError("Only a Contra pairs with another row, and never with itself.")
                other = _row_of(connection, run, entry["pair"])
                theirs = (other["proposal"] or {}).get("selection") or {}
                if theirs.get("pair") == ref and other["status"] == "proposed":
                    problem = _mirrors(proposal, other)
                    if problem:
                        raise ValueError(f"The paired row does not match this one: {problem}.")
        except (ValueError, ToolError) as refusal:
            last = submissions + 1
            changes = {"checks": {"submissions": last, "error": str(refusal)[:300]}}
            if last >= ATTEMPTS:
                changes.update(status="held", hold_codes=["statement_interpretation"],
                               review_reasons=[str(refusal)[:300]])
            work.update_record(connection, record, **changes)
            rejected.append({"ref": ref, "reason": str(refusal)})
            continue
        work.update_record(connection, record, status="proposed", company_id=company["id"], hold_codes=[],
                           review_reasons=[], proposal=proposal, checks={"submissions": submissions + 1})
        accepted.append(ref)
    remaining = connection.execute("SELECT count(*) AS n FROM run_records WHERE item_id=%s AND status='pending'",
                                   (state.item["id"],)).fetchone()["n"]
    return {"accepted": accepted, "held": held, "rejected": rejected, "remaining": remaining}


def _uuid(ref):
    try:
        return UUID(ref)
    except ValueError:
        return None


def _settled(connection, state, company, record, resolved, proposed):
    """The resolved row with its counter line's bills when that ledger keeps bill-by-bill balances.

    Raises ValueError for bills that cannot be written, and settlement.Unresolved
    when which bills the row settles is a person's choice.
    """
    billwise = state.billwise(connection, company)
    counter, lines = resolved["data"]["counter_ledger"], resolved.get("lines") or []
    other = next((line["ledger"] for line in lines[1:] if line["ledger"] in billwise), None)
    if other:
        raise ValueError(f"{other} keeps bill-by-bill balances, so it can only be the counter ledger.")
    if counter not in billwise:
        if proposed:
            raise ValueError(f"{counter} does not keep bill-by-bill balances; give no bills.")
        return resolved
    bills = []
    for bill in proposed or []:
        cents = Decimal(str(bill["amount"])) * 100
        if cents != int(cents):
            raise ValueError("Each bill amount must be exact to the paisa.")
        bills.append({"type": bill["type"], **({"name": bill["name"]} if "name" in bill else {}),
                      "amount_cents": int(cents)})
    settlement.lock(connection, state.run)
    allocated = settlement.allocate(settlement.open_bills(connection, state.run, company, counter, record=record),
                                    proposed=bills if proposed else None, **_terms(record, resolved))
    return {**resolved, "bills": allocated}


def _terms(record, resolved):
    """What a row's counter line settles: its amount and direction, and the text that may name the bills."""
    facts, lines = record["facts"], resolved.get("lines") or []
    return {"amount_cents": lines[0]["amount_cents"] if lines else abs(facts["amount_cents"]),
            "payment": facts["amount_cents"] < 0,
            "text": f"{facts.get('narration') or ''} {facts.get('reference') or ''}"}


def find_transfer(call, arguments):
    connection, run, results = call.connection, call.run, []
    for ref in arguments["refs"]:
        record = _row_of(connection, run, ref)
        facts = record["facts"]
        day = date.fromisoformat(facts["date"])
        candidates = connection.execute(
            """SELECT * FROM run_records WHERE run_id=%s AND kind=%s AND id<>%s
                   AND (facts->>'amount_cents')::bigint = %s AND (facts->>'date')::date BETWEEN %s AND %s
               ORDER BY (facts->>'date'), position LIMIT 5""",
            (run["id"], ROW, record["id"], -facts["amount_cents"], day - timedelta(days=3),
             day + timedelta(days=3))).fetchall()
        results.append({"ref": ref, "candidates": [_brief(row) for row in candidates]})
    return {"results": results}


def pair_return(call, arguments):
    state, connection, run = call.state, call.connection, call.run
    today = statement_layouts.today_for(run)
    results = []
    for utr in arguments["utrs"]:
        needle = "".join(utr.split()).upper()
        if len(needle) < 6:
            raise ToolError(f"{utr} is too short to identify a payment.")
        rows = connection.execute(
            """SELECT * FROM run_records WHERE run_id=%s AND kind=%s
                   AND (position(%s IN upper(coalesce(facts->>'reference',''))) > 0
                        OR position(%s IN upper(coalesce(facts->>'narration',''))) > 0)
               ORDER BY (facts->>'date'), position LIMIT 10""", (run["id"], ROW, needle, needle)).fetchall()
        tally = [{"company": company["name"], **desk_tools.voucher(row)}
                 for company in state.companies.values()
                 for row in mirror.vouchers_mentioning(connection, company["id"], company["version"], needle,
                                                       today - timedelta(days=400), today)]
        results.append({"utr": utr, "rows": [_brief(row) for row in rows], "tally": tally})
    return {"results": results}


def mapping(call, arguments):
    tables, results = call.state.mapping(call.connection), []
    for label in arguments["labels"]:
        wanted = normalized(label)
        matches = [{"sheet": sheet, "header": [str(v or "") for v in next((r for r in table if any(r)), [])][:30],
                    "rows": [[str(v or "") for v in row][:30] for row in table
                             if any(wanted in normalized(v) for v in row if v is not None)][:20]}
                   for sheet, table, _ in tables]
        results.append({"label": label, "sheets": [m for m in matches if m["rows"]]})
    return {"results": results}


def propose_layout(call, arguments):
    state, connection, run = call.state, call.connection, call.run
    if ("layout" in arguments) == ("exception" in arguments):
        raise ToolError("Give either a layout or an exception.")
    earlier = connection.execute("SELECT count(*) AS n FROM tool_calls WHERE item_id=%s AND name='propose_layout'",
                                 (state.item["id"],)).fetchone()["n"]
    if earlier >= ATTEMPTS:
        raise ToolError("No more attempts: this sheet will be held for review.")
    entry, path = state.entry, state.entry["file"]["path"]
    if "exception" in arguments:
        code = arguments["exception"]["code"]
        _hold_sheet(connection, state.item, path, "deferred" if code == "not_a_statement" else "held",
                    "statement_layout_unknown", arguments["exception"]["detail"])
        return {"accepted": True, "sheet": "skipped as not a statement" if code == "not_a_statement" else "held"}
    outcome = statement_layouts.prove(connection, run["tenant_id"], entry, arguments["layout"],
                                      today=statement_layouts.today_for(run), actor=run["actor_id"],
                                      provenance={"run_id": str(run["id"]), "file": path})
    if outcome["status"] == "refuted":
        raise ToolError(f"The balances refute this reading. {outcome['reason']}")
    if outcome["status"] == "question":
        statement_layouts.ask(connection, run, outcome["profile"], path, outcome["question"], outcome["proof"],
                              outcome["printed"])
        return {"accepted": True, "note": "A member confirms this reading once before its rows are entered."}
    return {"accepted": True}


def _brief(row):
    facts, selection = row["facts"], (row["proposal"] or {}).get("selection") or {}
    resolved = (row["proposal"] or {}).get("resolved") or {}
    return {key: value for key, value in {
        "ref": str(row["id"]), "date": facts.get("date"), "amount": _rupees(facts.get("amount_cents")),
        "file": facts.get("file"), "sheet": facts.get("sheet"), "account": facts.get("account") or None,
        "narration": (facts.get("narration") or "")[:160] or None, "status": row["status"],
        "family": resolved.get("family"), "company": resolved.get("company"),
        "bank_ledger": (resolved.get("data") or {}).get("bank_ledger"),
        "counter_ledger": (resolved.get("data") or {}).get("counter_ledger"), "pair": selection.get("pair"),
    }.items() if value is not None}


REF = {"type": "string", "minLength": 36, "maxLength": 36}
GUID = {"type": ["string", "null"], "maxLength": 100}
SELECTION = schema({
    "ref": REF, "company_guid": COMPANY, "bank_ledger_guid": COMPANY, "counter_ledger_guid": COMPANY,
    "voucher_type_guid": COMPANY, "family": {"enum": ["payment", "receipt", "contra"]},
    "cost_centre_guid": GUID, "cost_category_guid": GUID,
    "lines": {"type": "array", "minItems": 1, "maxItems": 10, "items": schema({
        "role": {"enum": ["counter", "tax", "tds", "charge"]}, "ledger_guid": COMPANY,
        "amount": {"type": "number", "exclusiveMinimum": 0}, "cost_centre_guid": GUID, "cost_category_guid": GUID},
        ["role", "ledger_guid", "amount"])},
    "pair": {**REF, "description": "The other leg's ref, for a transfer between own accounts."},
    "bills": {"type": "array", "minItems": 1, "maxItems": 20, "description": (
        "For a counter ledger that keeps bill-by-bill balances: the bills its line settles, adding up to its amount. "
        "Leave out to let the open bills decide."), "items": schema({
            "type": {"enum": list(settlement.TYPES)},
            "name": {"type": "string", "minLength": 1, "maxLength": 100,
                     "description": "The open bill's name; an Advance names a new one. On Account names none."},
            "amount": {"type": "number", "exclusiveMinimum": 0}}, ["type", "amount"])},
    "rules": {"type": "array", "maxItems": 10, "items": REF, "description": "The client's rules this row follows."},
    "payee": {"type": "string", "minLength": 1, "maxLength": 200,
              "description": "The counterparty the narration names, as printed, without references or amounts."},
    "evidence": {"type": "string", "minLength": 1, "maxLength": 1500},
}, ["ref", "company_guid", "bank_ledger_guid", "counter_ledger_guid", "voucher_type_guid", "evidence"])
EXCEPTION = schema({"ref": REF, "exception": schema({"code": {"enum": list(EXCEPTIONS)},
                                                     "detail": {"type": "string", "minLength": 1, "maxLength": 1000}},
                                                    ["code", "detail"])}, ["ref", "exception"])
COLUMN = {"type": "integer", "minimum": 1, "maximum": 100}
RULES = {"type": "array", "maxItems": 10, "items": schema({
    "column": COLUMN, "starts_with": {"type": "string", "minLength": 1, "maxLength": 100},
    "repeat_header": {"type": "boolean"}}, [])}
OPTIONAL_COLUMN = {"anyOf": [{"type": "null"}, schema({"column": COLUMN}, ["column"])]}
LAYOUT = schema({
    "header_row": {"type": "integer", "minimum": 1, "maximum": 200},
    "columns": schema({
        "date": schema({"column": COLUMN, "order": {"enum": ["dmy", "mdy", "ymd", "native"]}}, ["column", "order"]),
        "amount": {"oneOf": [
            schema({"mode": {"const": "debit_credit"}, "debit": COLUMN, "credit": COLUMN}, ["mode", "debit", "credit"]),
            schema({"mode": {"const": "signed"}, "column": COLUMN, "negative": {"enum": ["debit", "credit"]}},
                   ["mode", "column", "negative"]),
            schema({"mode": {"const": "indicator"}, "column": COLUMN, "indicator": COLUMN,
                    **{key: {"type": "array", "minItems": 1, "maxItems": 5,
                             "items": {"type": "string", "minLength": 1, "maxLength": 20}}
                       for key in ("debit_values", "credit_values")}},
                   ["mode", "column", "indicator", "debit_values", "credit_values"])]},
        "balance": OPTIONAL_COLUMN, "reference": OPTIONAL_COLUMN, "account": OPTIONAL_COLUMN,
        "narration": schema({"columns": {"type": "array", "maxItems": 5, "items": COLUMN}}, ["columns"]),
        "routing_hint": {"anyOf": [{"type": "null"}, schema(
            {"column": COLUMN, "label": {"type": "string", "minLength": 1, "maxLength": 100}}, ["column", "label"])]},
    }, ["date", "amount", "balance", "reference", "narration", "account", "routing_hint"]),
    "row_order": {"enum": ["oldest_first", "newest_first"]},
    "rows": schema({
        "opening": RULES, "closing": RULES, "ignore": RULES, "ends_at": RULES,
        "summary": {"type": "array", "maxItems": 10, "items": schema({
            "kind": {"enum": ["opening", "closing", "debit", "credit"]}, "column": COLUMN,
            "starts_with": {"type": "string", "minLength": 1, "maxLength": 100}, "value_column": COLUMN,
            "account_column": COLUMN}, ["kind", "column", "starts_with", "value_column"])}}, []),
    "details": {"type": "array", "maxItems": 10, "items": schema({
        "kind": {"enum": list(statement_layouts.DETAIL_KINDS)}, "row": {"type": "integer", "minimum": 1,
                                                                        "maximum": 200}, "column": COLUMN},
        ["kind", "row", "column"])},
    "evidence": {"type": "string", "minLength": 1, "maxLength": 1500},
}, ["header_row", "columns", "row_order", "rows", "evidence"])

CHUNK_TOOLS = {tool.name: tool for tool in (
    Tool("propose", "Propose entries for rows of this chunk, up to 50 at a time: a destination for each row, or an "
         "exception explaining what remains uncertain. Each is checked at once; a rejected row says why.",
         schema({"rows": {"type": "array", "minItems": 1, "maxItems": 50, "items": {"oneOf": [SELECTION, EXCEPTION]}}},
                ["rows"]), propose),
    Tool("find_transfer", "Rows anywhere in this run that could be the other leg of a transfer: equal and opposite "
         "amounts within three days.", schema({"refs": {"type": "array", "minItems": 1, "maxItems": 20, "items": REF}},
                                             ["refs"]), find_transfer),
    Tool("pair_return", "For a returned payment's UTR, the original payment: rows in this run, and vouchers in the "
         "client's Tally books, that mention it.", schema({"utrs": SUBJECTS}, ["utrs"]), pair_return),
    Tool("mapping", "Rows of the client's mapping file mentioning each label, with each sheet's header row.",
         schema({"labels": SUBJECTS}, ["labels"]), mapping),
)}
LAYOUT_TOOLS = {"propose_layout": Tool(
    "propose_layout", "Declare how to read this sheet (layout), or that it is not a statement (exception). Minkops "
    "proves the reading against the running balances and answers at once.",
    schema({"layout": LAYOUT, "exception": schema({"code": {"enum": ["not_a_statement", "unreadable"]},
                                                   "detail": {"type": "string", "minLength": 1, "maxLength": 500}},
                                                  ["code", "detail"])}, []),
    propose_layout)}


# --- settling ---------------------------------------------------------------------------

def _sheet_record(connection, item):
    return connection.execute("SELECT * FROM run_records WHERE item_id=%s AND kind=%s", (item["id"], SHEET)).fetchone()


def _hold_sheet(connection, item, path, status, code, reason):
    if _sheet_record(connection, item):
        return
    work.add_records(connection, item, [{
        "kind": SHEET, "source": {"file_id": item["source"]["file_id"], "sheet": item["source"]["sheet"]},
        "facts": {"file": path[:200], "sheet": item["source"]["sheet"]}, "status": status,
        "hold_codes": [code] if status == "held" else [], "review_reasons": [reason[:300]]}])


def settle(connection, run, item, outcome):
    if item["kind"] == "layout":
        _settle_layout(connection, run, item, outcome)
    else:
        reason = (outcome.error or "No ledger interpretation was returned for this transaction.")[:300]
        code = "run_stopped" if outcome.stopped else "statement_interpretation"
        connection.execute(
            """UPDATE run_records SET status='held', hold_codes=%s, review_reasons=%s, version=version+1,
               updated_at=now() WHERE item_id=%s AND status='pending'""", ([code], [reason], item["id"]))
    _finalize(connection, run, settling=item)


def _settle_layout(connection, run, item, outcome):
    entry = _sheet(connection, run, item["source"])
    path = files_for(connection, run["tenant_id"], [item["source"]["file_id"]])[0]["path"]
    if entry is None or "error" in entry:
        _hold_sheet(connection, item, path, "held", "statement_format", hold("statement_format").reason)
        return
    if _sheet_record(connection, item):
        return
    profile = statement_layouts.resolve(connection, run["tenant_id"], [entry])[0].get("profile")
    if profile and profile["status"] == "proposed":
        raise Wait(statement_layouts.blocker(profile["id"]))
    if not profile:
        code = "statement_layout_changed" if item["source"].get("changed") else "statement_layout_unknown"
        _hold_sheet(connection, item, path, "held", code, outcome.error or hold(code).reason)
        return
    rows, _, details = statement_layouts.read(entry, profile["payload"], entry["header_index"],
                                              today=statement_layouts.today_for(run))
    chunks = list(_chunks(rows, item["source"], details, profile["payload"], path))
    if not chunks:
        _hold_sheet(connection, item, path, "deferred", "statement_layout_unknown", "The sheet has no transactions.")
        return
    waiting = desk_tools.refreshing(connection, run["client_id"])
    added = work.add_items(connection, run, [work.ItemSpec("chunk", chunk["source"], waiting_on=waiting)
                                             for chunk in chunks])
    for added_item, chunk in zip(added, chunks, strict=True):
        work.add_records(connection, added_item, chunk["rows"])


def _finalize(connection, run, *, settling):
    """Once no other item is left, pair transfers, reconcile repeats, record spans and apply standing approval.

    `settling` is the item whose settle calls this; it finishes in the same transaction.
    """
    run = connection.execute("SELECT * FROM runs WHERE id=%s FOR UPDATE", (run["id"],)).fetchone()
    if connection.execute(
            "SELECT 1 FROM run_items WHERE run_id=%s AND id<>%s AND state IN ('waiting','queued','running') LIMIT 1",
            (run["id"], settling["id"])).fetchone():
        return
    records = connection.execute(
        "SELECT * FROM run_records WHERE run_id=%s AND kind=%s ORDER BY id FOR UPDATE", (run["id"], ROW)).fetchall()
    ready = [r for r in records if r["status"] == "proposed"]
    _pair_transfers(connection, ready)
    _reconcile_repeats(connection, [r for r in ready if r["status"] == "proposed"])
    _record_spans(connection, run, records)
    if (run["config"].get("review_mode") == "only_exceptions"
            and control_state(connection, run["tenant_id"], run["task_id"]) == "active"):
        for record in records:
            if record["status"] == "proposed" and not record["review_reasons"]:
                _approve(connection, run, record, actor=run["actor_id"])


def _pair_transfers(connection, ready):
    by_id = {str(r["id"]): r for r in ready}
    for record in ready:
        selection = record["proposal"]["selection"]
        if not selection.get("pair") or record["status"] != "proposed" or record["proposal"].get("transfer"):
            continue
        other = by_id.get(selection["pair"])
        problem = ("the other leg has no matching proposal"
                   if other is None or other["proposal"]["selection"].get("pair") != str(record["id"])
                   else _mirrors(record["proposal"], other))
        if problem:
            for leg in (record, other):
                if leg is not None and leg["status"] == "proposed":
                    work.update_record(connection, leg, status="held", hold_codes=["statement_transfer_unpaired"],
                                       review_reasons=[f"The two legs of this transfer do not match: {problem}."])
            continue
        debit, credit = (record, other) if record["facts"]["amount_cents"] < 0 else (other, record)
        work.update_record(connection, debit, proposal={**debit["proposal"],
                                                        "transfer": {"role": "writes", "other": str(credit["id"])}})
        work.update_record(connection, credit, proposal={**credit["proposal"],
                                                         "transfer": {"role": "covered", "by": str(debit["id"])}})


def _accounting(record):
    resolved = record["proposal"]["resolved"]
    return json.dumps([resolved["family"], resolved["voucher_type"]["GUID"], resolved["data"]["counter_ledger"],
                       resolved.get("lines"), resolved.get("allocation"), resolved.get("bills")], sort_keys=True,
                      default=str)


def _reconcile_repeats(connection, ready):
    """A transaction in two overlapping files is written once; differing routes of it hold."""
    groups = {}
    for record in ready:
        if record["proposal"].get("transfer") or record["proposal"].get("repeat_of"):
            continue
        resolved = record["proposal"]["resolved"]
        key = (resolved["company_guid"], resolved["data"]["bank_ledger"], record["facts"]["identity"])
        groups.setdefault(key, []).append(record)
    for group in groups.values():
        if len(group) < 2:
            continue
        if len({_accounting(r) for r in group}) > 1:
            for record in group:
                work.update_record(connection, record, status="held", hold_codes=["statement_conflict"],
                                   review_reasons=[hold("statement_conflict").reason])
            continue
        first, *rest = sorted(group, key=lambda r: (r["facts"]["file"], r["facts"]["sheet"], r["facts"]["row"]))
        for record in rest:
            work.update_record(connection, record, proposal={**record["proposal"], "repeat_of": str(first["id"])},
                               review_reasons=["Repeated in another selected statement; it is entered once."])


def _record_spans(connection, run, records):
    """Each bank ledger's opening and closing balance by its chain; a gap from the last statement is reported.

    A statement account's rows chain by their proven balances, held rows included:
    holding a row for its ledger does not unsettle its balance. The chain belongs
    to the one bank ledger its routed rows agree on.
    """
    accounts = {}
    for record in records:
        facts = record["facts"]
        if facts.get("balance_cents") is None or facts.get("amount_cents") is None:
            continue
        account = accounts.setdefault((facts["file"], facts["sheet"], facts.get("account") or ""),
                                      {"rows": {}, "banks": set()})
        account["rows"][facts["identity"]] = facts
        resolved = (record["proposal"] or {}).get("resolved")
        if resolved and record["status"] != "held":
            account["banks"].add((record["company_id"], resolved["data"]["bank_ledger"]))
    chains = {}
    for account in accounts.values():
        if len(account["banks"]) == 1:
            chains.setdefault(next(iter(account["banks"])), {}).update(account["rows"])
    for (company_id, bank), by_identity in chains.items():
        rows = list(by_identity.values())
        balances = {r["balance_cents"] for r in rows}
        openings = {r["balance_cents"] - r["amount_cents"] for r in rows}
        start = [r for r in rows if r["balance_cents"] - r["amount_cents"] not in balances]
        end = [r for r in rows if r["balance_cents"] not in openings]
        if len(start) != 1 or len(end) != 1:
            continue
        opening, closing = start[0]["balance_cents"] - start[0]["amount_cents"], end[0]["balance_cents"]
        connection.execute(
            """INSERT INTO statement_spans(tenant_id,run_id,company_id,bank_ledger,date_from,date_to,opening_cents,
               closing_cents) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (run_id,company_id,bank_ledger) DO UPDATE
               SET date_from=EXCLUDED.date_from,date_to=EXCLUDED.date_to,opening_cents=EXCLUDED.opening_cents,
               closing_cents=EXCLUDED.closing_cents""",
            (run["tenant_id"], run["id"], company_id, bank, start[0]["date"], end[0]["date"], opening, closing))
        previous = connection.execute(
            """SELECT * FROM statement_spans WHERE company_id=%s AND bank_ledger=%s AND run_id<>%s AND date_to < %s
               ORDER BY date_to DESC LIMIT 1""", (company_id, bank, run["id"], start[0]["date"])).fetchone()
        if previous and previous["closing_cents"] != opening:
            attention.record(connection, run, f"statement:{run['id']}:{company_id}:{bank}:gap", bank,
                             "Transactions missing", target={"reason": (
                                 f"{bank} closed at {rupees(previous['closing_cents'])} on {previous['date_to']} in an "
                                 f"earlier statement, but this one opens at {rupees(opening)} on {start[0]['date']}. "
                                 "Select the statement that covers the gap; rows here are not held.")},
                             actor=run["actor_id"])


# --- review and decisions ---------------------------------------------------------------

def _holds(record):
    return [{"code": code, "label": hold(code).label, "reason": hold(code).reason_for(STATEMENT)}
            for code in record["hold_codes"]]


def _offered(record):
    if record["status"] == "proposed":
        return ["approve", "nothing"]
    if record["status"] == "held":
        return [action for action in hold_actions(record["hold_codes"]) if action in OFFERED
                and (action != "retry" or record["kind"] == ROW)]
    return []


def _actions(record):
    """The row's one-click actions; Settle is one button per allocation the open bills leave."""
    choices = ((record["proposal"] or {}).get("settlement") or {}).get("choices") or []
    actions = []
    for action in _offered(record):
        if action == "settle":
            actions.extend({"action": action, "label": choice["label"], "detail": {"choice": index}}
                           for index, choice in enumerate(choices))
        else:
            actions.append({"action": action, "label": ACTIONS.get(action, "Approve")})
    return actions


def summarize(run, record):
    facts, resolved = record["facts"] or {}, (record["proposal"] or {}).get("resolved") or {}
    return {key: value for key, value in {
        "id": str(record["id"]), "version": record["version"], "kind": record["kind"], "status": record["status"],
        "file": facts.get("file"), "sheet": facts.get("sheet"), "row": facts.get("row"), "date": facts.get("date"),
        "amount": _rupees(facts.get("amount_cents")), "narration": (facts.get("narration") or "")[:120] or None,
        "company": resolved.get("company"), "bank_ledger": (resolved.get("data") or {}).get("bank_ledger"),
        "counter_ledger": " + ".join(line["ledger"] for line in resolved["lines"]) if resolved.get("lines")
        else (resolved.get("data") or {}).get("counter_ledger"), "bills": resolved.get("bills"),
        "holds": _holds(record), "review": record["review_reasons"], "actions": _actions(record),
    }.items() if value not in (None, [])}


def detail(connection, run, record):
    proposal = record["proposal"] or {}
    return {**summarize(run, record), "facts": record["facts"], "evidence": (proposal.get("selection") or {}).get(
        "evidence") or (proposal.get("exception") or {}).get("detail"), "transfer": proposal.get("transfer"),
            "repeat_of": proposal.get("repeat_of"), "current": record["current"],
            "lines": (proposal.get("resolved") or {}).get("lines"), "rules": proposal.get("rules"),
            "settlement": proposal.get("settlement")}


def decide(connection, run, record, action, detail, context):
    if action not in _offered(record):
        raise ServiceError("conflict", "That action is not available for this row now.")
    if action == "approve":
        return _approve(connection, run, record, actor=context["user"]["id"])
    if action == "settle":
        return _settle(connection, run, record, detail, actor=context["user"]["id"])
    if action == "nothing":
        work.update_record(connection, record, status="deferred")
        return {"status": "deferred"}
    if action == "retry_save":
        require_active(connection, run["tenant_id"], run["task_id"])
        work.update_record(connection, record, status="proposed", hold_codes=[], review_reasons=[])
        return _approve(connection, run, record, actor=context["user"]["id"])
    # Recheck: the row gets a fresh proposal in a new attempt of its chunk.
    item = connection.execute("SELECT * FROM run_items WHERE id=%s", (record["item_id"],)).fetchone()
    work.update_record(connection, record, status="pending", hold_codes=[], review_reasons=[], proposal=None,
                       checks=None, company_id=None)
    if item["state"] in ("done", "failed"):
        work.requeue_item(connection, run["tenant_id"], item["id"])
    return {"status": "pending"}


def _settle(connection, run, record, detail, *, actor):
    """A person's choice of the bills a held row settles: approved with them, or offered again when they changed."""
    proposal = record["proposal"]
    choices = proposal["settlement"]["choices"]
    index = (detail or {}).get("choice")
    if type(index) is not int or not 0 <= index < len(choices):
        raise ServiceError("invalid", "Choose one of the offered settlements.")
    resolved, terms = proposal["resolved"], _terms(record, proposal["resolved"])
    company = connection.execute("SELECT * FROM companies WHERE id=%s", (record["company_id"],)).fetchone()
    company = {**company, "version": run["pins"][str(company["id"])]}
    settlement.lock(connection, run)
    bills = settlement.open_bills(connection, run, company, resolved["data"]["counter_ledger"], record=record)
    try:
        settlement.check(bills, choices[index]["bills"], amount_cents=terms["amount_cents"], payment=terms["payment"])
    except ValueError:
        # Another row settled some of these bills since they were offered: offer what is open now.
        work.update_record(connection, record, proposal={**proposal, "settlement": {
            "choices": settlement.offers(bills, **terms)}}, review_reasons=[
            "Another entry of this run settled some of these invoices since they were offered. Choose again."])
        return {"status": "held"}
    work.update_record(connection, record, status="proposed", hold_codes=[], review_reasons=[], proposal={
        **proposal, "resolved": {**resolved, "bills": choices[index]["bills"]},
        "settlement": {**proposal["settlement"], "chosen": index}})
    return _approve(connection, run, record, actor=actor)


def approve_ready(connection, run, actor):
    """Approve every proposed row that needs no review, as one Write ready rows action."""
    require_active(connection, run["tenant_id"], run["task_id"])
    ids = connection.execute(
        """SELECT id FROM run_records WHERE run_id=%s AND kind=%s AND status='proposed' AND review_reasons='{}'
           ORDER BY id""", (run["id"], ROW)).fetchall()
    for row in ids:
        # Read each row as it is now: approving one transfer leg approves its partner too.
        record = connection.execute("SELECT * FROM run_records WHERE id=%s FOR UPDATE", (row["id"],)).fetchone()
        if record["status"] == "proposed" and not record["review_reasons"]:
            _approve(connection, run, record, actor=actor)
    approved = connection.execute("SELECT count(*) AS n FROM run_records WHERE id = ANY(%s) AND status IN "
                                  "('approved','writing')", ([row["id"] for row in ids],)).fetchone()["n"]
    work.refresh(connection, run["tenant_id"], run["id"], describe=describe)
    return {"approved": approved}


def _approve(connection, run, record, *, actor):
    """One approval writes once: a covered transfer leg or repeated row approves the row that writes it."""
    proposal = record["proposal"]
    leader_id = (proposal.get("transfer") or {}).get("by") or proposal.get("repeat_of")
    if leader_id:
        work.update_record(connection, record, status="approved")
        leader = connection.execute("SELECT * FROM run_records WHERE id=%s FOR UPDATE", (leader_id,)).fetchone()
        if leader["status"] == "proposed":
            _approve(connection, run, leader, actor=actor)
        return {"status": "approved"}
    company = connection.execute("SELECT * FROM companies WHERE id=%s", (record["company_id"],)).fetchone()
    if not writes.request(connection, run, record, _plan(connection, run, record), company, actor=actor):
        work.update_record(connection, record, status="held", hold_codes=["statement_save_waiting"],
                           review_reasons=[hold("statement_save_waiting").reason_for(STATEMENT)])
        return {"status": "held"}
    work.update_record(connection, record, status="writing")
    for follower in connection.execute(
            """SELECT * FROM run_records WHERE run_id=%s AND status='proposed'
               AND (proposal->'transfer'->>'by'=%s OR proposal->>'repeat_of'=%s) FOR UPDATE""",
            (run["id"], str(record["id"]), str(record["id"]))).fetchall():
        work.update_record(connection, follower, status="approved")
    return {"status": "writing"}


def _plan(connection, run, record):
    """The approved row's native v5 voucher; a transfer's two legs become one Contra."""
    proposal, facts = record["proposal"], record["facts"]
    resolved = proposal["resolved"]
    transfer = proposal.get("transfer")
    if transfer:
        other = connection.execute("SELECT facts FROM run_records WHERE id=%s", (transfer["other"],)).fetchone()
        legs = sorted([facts["identity"], other["facts"]["identity"]])
        identity = hashlib.sha256(json.dumps(legs).encode()).hexdigest()
        key = f"statement:{resolved['company_guid']}:contra"
        plan = statement_voucher(resolved, remote_id=narration_token(run["tenant_id"], key, identity),
                                 identity=identity, legs=legs)
        return {**plan, "destination_key": key}
    key = f"statement:{resolved['company_guid']}:{resolved['data']['bank_ledger']}"
    siblings = connection.execute(
        """SELECT facts->>'identity' AS identity FROM run_records WHERE run_id=%s AND kind=%s AND id<>%s
               AND company_id=%s AND proposal->'resolved'->'data'->>'bank_ledger'=%s AND facts->>'date'=%s
               AND (facts->>'amount_cents')::bigint=%s AND facts->>'identity' IS NOT NULL""",
        (run["id"], ROW, record["id"], record["company_id"], resolved["data"]["bank_ledger"], facts["date"],
         facts["amount_cents"])).fetchall()
    plan = statement_voucher(resolved, remote_id=narration_token(run["tenant_id"], key, facts["identity"]),
                             identity=facts["identity"], counterpart=resolved["family"] == "contra",
                             distinct=[narration_token(run["tenant_id"], key, s["identity"]) for s in siblings])
    return {**plan, "destination_key": key}


def written(connection, run, record, write, receipt):
    """A receipt from the companion: a verified save, a verified existing voucher, or a hold."""
    outcome = receipt.get("outcome")
    if outcome not in ("saved", "duplicate", "attention"):
        raise ServiceError("invalid", "Invalid Tally write receipt.")
    if outcome in ("saved", "duplicate"):
        try:
            current = observed_statement(write["plan"], receipt.get("current"))
        except ValueError as error:
            raise ServiceError("invalid", str(error)) from error
        work.update_record(connection, record, status=outcome, current=current, hold_codes=[], review_reasons=[])
        # A verified row a person approved is how its payee's rows are booked.
        memory.learn_routing(connection, run, record, write["plan"], current["guid"],
                             actor_id=memory.approver(connection, run, record))
        follow = {"status": "duplicate", "hold_codes": [], "review_reasons": []}
    else:
        code = receipt.get("hold") if receipt.get("hold") in SAVE_HOLDS else "statement_save_held"
        reason = (str(receipt.get("message") or "") or hold(code).reason_for(STATEMENT))[:300]
        work.update_record(connection, record, status="held", hold_codes=[code], review_reasons=[reason])
        follow = {"status": "held", "hold_codes": [code], "review_reasons": [reason]}
    for follower in connection.execute(
            """SELECT * FROM run_records WHERE run_id=%s AND status='approved'
               AND (proposal->'transfer'->>'by'=%s OR proposal->>'repeat_of'=%s) FOR UPDATE""",
            (run["id"], str(record["id"]), str(record["id"]))).fetchall():
        work.update_record(connection, follower, **follow)
    return {"verified": outcome in ("saved", "duplicate"), "outcome": outcome if outcome != "attention" else "held"}


def stopped(connection, run):
    """Stop: unstarted items are cancelled, unsaved rows hold, and pending writes are withdrawn."""
    work.cancel(connection, run["tenant_id"], run["id"])
    withdrawn = writes.cancel(connection, run)
    connection.execute(
        """UPDATE run_records SET status='held', hold_codes='{run_stopped}', review_reasons=%s, version=version+1,
           updated_at=now() WHERE run_id=%s AND (status IN ('pending','proposed','approved')
               OR (status='writing' AND id = ANY(%s)))""",
        ([hold("run_stopped").reason_for(STATEMENT)], run["id"], withdrawn))


describe = partial(work.describe_run, wording=work.Wording(
    input=("part", "parts"), entry=("entry", "entries"), destination="Tally",
    preparing="Refreshing the Tally copy on your PC.",
    failed="The statements could not be read. Recheck them or start a new run."))


class StatementEntry:
    """The `desk.statement` handler: the hooks lanes, the runs API and native writes call."""

    launch = staticmethod(launch)
    session = staticmethod(session)
    settle = staticmethod(settle)
    describe = staticmethod(describe)
    summarize = staticmethod(summarize)
    detail = staticmethod(detail)
    decide = staticmethod(decide)
    approve_ready = staticmethod(approve_ready)
    written = staticmethod(written)
    stopped = staticmethod(stopped)


HANDLER = StatementEntry()
