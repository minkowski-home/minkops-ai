"""Author disposable Tally rehearsal data; never connect to or change Tally.

Usage: python scripts/prepare_tally_demo.py --snapshot baseline.json --output DIR
PDF dependencies are development-only: reportlab, pypdf and pypdfium2.
The separate opt-in seed_tally_demo.mjs imports the reviewed seed-plan.json.
"""

import argparse
import copy
import hashlib
import json
import re
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

PREFIX = "QA18"
SPECS = [
    (
        "Modular Cabins",
        "Portable Site Cabins",
        "94060019",
        "Nos",
        18,
        False,
        [
            ("MS fabricated office cabin 20 x 8 ft", 1, 156000),
            ("Electrical fit-out kit", 1, 12500),
            ("Weatherproof flooring", 1, 8500),
            ("Site erection and unloading", 1, 6500),
        ],
    ),
    (
        "Siddhi Plant Spares",
        "Plant Repairs",
        "84314930",
        "Nos",
        18,
        False,
        [
            ("Tooth point PC-200 RC", 50, 850),
            ("Tooth lock PC-200 black", 50, 110),
            ("Adapter sleeve 35 mm", 12, 640),
            ("Bucket pin kit", 4, 1450),
            ("Seal and O-ring set", 6, 375),
            ("Grease nipple assortment", 20, 42),
        ],
    ),
    (
        "Deccan Steel",
        "Structural Steel",
        "72142090",
        "MT",
        18,
        True,
        [
            ("TMT bar Fe500D 12 mm", 2.375, 56400),
            ("TMT bar Fe500D 16 mm", 1.625, 55800),
            ("Binding wire annealed", 0.15, 68400),
            ("MS channel 100 mm", 0.875, 58900),
        ],
    ),
    (
        "Granite Aggregates",
        "Aggregates",
        "25171010",
        "MT",
        5,
        False,
        [
            ("Crushed aggregate 20 mm", 24.5, 945),
            ("Crushed aggregate 40 mm", 18.75, 880),
            ("Manufactured sand Zone II", 22.125, 760),
            ("Stone dust graded", 8.625, 540),
        ],
    ),
    (
        "Coastal Equipment Hire",
        "Equipment Hire",
        "997313",
        "Day",
        18,
        False,
        [
            ("Excavator hire PC200 - shift A", 8, 11500),
            ("Excavator hire PC200 - shift B", 4, 11500),
            ("Hydraulic breaker attachment hire", 5, 2400),
            ("Standby authorised hours", 2, 900),
            ("Operator attendance allowance", 12, 650),
            ("Mobilisation charge", 1, 4500),
        ],
    ),
    (
        "Transit Logistics",
        "Freight",
        "996511",
        "Trip",
        0,
        False,
        [
            ("Closed-body truck - route A", 2, 8400),
            ("Flatbed movement - route B", 1, 12600),
            ("Loading gang service", 3, 1200),
            ("Toll reimbursement at cost", 1, 960),
        ],
    ),
    (
        "Cement Depot",
        "Cement",
        "25232930",
        "Bag",
        12,
        False,
        [
            ("OPC 53 grade cement lot A", 240, 315),
            ("PPC cement lot B", 180, 292),
            ("Rapid hardening cement lot C", 80, 352),
            ("Sulphate resistant cement lot D", 60, 385),
        ],
    ),
]


def money(value):
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def identifier(company_guid, kind, name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"minkops/{PREFIX}/{company_guid}/{kind}/{name}"))


def tax_lines(base, rate, interstate):
    if not rate:
        return []
    rate = Decimal(str(rate)) / (1 if interstate else 2)
    return [
        {
            "ledger": f"{PREFIX} Input {label} {rate.normalize()}%",
            "label": label,
            "rate": str(rate),
            "amount": money(Decimal(base) * rate / 100),
        }
        for label in (["IGST"] if interstate else ["CGST", "SGST"])
    ]


