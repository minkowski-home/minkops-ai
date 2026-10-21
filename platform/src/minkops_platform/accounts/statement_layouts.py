"""Statement layouts: declared once per bank format, proven by balances, reused.

A layout is identified by its header row (cells and positions), so a statement
from the same bank export matches it after any preamble. A layout session
declares one for an unseen sheet; this module applies it to the real file and
keeps it only when the running balances prove the amounts and the dates prove
their order. When they cannot, a member answers one question (which date
order) or confirms sample rows once, and the sheet's run item waits for that
answer. Known layouts read with no AI call at all.
"""

from datetime import date
from pathlib import Path

from minkops_connectors.statement import (
    apply_layout,
    cell_text,
    header_signature,
    preview,
    read_tables,
    signatures,
)
from minkops_platform import attention, profiles, work
from minkops_platform.errors import ServiceError

KIND = "statement_layout"
BROKEN = ("statement_balance", "statement_closing", "statement_summary")
DETAIL_KINDS = ("account_number", "bank", "ifsc", "holder", "period")


def blocker(profile_id):
    """What a sheet's layout item waits on until a member answers its question."""
    return {"kind": "layout", "ref": str(profile_id)}


def sheets(files):
    """Every non-empty sheet of the statement files, or a format failure per file."""
    found = []
    for file in files:
        try:
            tables = read_tables(bytes(file["content"]), Path(file["path"]).suffix.lower())
        except (ValueError, UnicodeError):
            found.append({"file": file, "sheet": "", "error": "statement_format"})
            continue
        for sheet, table, formulas in tables:
            if any(any(str(v).strip() for v in row if v is not None) for row in table):
                found.append({"file": file, "sheet": sheet, "table": table, "formulas": formulas})
    return found


def resolve(connection, tenant_id, entries):
    """Attach each sheet's live layout (by header signature) and where its header sits."""
    candidates = [(entry, signatures(entry["table"])) for entry in entries if "table" in entry]
    keys = {sig for _, found in candidates for sig in found}
    live = connection.execute(
        "SELECT * FROM client_profiles WHERE tenant_id=%s AND kind=%s AND scope_key=ANY(%s) AND status IN ('proposed','active')",
        (tenant_id, KIND, list(keys))).fetchall() if keys else []
    by_signature = {p["scope_key"]: p for p in live}
    # The same bank header can occur in several files or sheets of one run;
    # each occurrence binds on its own.
    for entry, found in candidates:
        for signature, index in sorted(found.items(), key=lambda pair: pair[1]):
            if signature in by_signature:
                entry.update(profile=by_signature[signature], header_index=index)
                break
    return entries


def read(entry, layout, header_index, *, today, occurrences=None):
    """The sheet's canonical rows and proof through this layout, and the account details it declares."""
    rows, proof = apply_layout(entry["table"], layout, header_index, sheet=entry["sheet"],
                               formulas=entry["formulas"], occurrences=occurrences, today=today)
    details = {}
    for spec in layout.get("details") or []:
        cells = entry["table"][spec["row"] - 1] if spec["row"] <= len(entry["table"]) else ()
        value = cell_text(cells[spec["column"] - 1]) if spec["column"] <= len(cells) else ""
        if value:
            details[spec["kind"]] = value[:120]
    return rows, proof, details


def refuted(rows, proof):
    """The balances disprove this reading: some running balance or control does not chain."""
    return not proof["amounts"] and any(r.get("code") in BROKEN for r in rows)


def payload(spec, table):
    """A declared layout as stored: the reading, and the header it is recognised by."""
    header = table[spec["header_row"] - 1]
    return {key: spec[key] for key in ("columns", "row_order", "rows", "evidence")} | {
        "details": spec.get("details") or [], "header": [str(c or "") for c in header],
        "signature": header_signature(header)}


def _refutation(rows):
    """The first cause a reader can act on: a broken chain, then a printed control, before their consequences.

    A summary mismatch marks every transaction too; those marks say nothing about where the reading fails.
    """
    chain = [r for r in rows if r.get("code") == "statement_balance"]
    controls = [r for r in rows if r.get("code") in BROKEN and "amount_cents" not in r and "identity" not in r]
    first = (chain or controls or [r for r in rows if r.get("code") in BROKEN])[0]
    return f"Row {first['row']}: {first['reason']}"


def preview_sheet(entry):
    return {"file": entry["file"]["path"], "sheet": entry["sheet"], "rows": preview(entry["table"])}


