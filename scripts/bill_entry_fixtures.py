"""Score Bill Entry runs against labelled local fixture packages.

A fixture package holds `bills/*.pdf` and `evidence/expected-bills.json`, whose
answers never reach a model. Against DATABASE_URL:

  score RUN_ID PACKAGE...   Grade a finished run per input and print totals.

Educational Tally only accepts vouchers dated the 1st, 2nd or 31st. A bill held
solely because Tally refused its date is scored as passing.
"""

import argparse
import json
import os
import sys
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
    "before_books": {"date_before_books"},
    "inventory_required": {"unsupported_structure"},
}


def load_expected(packages):
    """Expected bills by input SHA-256, normalized across both package formats."""
    bills = {}
    for package in packages:
        for bill in json.loads((Path(package) / "evidence/expected-bills.json").read_text()):
            guids = bill.get("master_guids") or {}
            bill["vendor"] = bill.get("vendor") or bill.get("supplier")
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
    """Mismatches between a proposal's document summary and native lines and its label."""
    data, problems = record["data"], []
    for field in ("invoice_number", "date", "vendor"):
        if data.get(field) != bill.get(field):
            problems.append(f"{field} {data.get(field)!r} != {bill.get(field)!r}")
    for field in ("tax", "total"):
        if data.get(field) is None or money(data[field]) != money(bill[field]):
            problems.append(f"{field} {data.get(field)} != {bill[field]}")
    # The labelled purchase and tax lines are exactly the voucher's debit lines.
    debits = {line["ledger"]: money(line["amount"]) for line in (record.get("preview") or {}).get("lines", [])
              if line["side"] == "debit"}
    expected = {bill["purchase_ledger"]: money(bill["subtotal"]),
                **{line["ledger"]: money(line["amount"]) for line in bill["tax_allocations"]}}
    if debits != expected:
        problems.append(f"debit lines {debits} != {expected}")
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
    parser.add_argument("command", choices=("score",))
    parser.add_argument("run_id")
    parser.add_argument("packages", nargs="+")
    parser.add_argument("--rerun", action="store_true", help="Inputs were already saved; expect duplicates.")
    parser.add_argument("--dry", action="store_true", help="All outputs run: grade proposals before saving.")
    args = parser.parse_args()
    return score(args.run_id, load_expected(args.packages), args.rerun, args.dry)


if __name__ == "__main__":
    sys.exit(main())