def make_bill(
    company, spec_index, number, invoice, *, case="new", expected="create", issued="2026-10-01"
):
    supplier, purchase, hsn, unit, rate, interstate, rows = SPECS[spec_index]
    lines = []
    for index, (description, qty, price) in enumerate(rows):
        unit_price = Decimal(str(price)) + company["ordinal"] * Decimal("1.25")
        gross = Decimal(str(qty)) * unit_price
        # An explicit per-line trade discount tests gross vs taxable extraction.
        discount = Decimal("125.00") if index == 0 else Decimal("0.00")
        lines.append(
            {
                "description": description,
                "hsn": hsn,
                "qty": str(qty),
                "unit": unit,
                "rate": money(unit_price),
                "gross": money(gross),
                "discount": money(discount),
                "net": money(Decimal(money(gross)) - discount),
            }
        )
    subtotal = money(sum(Decimal(line["net"]) for line in lines))
    taxes = tax_lines(subtotal, rate, interstate)
    tax = money(sum(Decimal(t["amount"]) for t in taxes))
    return {
        "id": number,
        "company": company["company"],
        "company_guid": company["company_guid"],
        "invoice_number": invoice,
        "date": issued,
        "supplier": f"{PREFIX} {supplier}",
        "printed_supplier": f"{PREFIX} {supplier}",
        "purchase_ledger": f"{PREFIX} {purchase}",
        "lines": lines,
        "subtotal": subtotal,
        "tax_allocations": taxes,
        "tax": tax,
        "total": money(Decimal(subtotal) + Decimal(tax)),
        "round_off": "0.00",
        "case": case,
        "expected": expected,
        "interstate": interstate,
        "scan": spec_index == 1,
        "printed_buyer": company["company"],
    }


def purchase_voucher(company, bill, *, inventory=False):
    entries = [
        {"ledger": bill["supplier"], "amount": bill["total"]},
        {"ledger": bill["purchase_ledger"], "amount": money(-Decimal(bill["subtotal"]))},
    ]
    entries.extend(
        {"ledger": t["ledger"], "amount": money(-Decimal(t["amount"]))}
        for t in bill["tax_allocations"]
    )
    return {
        "guid": identifier(company["company_guid"], "voucher", bill["invoice_number"]),
        "type": "Purchase",
        "date": bill["date"],
        "reference": bill["invoice_number"],
        "party": bill["supplier"],
        "entries": entries,
        "inventory": inventory,
        "stock_item": f"{PREFIX} Excavator Wear Kit" if inventory else None,
    }


