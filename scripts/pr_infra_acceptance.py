"""Offline acceptance checks for the locally generated PR Infra UAT pack.

No fixture answers, customer documents or credentials are checked into Git.
`verify PACKAGE --statement FILE` checks the nine local PDFs and proves the
original ICICI statement through a declared layout including footer controls.
`score PACKAGE EXPORT.json --phase initial|follow-up|exceptions` grades a
read-only export shaped as {"run": <public run>, "files": [{id,path,sha256}]}.
It never launches AI, approves a decision or writes to a business system.
"""

import argparse
import hashlib
import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from minkops_connectors.statement import apply_layout, read_tables

PHASES = {"initial": ("B01", "B02", "B03"), "follow-up": ("B04", "B05"),
          "exceptions": ("B06", "B07", "B08", "B09")}
HOLDS = {"B05": {"correction"}, "B06": {"source_values_conflict"},
         "B07": {"company_unresolved"}, "B08": {"date_before_books"}}


def expected_bills(package):
    records = json.loads((Path(package) / "Evidence/expected-bills.json").read_text())
    return {record["id"].split("-", 1)[0]: record for record in records}


def icici_layout():
    """Explicit bank-format test declaration, not a production layout guess."""
    return {"columns": {"date": {"column": 4, "order": "dmy"},
            "amount": {"mode": "debit_credit", "debit": 8, "credit": 9},
            "balance": {"column": 10}, "reference": {"column": 2},
            "narration": {"columns": [6, 7]}, "account": None, "routing_hint": None},
            "row_order": "oldest_first", "rows": {
                "ends_at": [{"column": 1, "starts_with": "Page Total"}],
                "summary": [{"kind": kind, "column": 1, "starts_with": label, "value_column": 2}
                            for kind, label in (("opening", "Opening Bal:"), ("debit", "Withdrawls:"),
                                                ("credit", "Deposits:"), ("closing", "Closing Bal:"))]}}


def prove_statement(path):
    content = Path(path).read_bytes()
    sheets = []
    for name, table, formulas in read_tables(content, Path(path).suffix.lower()):
        rows, proof = apply_layout(table, icici_layout(), 16, sheet=name, formulas=formulas)
        assert rows and not any(row.get("code") for row in rows), "Statement reading or control proof failed."
        assert proof["amounts"] and proof["date_order"] and proof["summary"], "Statement proof incomplete."
        sheets.append({"sheet": name, "rows": len(rows), "payments": sum(r["amount_cents"] < 0 for r in rows),
                       "receipts": sum(r["amount_cents"] > 0 for r in rows),
                       "withdrawal_cents": sum(max(-r["amount_cents"], 0) for r in rows),
                       "deposit_cents": sum(max(r["amount_cents"], 0) for r in rows),
                       "opening_cents": rows[0]["balance_cents"] - rows[0]["amount_cents"],
                       "closing_cents": rows[-1]["balance_cents"],
                       "educational_date_rows": sum(date.fromisoformat(r["date"]).day in (1, 2, 31) for r in rows)})
    return {"sha256": hashlib.sha256(content).hexdigest(), "sheets": sheets}


def verify(package, statement=None):
    expected = expected_bills(package)
    assert set(expected) == {f"B{i:02}" for i in range(1, 10)}, "Expected exactly B01–B09."
    hashes = {}
    for key, bill in expected.items():
        content = (Path(package) / bill["file"]).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        assert digest == bill["sha256"], f"Fixture content changed: {key}"
        assert datetime.strptime(bill["date"], "%d-%b-%Y").day in (1, 2, 31), f"Educational date invalid: {key}"
        hashes[key] = digest
    assert hashes["B01"] == hashes["B04"] and hashes["B09"] != hashes["B01"]
    assert expected["B01"]["invoice_number"] == expected["B05"]["invoice_number"]
    assert expected["B01"]["total"] != expected["B05"]["total"]
    output = {"verified_bill_files": len(expected), "phases": PHASES}
    if statement:
        output["statement"] = prove_statement(statement)
    return output


