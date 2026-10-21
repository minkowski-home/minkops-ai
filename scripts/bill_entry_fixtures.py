"""Score a bill entry run against labelled fixture packages, and report how long it took.

A fixture package holds `bills/*.pdf` and `evidence/expected-bills.json`, whose
answers never reach a model. Against DATABASE_URL:

  score RUN_ID PACKAGE... [--rerun] [--dry]

Each input file is graded by its SHA-256: a correct proposal or save, a hold
for the expected reason, or a failure. Verdicts ending in "!" are critical: a
wrong save or proposal, a missed exception, or a second save. Timing reports
launch to the last file read, each file's session, and the tokens used.

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
from statistics import median

import psycopg
from psycopg.rows import dict_row

# The hold codes that correctly express each labelled reason a bill needs a person.
ATTENTION_CODES = {
    "ambiguous_supplier": {"supplier_unresolved", "company_unresolved", "classification_uncertain"},
    "missing_supplier": {"supplier_missing"},
    "before_books": {"date_before_books"},
    "inventory_required": {"unsupported_structure"},
    # Two files holding both versions hold together; one meeting the saved version is held at its save.
    "conflicting_version": {"source_values_conflict", "save_held"},
}
PROPOSED = ("proposed", "approved", "writing")


def load_expected(packages):
    """Expected bills by input SHA-256, normalized across both package formats."""
    bills = {}
    for package in packages:
        for bill in json.loads((Path(package) / "evidence/expected-bills.json").read_text()):
            bill["supplier"] = bill.get("vendor") or bill.get("supplier")
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


def normalized(value):
    return " ".join(str(value or "").split()).casefold()


# --- score ------------------------------------------------------------------


def grade(bill, records, *, rerun=False, dry=False):
    """(verdict, detail) for one input file's bills; verdicts ending in '!' are critical.

    In a dry (All outputs) run nothing is saved, so outcomes Tally decides, such
    as a duplicate or a correction, are unobservable: a correct proposal passes.
    """
    want = "duplicate" if rerun and bill["expected"] == "create" else bill["expected"]
    statuses = [record["status"] for record in records]
    codes = {code for record in records for code in record["hold_codes"]}
    proposed = [record for record in records if record["status"] in PROPOSED]
    if rerun and "saved" in statuses:
        return "double_save!", "a rerun created another voucher"
    if want == "attention":
        if "saved" in statuses:
            return "missed_exception!", f"saved; expected {bill['case']}"
        if codes & ATTENTION_CODES.get(bill["case"], set()):
            return "correct", f"codes {sorted(codes)}"
        if bill["case"] == "conflicting_version" and dry and len(proposed) == 1 and not compare(bill, proposed[0]):
            return "correct_ready", "the saved version is met at save"
        if proposed:
            return "missed_exception!", f"proposed; expected {bill['case']}"
        return "wrong_reason", f"codes {sorted(codes)}"
    if len(records) != 1:
        return "wrong_count", f"{len(records)} bills read from one labelled bill"
    record = records[0]
    mismatch = compare(bill, record)
    if record["status"] in ("saved", "duplicate"):
        if mismatch:
            return "wrong_save!", "; ".join(mismatch)
        if record["status"] != {"create": "saved"}.get(want, want) and not bill.get("pair"):
            return "unexpected_" + record["status"], ""
        return "correct", record["status"]
    if record["status"] in PROPOSED:
        if mismatch:
            return "wrong_proposal!", "; ".join(mismatch)
        return "correct_ready", "; ".join(record["review_reasons"])
    reason = " ".join(record["review_reasons"])
    if record["hold_codes"] in (["rejected"], ["save_held"]) and "date" in reason.lower() and not mismatch:
        return "correct_date_only", reason[:120]
    return "unnecessary_hold", f"{record['status']} {sorted(codes)} {reason[:160]}" + (
        f" | {'; '.join(mismatch)}" if mismatch else "")


def compare(bill, record):
    """Mismatches between a record's proposed voucher and its label."""
    preview = (record.get("proposal") or {}).get("preview") or {}
    problems = []
    for field, label in (("number", "invoice_number"), ("date", "date"), ("party", "supplier")):
        if normalized(preview.get(field)) != normalized(bill.get(label)):
            problems.append(f"{field} {preview.get(field)!r} != {bill.get(label)!r}")
    if preview.get("total") is None or money(preview["total"]) != money(bill["total"]):
        problems.append(f"total {preview.get('total')} != {bill['total']}")
    # The labelled purchase and tax lines are the voucher's debit lines, beside at most a rupee of round-off.
    debits = {line["ledger"]: money(line["amount"]) for line in preview.get("lines", []) if line["side"] == "debit"}
    expected = {bill["purchase_ledger"]: money(bill["subtotal"]),
                **{line["ledger"]: money(line["amount"]) for line in bill["tax_allocations"]}}
    extra = {ledger: amount for ledger, amount in debits.items() if ledger not in expected}
    if {ledger: debits.get(ledger) for ledger in expected} != expected or any(v > 1 for v in extra.values()):
        problems.append(f"debit lines {debits} != {expected}")
    if record.get("company_guid") not in (None, bill["company_guid"]):
        problems.append("company")
    entries = (record.get("current") or {}).get("entries")
    if entries:
        taxes = {line["ledger"]: -int(money(line["amount"]) * 100) for line in bill["tax_allocations"]}
        observed = {e["ledger"]: e["amount"] for e in entries if e["ledger"] in taxes or "GST" in e["ledger"]}
        if observed != taxes:
            problems.append(f"tax lines {observed} != {taxes}")
    return problems