def prove(connection, tenant_id, entry, spec, *, today, actor, provenance):
    """Keep a declared layout the balances prove, ask once when they cannot decide, refuse what they refute.

    Returns {"status": "active" | "question" | "known", "profile"} or
    {"status": "refuted", "reason"} with a reason the layout session can act on.
    """
    if spec["header_row"] > len(entry["table"]):
        return {"status": "refuted", "reason": "The header row is beyond the end of the sheet."}
    stored = payload(spec, entry["table"])
    try:
        rows, proof, _ = read(entry, stored, spec["header_row"] - 1, today=today)
    except (ValueError, KeyError, TypeError, IndexError) as error:
        return {"status": "refuted", "reason": f"The layout cannot be applied: {error or 'a column is missing'}."}
    if refuted(rows, proof):
        return {"status": "refuted", "reason": _refutation(rows)}
    if not any(not r.get("code") for r in rows):
        return {"status": "refuted", "reason": "No transaction reads through this layout."}
    # Two sheets in one new format can be proven at once: the second finds the first.
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                       (f"{KIND}:{tenant_id}:{stored['signature']}",))
    existing = profiles.current(connection, tenant_id, KIND, stored["signature"])
    if existing:
        return {"status": "known", "profile": existing}  # another run learned this format meanwhile
    question = "sample" if not proof["amounts"] else None if proof["date_order"] else "date_order"
    profile = profiles.create(connection, tenant_id, KIND, stored["signature"],
                              {**stored, "proof": proof, "question": question},
                              status="proposed" if question else "active",
                              actor=None if question else actor, provenance=provenance)
    if question is None:
        return {"status": "active", "profile": profile}
    # Ask about the printed date, not our reading of it: an ISO date would
    # hide the very ambiguity the member is deciding.
    date_column = stored["columns"]["date"]["column"]
    printed = [cell_text(entry["table"][r["row"] - 1][date_column - 1]) for r in rows if not r.get("code")][:1]
    return {"status": "question", "profile": profile, "question": question, "proof": proof, "printed": printed}


def ask(connection, run, profile, path, question, proof, printed):
    """One Attention card per layout question; the sheet's item waits on it."""
    if question == "date_order":
        title, actions = "Choose date order", ["dmy", "mdy"]
        prompt = f"Dates such as {printed[0] if printed else 'these'} could be day-first or month-first."
    else:
        title, actions = "Confirm statement layout", ["confirm", "nothing"]
        prompt = "These rows could not be checked against running balances. Confirm Minkops reads them correctly."
    return attention.record(connection, run, f"layout:{profile['id']}", path, title, kind="layout", target={
        "profile_id": str(profile["id"]), "question": question, "prompt": prompt, "actions": actions,
        "samples": proof["samples"]})


ANSWERS = {"dmy": "Day first", "mdy": "Month first", "confirm": "Confirm", "nothing": "Do nothing"}


def question(target):
    """The card a person answers: its prompt, sample rows and the offered answers."""
    return {"prompt": target.get("prompt"), "samples": target.get("samples", [])[:3],
            "options": [{"action": action, "label": ANSWERS[action]} for action in target.get("actions", [])]}


def decide(connection, tenant, user, item, action):
    """Answer a layout card, then release every sheet waiting on it."""
    profile = profiles.get(connection, tenant["id"], item["target"]["profile_id"], lock=True)
    if profile is None or profile["status"] != "proposed":
        raise ServiceError("conflict", "This statement layout is no longer awaiting a decision.")
    if action not in item["target"]["actions"]:
        raise ServiceError("invalid", "Choose one of the offered answers.")
    if action == "nothing":
        profiles.decline(connection, profile, "Not confirmed by a member.")
        outcome = "superseded"
    else:
        if action in ("dmy", "mdy"):
            columns = profile["payload"]["columns"]
            profile = profiles.update_payload(connection, profile, {
                **profile["payload"], "question": None,
                "columns": {**columns, "date": {**columns["date"], "order": action}}})
        profiles.confirm(connection, profile, user["id"])
        outcome = "active"
    attention.audit(connection, item, user["id"], "confirmed" if outcome == "active" else "deferred",
                    f"Statement layout {'confirmed' if outcome == 'active' else 'not confirmed'}.")
    connection.execute("UPDATE attention_items SET status='done',done_by=%s,done_at=now(),updated_at=now() WHERE id=%s",
                       (user["id"], item["id"]))
    work.release(connection, tenant["id"], blocker(profile["id"]))
    return {"status": outcome}


def today_for(run):
    """Statements cannot contain transactions after the run was started."""
    created = run.get("created_at")
    return created.date() if created else date.today()