def grade(case, bill, records, unresolved, *, allow_policy_holds=False):
    """An explicit expected hold is a success; an unexplained hold is not."""
    codes = {code for row in records for code in row.get("exception_codes", [])}
    codes.update(row["code"] for row in [*records, *unresolved] if row.get("code"))
    statuses = {row.get("status") for row in records}
    if len(records) > 1:
        return False, "One source invoice produced multiple proposals."
    if case in HOLDS:
        ok = "saved" not in statuses and bool(codes & HOLDS[case])
        return ok, f"Expected hold {sorted(HOLDS[case])}; got {sorted(codes)}."
    if case == "B02" and allow_policy_holds and codes & {"unsupported_structure", "classification_uncertain"}:
        return "saved" not in statuses, "Explicit accounting/inventory policy hold; not a happy-path save."
    if len(records) != 1:
        return False, "Expected one invoice proposal."
    row = records[0]
    document, data = row.get("document") or {}, row.get("data") or {}
    number = document.get("number", data.get("invoice_number"))
    total = document.get("total", data.get("total"))
    source_date = document.get("date", data.get("date"))
    tax = data.get("tax")
    if tax is None and row.get("voucher"):
        tax = sum(Decimal(str(line["amount"])) for line in row["voucher"].get("lines", []) if line.get("role") == "tax")
    expected_date = datetime.strptime(bill["date"], "%d-%b-%Y").date().isoformat()
    if (number != bill["invoice_number"] or source_date != expected_date or total is None
            or Decimal(str(total)) != Decimal(bill["total"])):
        return False, "Invoice number, source date or printed total differs."
    if bill.get("tax") is not None and (tax is None or Decimal(str(tax)) != Decimal(bill["tax"])):
        return False, "Tax allocation total differs."
    if case in ("B04", "B09"):
        return statuses == {"duplicate"}, f"Expected duplicate after B01 save; got {sorted(str(s) for s in statuses)}."
    if case == "B03":
        ok = "supplier_missing" in codes and "supplier" in row.get("allowed_actions", []) and "saved" not in statuses
        return ok, "Expected missing supplier with an eligible Create Ledger decision before any write."
    ok = not codes and not row.get("findings") and not row.get("save_hold")
    return ok, "Expected a clean supported proposal or verified save."


def score(package, export, phase, *, allow_policy_holds=False):
    expected, result = expected_bills(package), export["run"].get("result") or {}
    files = {str(file["id"]): file for file in export["files"]}
    rows = []
    for case in PHASES[phase]:
        bill = expected[case]
        found = [key for key, file in files.items() if Path(file["path"].replace("\\", "/")).name == Path(bill["file"]).name]
        if len(found) != 1:
            rows.append({"case": case, "passed": False, "detail": "Expected exactly one selected input file."})
            continue
        file_id = found[0]
        assert files[file_id]["sha256"] == bill["sha256"], "Run used a changed fixture."
        records = [r for r in result.get("records", []) if r["source_file_id"] == file_id]
        unresolved = [r for r in result.get("unresolved", []) if r["source_file_id"] == file_id]
        passed, detail = grade(case, bill, records, unresolved, allow_policy_holds=allow_policy_holds)
        rows.append({"case": case, "passed": passed, "detail": detail})
    return {"phase": phase, "outcomes": rows, "counts": dict(Counter("passed" if r["passed"] else "failed" for r in rows))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("verify")
    check.add_argument("package")
    check.add_argument("--statement")
    run = sub.add_parser("score")
    run.add_argument("package")
    run.add_argument("export")
    run.add_argument("--phase", choices=PHASES, required=True)
    run.add_argument("--allow-policy-holds", action="store_true")
    args = parser.parse_args()
    output = (verify(args.package, args.statement) if args.command == "verify" else
              score(args.package, json.loads(Path(args.export).read_text()), args.phase,
                    allow_policy_holds=args.allow_policy_holds))
    print(json.dumps(output, indent=2))
    return int(bool(output.get("counts", {}).get("failed")))


if __name__ == "__main__":
    raise SystemExit(main())