def build_company(source, ordinal):
    company = {
        "company": source["company"],
        "company_guid": source["company_guid"],
        "ordinal": ordinal,
        "books_from": source.get("identity", {}).get("BOOKSFROM", "20260401"),
        "state": source.get("identity", {}).get("STATENAME") or "Andhra Pradesh",
        "slug": f"{ordinal:02d}-"
        + re.sub(r"[^a-z0-9]+", "-", source["company"].lower()).strip("-"),
    }
    masters = []

    def master(kind, name, parent=None, **values):
        masters.append(
            {
                "type": kind,
                "name": f"MKQA{name}" if kind == "UNIT" else f"{PREFIX} {name}",
                "parent": parent,
                "guid": identifier(company["company_guid"], kind, name),
                **values,
            }
        )

    for name, parent in [("Vendors", "Sundry Creditors"), ("Purchase Heads", "Purchase Accounts")]:
        master("GROUP", name, parent)
    for name, *_ in SPECS:
        master("LEDGER", name, f"{PREFIX} Vendors", alias=f"{name} - QA")
    for name in ("Pioneer Industrial", "Pioneer Electrical", "Inventory Depot"):
        master("LEDGER", name, f"{PREFIX} Vendors")
    for _, purchase, *_ in SPECS:
        master("LEDGER", purchase, f"{PREFIX} Purchase Heads")
    for rate in ("2.5", "6", "9"):
        for label in ("CGST", "SGST"):
            master("LEDGER", f"Input {label} {rate}%", "Duties & Taxes")
    master("LEDGER", "Input IGST 18%", "Duties & Taxes")
    for name, parent in [
        ("Bank Current", "Bank Accounts"),
        ("Cash Imprest", "Cash-in-Hand"),
        ("Customer A", "Sundry Debtors"),
        ("Customer B", "Sundry Debtors"),
        ("Project Revenue", "Sales Accounts"),
        ("Site Administration", "Indirect Expenses"),
        ("Accrued Expenses", "Current Liabilities"),
        ("Round Off", "Indirect Expenses"),
    ]:
        master("LEDGER", name, parent)
    master("COSTCATEGORY", "Projects")
    for name in ("AG Section 1", "Canal Package 2", "Head Office"):
        master("COSTCENTRE", name, category=f"{PREFIX} Projects")
    for name in ("Nos", "MT", "Day", "Bag", "Trip"):
        master("UNIT", name)
    master("STOCKGROUP", "Construction Materials")
    master("STOCKCATEGORY", "Site Consumables")
    for name in ("Central Stores", "AG Section Stores"):
        master("GODOWN", name, "Main Location")
    items = [
        ("Excavator Wear Kit", "Nos"),
        ("Tooth Point PC200", "Nos"),
        ("Tooth Lock PC200", "Nos"),
        ("Bucket Pin", "Nos"),
        ("Seal Kit", "Nos"),
        ("OPC Cement", "Bag"),
        ("PPC Cement", "Bag"),
        ("TMT Steel 12mm", "MT"),
        ("TMT Steel 16mm", "MT"),
        ("Aggregate 20mm", "MT"),
        ("M Sand", "MT"),
        ("Portable Cabin", "Nos"),
    ]
    for name, unit in items:
        master("STOCKITEM", name, f"{PREFIX} Construction Materials", unit=f"MKQA{unit}")
    company["masters"] = masters
    vouchers = []
    code = f"C{ordinal:02d}"
    for month, day in ((6, 1), (7, 2), (8, 31), (9, 1)):
        for i in range(len(SPECS)):
            bill = make_bill(
                company,
                i,
                "history",
                f"{PREFIX}/{code}/H{month:02d}/{i + 1:03d}",
                issued=f"2026-{month:02d}-{day:02d}",
            )
            vouchers.append(purchase_voucher(company, bill))
    bills = [
        make_bill(
            company,
            i,
            f"{i + 1:02d}",
            f"{PREFIX}/{code}/26-27/{i + 1:03d}",
            issued="2026-10-01" if i % 2 == 0 else "2026-10-02",
        )
        for i in range(len(SPECS))
    ]
    for case, expected in (
        ("existing_duplicate", "duplicate"),
        ("conflicting_version", "attention"),
    ):
        bill = make_bill(
            company,
            1,
            f"{len(bills) + 1:02d}",
            f"{PREFIX}/{code}/{case.upper()}/001",
            case=case,
            expected=expected,
            issued="2026-09-02",
        )
        vouchers.append(purchase_voucher(company, bill))
        if case == "conflicting_version":
            bill["lines"][0]["rate"] = money(Decimal(bill["lines"][0]["rate"]) + 5)
            for field in ("gross", "net"):
                bill["lines"][0][field] = money(Decimal(bill["lines"][0][field]) + 250)
            bill["subtotal"] = money(Decimal(bill["subtotal"]) + 250)
            bill["tax_allocations"] = tax_lines(bill["subtotal"], 18, False)
            bill["tax"] = money(sum(Decimal(t["amount"]) for t in bill["tax_allocations"]))
            bill["total"] = money(Decimal(bill["subtotal"]) + Decimal(bill["tax"]))
        bills.append(bill)
    for case in (
        "missing_supplier",
        "ambiguous_supplier",
        "separate_round_off",
        "before_books",
        "inventory_required",
    ):
        bill = make_bill(
            company,
            1,
            f"{len(bills) + 1:02d}",
            f"{PREFIX}/{code}/{case.upper()}/001",
            case=case,
            expected="attention",
        )
        bill["scan"] = case == "ambiguous_supplier"
        if case == "missing_supplier":
            bill["supplier"] = bill["printed_supplier"] = f"{PREFIX} New Horizon Pumps"
        if case == "ambiguous_supplier":
            bill["supplier"] = f"{PREFIX} Pioneer Industrial"
            bill["printed_supplier"] = f"{PREFIX} Pioneer"
        if case == "separate_round_off":
            bill["round_off"] = "0.37"
            bill["total"] = money(Decimal(bill["total"]) + Decimal("0.37"))
        if case == "before_books":
            bill["date"] = "2026-03-31"
        if case == "inventory_required":
            bill["supplier"] = bill["printed_supplier"] = f"{PREFIX} Inventory Depot"
        bills.append(bill)
    duplicate = copy.deepcopy(bills[0])
    duplicate.update(
        id=f"{len(bills) + 1:02d}",
        case="same_bill_scan_copy",
        scan=True,
        duplicate_of=bills[0]["id"],
    )
    bills.append(duplicate)
    # Inventory history deliberately differs from ordinary ledger-only practice.
    for i in (1, 2):
        bill = make_bill(
            company, 1, "history", f"{PREFIX}/{code}/STOCK/{i:03d}", issued=f"2026-09-0{i}"
        )
        bill["supplier"] = f"{PREFIX} Inventory Depot"
        vouchers.append(purchase_voucher(company, bill, inventory=True))

    def supporting(kind, index, debit, credit, amount):
        reference = f"{PREFIX}/{code}/{kind.upper().replace(' ', '')}/{index:03d}"
        vouchers.append(
            {
                "type": kind,
                "reference": reference,
                "date": "2026-09-02",
                "party": None,
                "guid": identifier(company["company_guid"], "voucher", reference),
                "inventory": False,
                "entries": [
                    {"ledger": f"{PREFIX} {debit}", "amount": money(-amount)},
                    {"ledger": f"{PREFIX} {credit}", "amount": money(amount)},
                ],
            }
        )

    for i in range(8):
        supporting("Payment", i + 1, SPECS[i % 7][0], "Bank Current", 5000 + i * 125)
    for i in (1, 2):
        supporting("Receipt", i, "Bank Current", "Customer A", 30000 + i * 1000)
        supporting("Sales", i, "Customer A", "Project Revenue", 45000 + i * 1000)
        supporting("Journal", i, "Site Administration", "Accrued Expenses", 1000 + i * 100)
        supporting("Contra", i, "Cash Imprest", "Bank Current", 2000 + i * 100)
    supporting("Debit Note", 1, "Siddhi Plant Spares", "Plant Repairs", 1250)
    supporting("Credit Note", 1, "Project Revenue", "Customer A", 750)
    company.update(vouchers=vouchers, bills=bills)
    validate_company(company)
    return company


