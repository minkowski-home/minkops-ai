"""Statement layouts: inferred once per bank format, proven by balances, reused.

A layout is identified by its header row (cells and positions), so a statement
from the same bank export matches it after any preamble. The layout stage
proposes one for each unseen sheet; this module applies it to the real file and
activates it only when the running balances prove the amounts and the dates
prove their order. Otherwise a member answers one question (which date order)
or confirms sample rows once. Known layouts parse with no AI call at all.
"""

from collections import Counter
from datetime import date
from pathlib import Path

from psycopg.types.json import Jsonb

from minkops_connectors.statement import (
    apply_layout,
    header_signature,
    preview,
    read_tables,
    signatures,
)
from minkops_platform import attention, profiles
from minkops_platform.errors import ServiceError

KIND = "statement_layout"


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


def resolve(connection, tenant_id, files):
    """Attach each sheet's live layout (by header signature) and where its header sits."""
    entries = sheets(files)
    candidates = {sig: (entry, index) for entry in entries if "table" in entry
                  for sig, index in signatures(entry["table"]).items()}
    live = connection.execute(
        "SELECT * FROM client_profiles WHERE tenant_id=%s AND kind=%s AND scope_key=ANY(%s) AND status IN ('proposed','active')",
        (tenant_id, KIND, list(candidates))).fetchall() if candidates else []
    for profile in sorted(live, key=lambda p: candidates[p["scope_key"]][1]):
        entry, index = candidates[profile["scope_key"]]
        if "profile" not in entry:
            entry.update(profile=profile, header_index=index)
    return entries


def parse(entries, *, today):
    """Canonical rows for every sheet; unknown or unproven layouts hold their sheet."""
    rows, occurrences = [], {}
    for entry in entries:
        file = entry["file"]
        base = {"source_file_id": str(file["id"]), "source_file": file["path"]}
        if entry.get("error"):
            rows.append({**base, "row": 0, "sheet": "", "code": "statement_format", "status": "held",
                         "reason": "Use a readable CSV or XLSX statement; convert legacy XLS files in Excel."})
            continue
        profile = entry.get("profile")
        if not profile or profile["status"] != "active":
            rows.append({**base, "row": 0, "sheet": entry["sheet"], "status": "held",
                         "code": "statement_layout_unknown" if not profile else "statement_layout_unconfirmed",
                         "reason": "Minkops could not read this sheet's layout." if not profile
                         else "This statement layout is waiting for one confirmation in Attention."})
            continue
        counter = occurrences.setdefault(str(file["id"]), Counter())
        parsed, _ = apply_layout(entry["table"], profile["payload"], entry["header_index"], sheet=entry["sheet"],
                                 formulas=entry["formulas"], occurrences=counter, today=today)
        for row in parsed:
            row.update(base, status="held" if row.get("code") else "ready")
            rows.append(row)
    if len(rows) > 10000:
        raise ValueError("Select at most 10,000 transaction rows in one run.")
    return rows


def preview_sheets(connection, tenant_id, files):
    """The new sheets a layout session must read, as bounded text previews."""
    return [{"source_file_id": str(e["file"]["id"]), "path": e["file"]["path"], "sheet": e["sheet"],
             "preview": preview(e["table"])}
            for e in resolve(connection, tenant_id, files) if "table" in e and "profile" not in e]


def sweep(connection):
    """Resume statement runs whose layout session failed; their sheets then hold."""
    for row in connection.execute(
            "SELECT DISTINCT tenant_id FROM workflow_runs WHERE state='queued' AND config->'awaits' ? 'layout_run'").fetchall():
        release(connection, row["tenant_id"])


def _payload(spec, table):
    header = table[spec["header_row"] - 1]
    return {k: spec[k] for k in ("columns", "row_order", "rows", "evidence")} | {
        "header": [str(c or "") for c in header], "signature": header_signature(header)}