def _duration(seconds):
    minutes, seconds = divmod(round(seconds), 60)
    return f"{minutes}m{seconds:02d}s"


def timing(run, items):
    """Launch to the last file read, each file's session, and the tokens the sessions used."""
    finished = [item["finished_at"] for item in items if item["finished_at"]]
    sessions = [(item["finished_at"] - item["started_at"]).total_seconds() for item in items
                if item["finished_at"] and item["started_at"]]
    usage = Counter()
    for item in items:
        for key, value in (item["usage"] or {}).items():
            if isinstance(value, int):
                usage[key] += value
        usage["cached"] += ((item["usage"] or {}).get("input_tokens_details") or {}).get("cached_tokens", 0)
    read = _duration((max(finished) - run["created_at"]).total_seconds()) if len(finished) == len(items) else "not yet"
    spread = f"p50 {_duration(median(sessions))}, max {_duration(max(sessions))}" if sessions else "none"
    return (f"Read {len(finished)} of {len(items)} files in {read} from launch (sessions {spread}); tokens: "
            f"input {usage['input_tokens']} ({usage['cached']} cached), output {usage['output_tokens']}.")


def score(url, run_id, expected, *, rerun=False, dry=False):
    with psycopg.connect(url, row_factory=dict_row) as connection:
        run = connection.execute("SELECT * FROM runs WHERE id=%s", (run_id,)).fetchone()
        items = connection.execute(
            """SELECT i.*, f.path, f.sha256 FROM run_items i JOIN account_files f
               ON f.tenant_id=i.tenant_id AND f.id::text=i.source->>'file_id'
               WHERE i.run_id=%s ORDER BY i.ordinal""", (run_id,)).fetchall()
        records = connection.execute(
            """SELECT r.*, c.guid AS company_guid FROM run_records r LEFT JOIN companies c ON c.id=r.company_id
               WHERE r.run_id=%s ORDER BY r.item_id, r.position""", (run_id,)).fetchall()
    rows, verdicts, outcomes = [], Counter(), []
    for item in items:
        bill = expected.get(item["sha256"])
        if bill is None:
            rows.append((item["path"], "-", "unlabelled", ""))
            continue
        mine = [record for record in records if record["item_id"] == item["id"]]
        if item["state"] == "failed" and not any(record["status"] != "held" for record in mine):
            verdict, detail = "failed!", (item["error"] or "")[:160]
        else:
            verdict, detail = grade(bill, mine, rerun=rerun, dry=dry)
        verdicts[verdict] += 1
        outcomes.append((bill, mine[0]["status"] if mine else None))
        rows.append((bill["file"], bill["expected"], verdict, detail))
    saved = Counter(bill["pair"] for bill, status in outcomes if bill.get("pair") and status == "saved")
    for pair, count in saved.items():
        if count > 1:
            verdicts["double_save!"] += 1
            rows.append((f"pair {pair}", "one save", "double_save!", f"{count} saves"))
    for row in rows:
        print(" | ".join(map(str, row)))
    total = sum(verdicts.values())
    passed = sum(n for verdict, n in verdicts.items() if verdict.startswith("correct"))
    print(f"\nRun {run_id} ({run['state']}, {run['config'].get('review_mode')}): {passed}/{total} pass; "
          + ", ".join(f"{verdict} {n}" for verdict, n in sorted(verdicts.items())))
    print(timing(run, items))
    return 1 if any(verdict.endswith("!") for verdict in verdicts) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("score",))
    parser.add_argument("run_id")
    parser.add_argument("packages", nargs="+")
    parser.add_argument("--rerun", action="store_true", help="Inputs were already saved; expect duplicates.")
    parser.add_argument("--dry", action="store_true", help="All outputs run: grade proposals before saving.")
    args = parser.parse_args()
    return score(os.environ["DATABASE_URL"], args.run_id, load_expected(args.packages), rerun=args.rerun, dry=args.dry)


if __name__ == "__main__":
    sys.exit(main())