def validate_company(company):
    names = {m["name"] for m in company["masters"] if m["type"] == "LEDGER"}
    references = set()
    for voucher in company["vouchers"]:
        if sum(Decimal(e["amount"]) for e in voucher["entries"]) != 0:
            raise ValueError("Unbalanced seed voucher")
        if any(e["ledger"] not in names for e in voucher["entries"]):
            raise ValueError("Unknown seed ledger")
        if voucher["reference"] in references:
            raise ValueError("Repeated seed voucher")
        references.add(voucher["reference"])
    for record in company["bills"] + company["vouchers"]:
        if date.fromisoformat(record["date"]).day not in (1, 2, 31):
            raise ValueError("Date not supported by Educational Tally")


def draw_bill(pdf, bill, company):
    """Two full pages: invoice plus corroborating transport/service detail."""
    from reportlab.lib.colors import HexColor

    height = 841.89
    navy = HexColor("#21354B")

    def text(x, y, value, size=8, bold=False):
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        pdf.drawString(x, y, str(value))

    def rule(y):
        pdf.setStrokeColor(HexColor("#9CA8B3"))
        pdf.line(30, y, 565, y)

    def header(title, page):
        pdf.setFillColor(navy)
        pdf.rect(30, height - 61, 535, 29, fill=1, stroke=0)
        pdf.setFillColorRGB(1, 1, 1)
        text(40, height - 51, title, 13, True)
        pdf.setFillColorRGB(0.1, 0.1, 0.1)
        text(
            30, 18, "SYNTHETIC TEST DOCUMENT - NOT FOR PAYMENT / NOT A VALID TAX DOCUMENT", 7, True
        )
        text(505, 18, f"Page {page} / 2", 7)

    header("TAX INVOICE  |  Original for recipient", 1)
    text(32, 760, bill["printed_supplier"], 13, True)
    text(32, 745, "Plot 18, Industrial Service Road, Vijayawada - 520007", 8)
    text(32, 732, "Email: dispatch@example.invalid   Phone: 00000 00000", 8)
    text(32, 719, "Registered supplier / trading identity as printed above", 7)
    text(335, 760, "INVOICE NO.", 7, True)
    text(335, 746, bill["invoice_number"], 8, True)
    text(
        335, 730, "Invoice date: " + date.fromisoformat(bill["date"]).strftime("%d-%b-%Y"), 9, True
    )
    text(335, 716, "Terms: 30 days from invoice; INR", 8)
    rule(706)
    text(32, 688, "BILL TO / BUYER", 8, True)
    text(32, 673, company["company"], 10, True)
    text(32, 658, "Accounts Department, Project Administration Office", 8)
    text(32, 644, "Buyer GSTIN: not furnished in this test company", 7)
    text(32, 630, f"State: {company['state']}  |  Exact buyer name governs routing", 7)
    text(335, 688, "SHIP TO / CONSIGNEE", 8, True)
    text(335, 673, "AG Section-1 / Canal Package-2 stores", 9)
    text(335, 658, "Site gate 6, Material Receipt Office", 8)
    text(
        335,
        644,
        "Place of supply: "
        + ("Telangana (interstate)" if bill["interstate"] else company["state"]),
        7,
    )
    text(335, 630, "Vehicle: QA00TEST001  |  Mode: Road", 7)
    rule(617)
    for y, value in [
        (601, f"Purchase order: PO-QA-{company['ordinal']:02d}-0098  /  date: 01-Sep-2026"),
        (587, "Delivery note: DN-00482  /  date: 02-Sep-2026  |  GRN: GRN-01811 / 02-Oct-2026"),
        (573, "Transport ref: LR-172373172649  |  e-way reference: QA-EWB-001795  /  01-Oct-2026"),
    ]:
        text(32, y, value, 8)
    rule(562)
    columns = [
        (32, "No."),
        (55, "Description / HSN-SAC"),
        (292, "Qty / unit"),
        (362, "Rate"),
        (422, "Discount"),
        (490, "Taxable"),
    ]
    for x, value in columns:
        text(x, 547, value, 8, True)
    rule(539)
    y = 521
    for i, line in enumerate(bill["lines"], 1):
        text(32, y, i, 8)
        text(55, y, line["description"], 8)
        text(55, y - 11, "HSN/SAC " + line["hsn"], 6)
        for x, value in [
            (292, line["qty"] + " " + line["unit"]),
            (362, line["rate"]),
            (427, line["discount"]),
            (490, line["net"]),
        ]:
            text(x, y, value, 7)
        y -= 28
    rule(335)
    text(32, 319, "Taxable after trade discount; gross values appear in annexure.", 7)
    text(350, 319, "Assessable value", 8)
    text(490, 319, bill["subtotal"], 8, True)
    y = 302
    for tax in bill["tax_allocations"]:
        text(350, y, f"{tax['label']} @ {tax['rate']}%", 8)
        text(490, y, tax["amount"], 8)
        y -= 17
    if not bill["tax_allocations"]:
        text(350, y, "Tax amount (test exempt)", 8)
        text(490, y, "0.00", 8)
        y -= 17
    if bill["round_off"] != "0.00":
        text(350, y, "Round off (separate)", 8)
        text(490, y, bill["round_off"], 8)
        y -= 17
    rule(y)
    text(350, y - 19, "INVOICE TOTAL INR", 9, True)
    text(483, y - 19, bill["total"], 10, True)
    text(32, 206, "Previous balance: 37,850.00 (excluded from this invoice)", 8)
    text(32, 190, "Security deposit: 10,000.00 (not payable on this document)", 8)
    text(32, 174, "Payment due for THIS invoice only: INR " + bill["total"], 9, True)
    text(32, 151, "Bank: Test Bank  |  A/c: 000000001818  |  IFSC: TEST0000018", 7)
    text(
        32,
        135,
        "Declaration: quantities received subject to site quality checks and weighbridge slip.",
        7,
    )
    text(32, 121, "No bank details in this fixture may be used for a real payment.", 7)
    pdf.saveState()
    pdf.translate(410, 96)
    pdf.rotate(-5)
    pdf.setStrokeColor(HexColor("#345C9C"))
    pdf.setFillColor(HexColor("#345C9C"))
    pdf.rect(-15, -18, 160, 45)
    text(-8, 11, "RECEIVED - QA SITE STORES", 8, True)
    text(-8, -2, "DMR 1811 / 02-Oct-2026", 8)
    pdf.restoreState()
    pdf.showPage()
    header("E-WAY / DELIVERY & SERVICE ANNEXURE", 2)
    text(32, 758, "Corroborating document - belongs to the SAME invoice", 12, True)
    text(32, 736, "Invoice no.: " + bill["invoice_number"], 9, True)
    text(32, 719, "Invoice date: " + bill["date"] + "  |  Invoice total INR " + bill["total"], 9)
    text(32, 697, "Dispatch from: " + bill["printed_supplier"], 9)
    text(32, 680, "Deliver to: " + company["company"], 9, True)
    text(32, 663, "Destination: AG Section-1 site stores / receiving gate 6", 9)
    text(32, 646, "Reference generated: 01-Oct-2026 11:11  |  Valid through: 02-Oct-2026", 8)
    rule(630)
    text(32, 611, "Goods / service reconciliation", 10, True)
    y = 587
    for line in bill["lines"]:
        text(32, y, line["description"], 9)
        text(
            32,
            y - 14,
            f"{line['qty']} {line['unit']} x {line['rate']} = {line['gross']}  less {line['discount']} = {line['net']}",
            8,
        )
        y -= 45
    rule(300)
    text(
        32,
        281,
        "Taxable: "
        + bill["subtotal"]
        + "   Taxes: "
        + bill["tax"]
        + "   Invoice total: "
        + bill["total"],
        10,
        True,
    )
    text(32, 258, "LR no.: LR-172373172649  |  Vehicle: QA00TEST001  |  Distance: 80 km", 9)
    text(
        32,
        239,
        "PO, GRN, DMR, e-way and LR numbers are supporting references, not invoice numbers.",
        8,
    )
    text(
        32,
        220,
        "Prior balances, deposits and copied totals must not be added to the invoice amount.",
        8,
    )
    if bill["case"] == "inventory_required":
        text(
            32,
            193,
            "STOCK RECEIPT: update item quantities and batch QA-BATCH-01 in Central Stores.",
            8,
            True,
        )
        text(32, 178, "Maintain item inventory as in this supplier's earlier stock invoices.", 8)
    text(
        32,
        148,
        "Received quantities checked against dispatch register and site attendance sheets.",
        8,
    )
    text(
        32,
        130,
        "Prepared by: Dispatch clerk    Checked by: Site stores    Approved by: QA supervisor",
        8,
    )
    text(
        32, 100, "Supplier signature __________________    Receiver signature __________________", 9
    )
    pdf.showPage()