def learn(connection, run, result, files, *, today):
    """Store each proposed layout that proves out; ask once when it cannot."""
    entries = {(str(e["file"]["id"]), e["sheet"]): e for e in sheets(files) if "table" in e}
    for spec in result.get("layouts", []):
        entry = entries.get((spec["source_file_id"], spec["sheet"]))
        if entry is None or spec["header_row"] > len(entry["table"]):
            continue
        payload = _payload(spec, entry["table"])
        try:
            rows, proof = apply_layout(entry["table"], payload, spec["header_row"] - 1, sheet=entry["sheet"],
                                       formulas=entry["formulas"], today=today)
        except (ValueError, KeyError, TypeError, IndexError):
            continue
        broken = any(r.get("code") == "statement_balance" for r in rows)
        if payload["columns"].get("balance") and broken and not proof["amounts"]:
            continue  # The balances refute this reading; the sheet holds instead.
        if profiles.current(connection, run["tenant_id"], KIND, payload["signature"]):
            continue  # Another run already learned (or is confirming) this format.
        ambiguous = [r["date"] for r in rows if not r.get("code")][:1]
        question = None if proof["date_order"] else "date_order"
        if not proof["amounts"]:
            question = "sample"
        status = "active" if question is None else "proposed"
        profile = profiles.create(connection, run["tenant_id"], KIND, payload["signature"],
                                  {**payload, "proof": proof, "question": question}, status=status,
                                  actor=run["actor_id"] if status == "active" else None,
                                  provenance={"run_id": str(run["id"]), "file": entry["file"]["path"]})
        if question:
            _card(connection, run, profile, entry["file"]["path"], question, proof, ambiguous)
    release(connection, run["tenant_id"], finished=str(run["id"]))


def _card(connection, run, profile, path, question, proof, ambiguous):
    if question == "date_order":
        title, actions = "Choose date order", ["dmy", "mdy"]
        prompt = (f"Dates such as {ambiguous[0] if ambiguous else 'these'} could be day-first or month-first.")
    else:
        title, actions = "Confirm statement layout", ["confirm", "nothing"]
        prompt = "These rows could not be checked against running balances. Confirm Minkops reads them correctly."
    attention.record(connection, run, f"layout:{profile['id']}", path, title, kind="layout", target={
        "profile_id": str(profile["id"]), "question": question, "prompt": prompt, "actions": actions,
        "samples": proof["samples"]})


def decide(connection, tenant, user, item, action):
    """Answer a layout card: a date order, or confirm/decline sample rows."""
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
            payload = {**profile["payload"], "columns": {**profile["payload"]["columns"],
                       "date": {**profile["payload"]["columns"]["date"], "order": action}}, "question": None}
            connection.execute("UPDATE client_profiles SET payload=%s WHERE id=%s", (Jsonb(payload), profile["id"]))
            profile = {**profile, "payload": payload}
        profiles.confirm(connection, profile, user["id"])
        outcome = "active"
    attention.audit(connection, item, user["id"], "confirmed" if outcome == "active" else "deferred",
                    f"Statement layout {'confirmed' if outcome == 'active' else 'not confirmed'}.")
    connection.execute("UPDATE attention_items SET status='done',done_by=%s,done_at=now(),updated_at=now() WHERE id=%s",
                       (user["id"], item["id"]))
    release(connection, tenant["id"])
    return {"status": outcome}


def release(connection, tenant_id, *, finished=None):
    """Statement runs waiting on layouts resume once none of their formats is still being decided."""
    waiting = connection.execute(
        """SELECT r.id,r.config FROM workflow_runs r WHERE r.tenant_id=%s AND r.state='queued'
        AND r.config->'awaits' ? 'layout_run'""", (tenant_id,)).fetchall()
    for run in waiting:
        child = connection.execute("SELECT state,id FROM workflow_runs WHERE tenant_id=%s AND id::text=%s",
                                   (tenant_id, run["config"]["awaits"]["layout_run"])).fetchone()
        if child and child["state"] not in ("review", "failed") and str(child["id"]) != finished:
            continue
        pending = connection.execute(
            """SELECT 1 FROM client_profiles WHERE tenant_id=%s AND kind=%s AND status='proposed'
            AND provenance->>'run_id'=%s LIMIT 1""", (tenant_id, KIND, str(child["id"]) if child else "")).fetchone()
        if pending:
            continue
        connection.execute("UPDATE workflow_runs SET config=(config-'awaits') || '{\"layouts_attempted\":true}'::jsonb,"
                           "updated_at=now() WHERE id=%s", (run["id"],))


def today_for(run):
    """Statements cannot contain transactions after the run was started."""
    created = run.get("created_at")
    return created.date() if created else date.today()
