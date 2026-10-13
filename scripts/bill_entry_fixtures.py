"""Replay and score Bill Entry runs against labelled local fixture packages.

A fixture package holds `bills/*.pdf` and `evidence/expected-bills.json`, whose
answers never reach a model. Two commands, both against DATABASE_URL:

  score RUN_ID PACKAGE...   Grade a finished run per input and print totals.
  replay RUN_ID PACKAGE...  Process the run's queued bills with the expected
                            answer instead of a hosted session.

Replay exercises everything after extraction: output validation, master
selection, aggregation, attention, review mode and the companion's native
read-first save. Stop the normal worker first, so no paid session claims the
same run. Unrelated queued runs are never touched.

Educational Tally only accepts vouchers dated the 1st, 2nd or 31st. A bill held
solely because Tally refused its date is scored as passing.
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DATABASE = os.environ["DATABASE_URL"]
# Expected attention outcomes and the exception codes that correctly express them.
ATTENTION_CODES = {
    "conflicting_version": {"correction"},
    "ambiguous_supplier": {"supplier_unresolved", "company_unresolved", "classification_uncertain"},
    "missing_supplier": {"supplier_missing"},
    "separate_round_off": {"unsupported_structure", "source_values_conflict"},
}


def load_expected(packages):
    """Expected bills by input SHA-256, normalized across both package formats."""
    bills = {}
    for package in packages:
        for bill in json.loads((Path(package) / "evidence/expected-bills.json").read_text()):
            guids = bill.get("master_guids") or {}
            bill["vendor_guid"] = bill.get("vendor_guid") or guids.get("vendor")
            bill["purchase_guid"] = bill.get("purchase_guid") or guids.get("purchase_ledger")
            bill["package"] = Path(package).name
            bills[bill["sha256"]] = bill
    # Two copies of one bill in a batch: whichever is processed first is saved.
    for bill in bills.values():
        if bill.get("duplicate_of") is not None:
            pair = (bill["package"], bill["duplicate_of"])
            bill["pair"] = pair
            for other in bills.values():
                if (other["package"], other["id"]) == pair:
                    other["pair"] = pair
    return bills


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


# --- replay -----------------------------------------------------------------


def replay_output(bill, file_id, target):
    """The output a correct agent returns for this bill under the 0.12 contract."""
    company = next(c for c in target["companies"] if c["references"]["company_guid"] == bill["company_guid"])
    refs = {master["identity"]["GUID"]: ref for ref, master in company["ledger_refs"].items()}

    def pick(guid, basis):
        return {"ref": refs[guid], "evidence": basis} if guid else {"ref": None, "evidence": basis}

    case = bill.get("case", "")
    data = {"invoice_number": bill["invoice_number"], "vendor": None, "date": bill["date"],
            "purchase_ledger": None, "subtotal": float(bill["subtotal"]), "tax": float(bill["tax"]),
            "tax_ledger": None, "total": float(bill["total"]), "cost_code": None}
    record = {
        "source_file_id": file_id, "destination_file_id": target["discovery_id"], "sheet": "Purchase",
        "table": None, "operation": "append", "data": data, "exceptions": [], "notes": [],
        "company_guid": bill["company_guid"],
        "company_evidence": f"Buyer printed as {bill.get('printed_buyer') or bill['company']}.",
        "master_refs": {
            "vendor": pick(bill["vendor_guid"], "Supplier name and identifiers match this master."),
            "purchase_ledger": pick(bill["purchase_guid"], "Bill purpose matches independent history."),
            "tax_ledger": None,
        },
    }
    if Decimal(bill["tax"]):
        record["tax_allocations"] = [
            {"ref": refs[line["guid"]], "amount": float(line["amount"]), "evidence": f"Printed {line['label']}."}
            for line in bill["tax_allocations"]]
    created = next((ref for ref, master in company["ledger_refs"].items()
                    if case == "missing_supplier" and master["name"] == bill["supplier"]), None)
    if created:
        # On a rerun after Create this ledger, the supplier is an existing master.
        record["master_refs"]["vendor"] = {"ref": created, "evidence": "Printed supplier matches this master."}
    elif case == "missing_supplier":
        data["vendor"] = bill["supplier"]
        record["master_refs"]["vendor"] = {"ref": None, "new_supplier": True,
                                           "evidence": "No discovered ledger matches the printed supplier."}
        record["exceptions"].append({"code": "supplier_missing", "detail": "Printed supplier has no ledger."})
    elif case == "ambiguous_supplier":
        record["exceptions"].append({"code": "supplier_unresolved",
                                     "detail": "Printed name matches two supplier ledgers."})
    elif case == "separate_round_off":
        record["exceptions"].append({"code": "unsupported_structure",
                                     "detail": f"Separate printed round-off of {bill['round_off']}."})
    # Ledger fields are filled from master_refs but still quote the bill text.
    printed = {"vendor": bill.get("printed_supplier") or bill.get("printed_vendor") or bill.get("supplier")
               or bill.get("vendor"),
               "purchase_ledger": bill["lines"][0]["description"] if bill.get("lines") else None}
    record["evidence"] = [{"field": field, "page": 1, "quote": str(value)}
                          for field, value in {**data, **printed}.items() if value is not None]
    return {"records": [record], "exceptions": [], "notes": [], "unresolved": []}


def replay(run_id, expected):
    from minkops_platform.accounts.batch import reconcile_once
    from minkops_platform.accounts.run_store import AccountsRunStore
    from minkops_platform.accounts.worker import process
    from minkops_platform.runtime import lifecycle

    class RunOnly(AccountsRunStore):
        """Claims only this run and its children."""
        def candidates(self, connection):
            return [r for r in super().candidates(connection)
                    if run_id in (str(r["id"]), str(r.get("parent_run_id")))]

    def executor(key, files, context, on_event, **_):
        selected = context["config"]["file_ids"]
        source = next(f for f in files if str(f["id"]) in selected)
        bill = expected.get(source["sha256"])
        if bill is None:
            raise ValueError(f"No expected answer for {source['path']}.")
        return replay_output(bill, str(source["id"]), context["config"]["tally_target"])

    store = RunOnly()
    while True:
        reconcile_once(DATABASE)
        worked = lifecycle.work_once(DATABASE, store, lambda c, r: process(c, r, executor=executor))
        with psycopg.connect(DATABASE, row_factory=dict_row) as connection:
            state = connection.execute("SELECT state FROM account_runs WHERE id=%s", (run_id,)).fetchone()["state"]
        if not worked and state not in ("queued", "executing"):
            print(f"Run {run_id} is {state}.")
            return
        if not worked:
            time.sleep(1)


# --- score ------------------------------------------------------------------


def grade(bill, records, issue, deferred, rerun, dry=False):
    """(verdict, detail) for one input; verdicts ending in '!' are critical.

    In a dry (All outputs) run nothing is saved, so native outcomes such as a
    duplicate or a correction are unobservable: a clean, correct proposal passes.
    """
    want = "duplicate" if rerun and bill["expected"] == "create" else bill["expected"]
    statuses = [r.get("status") for r in records]
    codes = {c for r in records for c in r.get("exception_codes", [])} | ({issue.get("code")} if issue else set())
    ready = len(records) == 1 and not records[0].get("findings") and not issue and statuses[0] in (None, "pending")
    if dry and ready and (want != "attention" or bill["case"] == "conflicting_version"):
        mismatch = compare(bill, records[0])
        return ("wrong_proposal!", "; ".join(mismatch)) if mismatch else ("correct_ready", "")
    if rerun and "saved" in statuses:
        return "double_save!", "a rerun created another voucher"
    if rerun and want == "attention" and statuses == ["duplicate"] and bill["case"] in (
            "missing_supplier", "conflicting_version"):
        return "correct", "resolved by its decision; now a duplicate"
    if want == "attention":
        if any(s in ("saved",) for s in statuses):
            return "missed_exception!", f"saved; expected {bill['case']}"
        if bill["case"] == "conflicting_version":
            held = any(r.get("current") and r.get("status") == "held" for r in records)
            return ("correct" if held else "wrong_reason"), "correction held" if held else f"codes {sorted(codes)}"
        ok = codes & ATTENTION_CODES.get(bill["case"], set())
        return ("correct" if ok else "wrong_reason"), f"codes {sorted(codes)}" + (" (deferred)" if deferred else "")
    if not records:
        return "unnecessary_hold", f"unresolved: {issue.get('code') if issue else 'no output'} {issue.get('reason', '')[:120] if issue else ''}"
    record = records[0]
    mismatch = compare(bill, record)
    if record.get("status") in ("saved", "duplicate"):
        if mismatch:
            return "wrong_save!", "; ".join(mismatch)
        if record["status"] != {"create": "saved"}.get(want, want) and not bill.get("pair"):
            return "unexpected_" + record["status"], ""
        return "correct", record["status"]
    hold = record.get("save_hold") or " ".join(record.get("findings", []))
    if "date" in hold.lower() and not mismatch and not record.get("exception_codes"):
        return "correct_date_only", hold[:120]
    return "unnecessary_hold", f"{record.get('status')} {sorted(codes)} {hold[:160]}" + (f" | {'; '.join(mismatch)}" if mismatch else "")


def compare(bill, record):
    data, problems = record["data"], []
    for field in ("invoice_number", "date", "vendor", "purchase_ledger"):
        if data.get(field) != bill.get(field):
            problems.append(f"{field} {data.get(field)!r} != {bill.get(field)!r}")
    for field in ("subtotal", "tax", "total"):
        if data.get(field) is None or money(data[field]) != money(bill[field]):
            problems.append(f"{field} {data.get(field)} != {bill[field]}")
    if record.get("company_guid") not in (None, bill["company_guid"]):
        problems.append("company")
    entries = (record.get("current") or {}).get("entries")
    if entries:
        expected = {line["ledger"]: -int(money(line["amount"]) * 100) for line in bill["tax_allocations"]}
        actual = {e["ledger"]: e["amount"] for e in entries if e["ledger"] in expected or "GST" in e["ledger"]}
        if actual != expected:
            problems.append(f"tax lines {actual} != {expected}")
    return problems


def score(run_id, expected, rerun, dry=False):
    with psycopg.connect(DATABASE, row_factory=dict_row) as connection:
        run = connection.execute("SELECT * FROM account_runs WHERE id=%s", (run_id,)).fetchone()
        files = {str(f["id"]): f for f in connection.execute(
            "SELECT id,path,sha256 FROM account_files WHERE id = ANY(%s::uuid[])", (run["file_ids"],))}
        failed = {c["file_ids"][0]: c["error"] for c in connection.execute(
            "SELECT file_ids,error FROM account_runs WHERE parent_run_id=%s AND state='failed'", (run_id,))}
    result = run["result"] or {}
    rows, verdicts, outcomes = [], Counter(), []
    for file_id in run["file_ids"]:
        bill = expected.get(files[file_id]["sha256"])
        if bill is None:
            rows.append((files[file_id]["path"], "-", "unlabelled", ""))
            continue
        records = [r for r in result.get("records", []) if r["source_file_id"] == file_id]
        issue = next((i for i in result.get("unresolved", []) if i["source_file_id"] == file_id), None)
        deferred = any(i["source_file_id"] == file_id for i in result.get("deferred", []))
        if file_id in failed and not records:
            verdict, detail = "failed!", (failed[file_id] or "")[:160]
        else:
            verdict, detail = grade(bill, records, issue, deferred, rerun, dry)
        verdicts[verdict] += 1
        outcomes.append((bill, verdict, records[0].get("status") if records else None))
        rows.append((bill["file"], bill["expected"], verdict, detail))
    saved = Counter(bill["pair"] for bill, verdict, status in outcomes if bill.get("pair") and status == "saved")
    for pair, count in saved.items():
        if count > 1:
            verdicts["double_save!"] += 1
            rows.append((f"pair {pair}", "one save", "double_save!", f"{count} saves"))
    for row in rows:
        print(" | ".join(map(str, row)))
    total = sum(verdicts.values())
    passed = sum(n for k, n in verdicts.items() if k.startswith("correct"))
    print(f"\nRun {run_id} ({run['state']}, {run['config'].get('review_mode')}): "
          f"{passed}/{total} pass; " + ", ".join(f"{k} {v}" for k, v in sorted(verdicts.items())))
    return 1 if any(k.endswith("!") for k in verdicts) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("score", "replay"))
    parser.add_argument("run_id")
    parser.add_argument("packages", nargs="+")
    parser.add_argument("--rerun", action="store_true", help="Inputs were already saved; expect duplicates.")
    parser.add_argument("--dry", action="store_true", help="All outputs run: grade proposals before saving.")
    args = parser.parse_args()
    expected = load_expected(args.packages)
    if args.command == "replay":
        replay(args.run_id, expected)
        return 0
    return score(args.run_id, expected, args.rerun, args.dry)


if __name__ == "__main__":
    sys.exit(main())