def raster_copy(source, destination):
    import pypdfium2
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas

    document = pypdfium2.PdfDocument(str(source))
    canvas = Canvas(str(destination), pagesize=(595.28, 841.89), invariant=1)
    for index in range(len(document)):
        image = document[index].render(scale=1.55).to_pil().convert("RGB")
        # Mild paper skew is a PDF placement, without destructive image editing.
        canvas.saveState()
        canvas.translate(297.64, 420.945)
        canvas.rotate(-0.6 if index == 0 else 0.4)
        canvas.drawImage(ImageReader(image), -292, -414, width=584, height=828)
        canvas.restoreState()
        canvas.showPage()
    canvas.save()
    document.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    if snapshot.get("partial") or not snapshot.get("companies"):
        raise SystemExit("A complete live baseline is required.")
    companies = [build_company(c, i) for i, c in enumerate(snapshot["companies"], 1)]
    args.output.mkdir(parents=True, exist_ok=False)
    evidence = args.output / "evidence"
    evidence.mkdir()
    (evidence / "baseline.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    from pypdf import PdfWriter
    from reportlab.pdfgen.canvas import Canvas

    for company in companies:
        directory = args.output / company["slug"]
        (directory / "bills").mkdir(parents=True)
        (directory / "evidence").mkdir()
        combined = PdfWriter()
        for bill in company["bills"]:
            target = directory / "bills" / f"{bill['id']}-{bill['case']}.pdf"
            vector = directory / "evidence" / "render-source.pdf"
            canvas = Canvas(str(vector), pagesize=(595.28, 841.89), invariant=1)
            draw_bill(canvas, bill, company)
            canvas.save()
            if bill["scan"]:
                raster_copy(vector, target)
                vector.unlink()
            else:
                vector.replace(target)
            bill["file"] = target.relative_to(directory).as_posix()
            bill["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
            combined.append(str(target))
        combined.write(str(directory / "all-bills-preview.pdf"))
        combined.close()
        (directory / "evidence" / "expected-bills.json").write_text(
            json.dumps(company["bills"], indent=2), encoding="utf-8"
        )
    (evidence / "seed-plan.json").write_text(
        json.dumps({"prefix": PREFIX, "companies": companies}, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            [
                {
                    "company": c["company"],
                    "masters": len(c["masters"]),
                    "vouchers": len(c["vouchers"]),
                    "bills": len(c["bills"]),
                }
                for c in companies
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
