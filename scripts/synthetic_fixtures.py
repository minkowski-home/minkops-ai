"""Synthetic look-alikes of PR Infra's sample statement and bills.

The real files stay in the private fixture store (~/minkops-private/fixtures),
never in git. These reproduce what the rebuild depends on (layout, value and
date formats, narration families, footer controls, scan characteristics) with
no client identifiers, so tests and benchmarks run anywhere. Every name,
number, GSTIN, account and amount below is invented.

  statement OUT.xlsx    One month in the bank's "Detailed Statement" layout.
  bills OUT_DIR         Two image-only e-invoice scans and their answers.

Generation is a development task: it needs the dev dependency group (Pillow,
qrcode, cryptography). The committed outputs need only the application stack.
Expected answers are written beside the bills and must never reach a model.
"""

import argparse
import base64
import json
import random
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from openpyxl import Workbook

from minkops_platform.accounts.supplier_gst import ALPHABET

# Narration families measured on the real statement: (withdrawals, deposits).
FAMILIES = {"INF/NEFT": (700, 0), "UPI": (204, 4), "RTGS": (120, 10), "MMT/IMPS": (103, 3),
            "INF/INFT": (53, 2), "other": (17, 2), "NEFT-RETURN": (0, 8), "BIL/ONL": (6, 0)}
# Debits per payee, most frequent first: 881 payees, 716 seen once; the top 10
# cover about 8% of debits, the top 50 about 20% and the top 200 about 43%.
PAYEE_COUNTS = [12, 11, 10, 10, 9, 9, 9, 9, 9, 8] + [4] * 25 + [3] * 15 + [3] * 16 + [2] * 99 + [1] * 716
SITES = ["KTA", "BRP", "HSP", "MNG", "DBP", "SKR", "JPR", "TNK"]
FIRST = ["RAMESH", "SURESH", "MAHESH", "GANESH", "ANIL", "SUNIL", "VIJAY", "AJAY", "RAJU", "MOHAN", "SOHAN",
         "KISHAN", "RAKESH", "DINESH", "PRAKASH", "MUKESH", "NARESH", "HARISH", "SATISH", "GIRISH", "MANOJ", "PAWAN",
         "DEEPAK", "ASHOK", "VINOD", "PRAMOD", "SANJAY", "RAVI", "KAMAL", "GOPAL", "SHYAM", "RADHE", "BABU", "LALIT"]
LAST = ["KUMAR", "SINGH", "SHARMA", "VERMA", "YADAV", "MEENA", "GURJAR", "JAT", "SAINI", "PRAJAPAT", "NAI",
        "BAIRWA", "REGAR", "KHAN", "MALI", "DHAKAD", "CHOUDHARY", "RATHORE", "SHEKHAWAT", "JOSHI"]
FIRMS = ["TRADERS", "ENTERPRISES", "CONSTRUCTION", "TRANSPORT", "HARDWARE", "SUPPLIERS", "BUILDERS", "STONE CRUSHER",
         "EARTH MOVERS", "FUEL STATION", "STEEL", "CEMENT AGENCY"]
BANKS = ["SBIN", "PUNB", "BARB", "HDFC", "UBIN", "CNRB", "BKID", "IDIB", "AUBL", "RMGB"]
RETURN_REASONS = [("Account Does Not Exist", "AC01"), ("Invalid Account Number", "AC03"),
                  ("Account Closed", "AC04"), ("Beneficiary Name Mismatch", "BE01")]
STATEMENT_HEADER = ["S.N.", "Tran. Id", "Value Date", "Transaction Date", "Transaction Posted Date",
                    "Cheque. No./Ref. No.", "Transaction Remarks", "Withdrawal Amt (INR)", "Deposit Amt (INR)",
                    "Balance (INR)"]


def indian(cents):
    """Indian digit grouping as the bank prints it: 12,34,567.89."""
    rupees, paise = divmod(abs(cents), 100)
    digits = str(rupees)
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail]) + f".{paise:02}"


def gstin(state, pan, entity="1"):
    """A structurally valid GSTIN; the check character uses supplier_gst's alphabet."""
    body = f"{state}{pan}{entity}Z"
    total, factor = 0, 2
    for character in reversed(body):
        product = ALPHABET.index(character) * factor
        total += product // 36 + product % 36
        factor = 3 - factor
    return body + ALPHABET[(36 - total % 36) % 36]


def payees(rng):
    """Distinct invented payees: people for wage-style NEFTs, a few firms."""
    names, seen = [], set()
    while len(names) < len(PAYEE_COUNTS):
        if rng.random() < 0.15:
            name = f"{rng.choice(FIRST)} {rng.choice(FIRMS)}"
        else:
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if rng.random() < 0.3:
                name = f"{rng.choice(FIRST)[0]} {name}"
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def amount(rng, family, deposit):
    """Paise, drawn so the digit-count spread resembles the real month."""
    if family == "INF/NEFT":
        rupees = rng.choice([rng.randrange(8_000, 60_000, 100), rng.randrange(8_000, 60_000, 500),
                             rng.randrange(1_000, 9_999) + rng.randrange(0, 100) / 100])
    elif family == "UPI":
        rupees = rng.randrange(150, 9_000) + rng.randrange(0, 100) / 100
    elif family == "RTGS":
        rupees = rng.randrange(5_000_000, 40_000_000, 1_000) if deposit else rng.randrange(200_000, 3_500_000, 100)
    elif family in ("MMT/IMPS", "INF/INFT"):
        rupees = rng.randrange(2_000, 180_000) + rng.randrange(0, 100) / 100
    elif family == "BIL/ONL":
        rupees = rng.randrange(1_500, 45_000) + rng.randrange(0, 100) / 100
    else:
        rupees = rng.randrange(900, 250_000) + rng.randrange(0, 100) / 100
    return int(Decimal(str(rupees)) * 100)


def utr(rng, bank):
    return f"{bank[:2]}N{rng.randrange(10**11, 10**12)}"


def narration(rng, family, payee, *, site, deposit, batch=None, reference=None):
    compact = payee.replace(" ", "")
    if family == "INF/NEFT":
        return (f"INF/NEFT/{reference}/{rng.choice(BANKS)}{rng.randrange(10**6, 10**7)}/"
                f"{batch or rng.randrange(10**7, 10**8)} /{payee:<20}/{site}")
    if family == "UPI":
        handle = f"{compact.lower()[:10]}{rng.randrange(10, 99)}@{rng.choice(['ybl', 'okaxis', 'paytm', 'oksbi'])}"
        return f"UPI/{rng.randrange(10**11, 10**12)}/{compact[:12]}/{handle}//{rng.choice(BANKS)}{rng.randrange(10**9, 10**10)}"
    if family == "RTGS":
        name = payee[:20]
        if rng.random() < 0.5:
            return f"RTGS/{rng.choice(BANKS)}R{rng.randrange(10**11, 10**12)}/{rng.choice(BANKS)}{rng.randrange(10**6, 10**7)}/{name}"
        return f"RTGS-{rng.choice(BANKS)}R{rng.randrange(10**11, 10**12)}-{name}-{rng.randrange(10**9, 10**10)}-{site}"
    if family == "MMT/IMPS":
        return f"MMT/IMPS/{rng.randrange(10**11, 10**12)}/{compact[:10]}{rng.randrange(10, 99)}/{rng.choice(BANKS)}/X{rng.randrange(10**5, 10**6)}"
    if family == "INF/INFT":
        return f"INF/INFT/{rng.randrange(10**8, 10**9)}/{site}{rng.randrange(10, 99)}/{payee}"
    if family == "BIL/ONL":
        return f"BIL/ONL/{rng.randrange(10**11, 10**12)}/{rng.choice(['Electricity Board', 'Mobile Billpay', 'Broadband Bill'])}"
    return f"CMS/{rng.choice(['Fuel Card', 'Toll Wallet'])} Topup {site}{rng.randrange(10, 99)} {payee.title()[:16]}"


def statement_rows(seed):
    """Transactions oldest first, with running balances that chain exactly."""
    rng = random.Random(seed)
    names = payees(rng)
    debit_payees = [name for name, count in zip(names, PAYEE_COUNTS, strict=True) for _ in range(count)]
    rng.shuffle(debit_payees)
    related = "MINKOPS SYNTHETIC HOLDINGS PVT LTD"
    batch = f"{rng.randrange(10**7, 10**8)}"
    rows = []
    for family, (withdrawals, deposits) in FAMILIES.items():
        if family == "NEFT-RETURN":
            continue
        for index in range(withdrawals + deposits):
            deposit = index >= withdrawals
            payee = related if deposit and family == "RTGS" else (
                f"{rng.choice(FIRST)} {rng.choice(LAST)}" if deposit else debit_payees.pop())
            day = rng.choice(range(1, 31)) if family != "INF/NEFT" or rng.random() > 0.35 else rng.choice((1, 2, 10, 25))
            rows.append({"family": family, "payee": payee, "deposit": deposit,
                         "amount_cents": amount(rng, family, deposit) * (1 if deposit else -1),
                         "date": date(2026, 9, day), "minute": rng.randrange(9 * 60, 19 * 60),
                         "site": rng.choice(SITES), "bank": rng.choice(BANKS)})
    assert not debit_payees, "Every planned debit must have a payee."
    for row in rows:
        if row["family"] == "INF/NEFT":
            row["reference"] = utr(rng, row["bank"])
            # Bulk wage-style payments share one batch reference across many rows.
            row["batch"] = batch if row["date"].day in (1, 2) and rng.random() < 0.8 else None
    # Each NEFT return carries the original payment's UTR, on the same day.
    returned = rng.sample([r for r in rows if r["family"] == "INF/NEFT"], FAMILIES["NEFT-RETURN"][1])
    for original in returned:
        reason, code = rng.choice(RETURN_REASONS)
        rows.append({"family": "NEFT-RETURN", "payee": original["payee"], "deposit": True,
                     "amount_cents": -original["amount_cents"], "date": original["date"],
                     "minute": min(original["minute"] + rng.randrange(30, 240), 23 * 60 + 59),
                     "reason": reason, "code": code, "reference": original["reference"], "returns": original})
    rows.sort(key=lambda r: (r["date"], r["minute"]))
    # The smallest opening that keeps every running balance above ₹1 lakh.
    lowest, running = 0, 0
    for row in rows:
        running += row["amount_cents"]
        lowest = min(lowest, running)
    opening = -lowest + 10_000_000 + 4_567_812
    balance = opening
    for number, row in enumerate(rows, 1):
        balance += row["amount_cents"]
        row["balance_cents"], row["number"] = balance, number
        row["tran_id"] = f"S{rng.randrange(10**7, 10**8)}" if rng.random() > 0.04 else f"S{rng.randrange(10**6, 10**7)}"
        if row["family"] == "NEFT-RETURN":
            row["narration"] = f"NEFT-RETURN-{row['reference']}-{row['payee'].replace(' ', '')}-{row['reason']}  {row['code']}"
        else:
            row["narration"] = narration(rng, row["family"], row["payee"], site=row["site"], deposit=row["deposit"],
                                         batch=row.get("batch"), reference=row.get("reference"))
    # One bank transaction ID is printed on two different rows; balances keep
    # their row identities distinct.
    rows[400]["tran_id"] = rows[399]["tran_id"]
    return opening, rows


def write_statement(path, seed=7):
    opening, rows = statement_rows(seed)
    book = Workbook()
    sheet = book.active
    sheet.title = "Sheet1"
    meta = [
        [], ["Detailed Statement"],
        ["Name:", "MINKOPS SYNTHETIC INFRA PVT LTD", None, None, None, "Account Currency:", "INR"],
        ["Address:", "12, SYNTHETIC INDUSTRIAL AREA, JAIPUR", None, None, None, "A/C Branch:", "SYNTH"],
        ["A/C No:", "999905001234", None, None, None, "Branch Address:", "1 TEST ROAD, JAIPUR"],
        ["A/C Type:", "CAA", None, None, None, "Cust ID:", "999912345"],
        ["Jt. Holder:", None, None, None, None, "Branch Code:", "9999"],
        ["Transaction Date from:", "01/09/2026", None, None, None, "IFSC Code:", "ICIC0009999"],
        ["Transaction Period", "From 01/09/2026 To 30/09/2026"],
        ["Statement Request/Download Date:", "01/10/2026"],
        ["Advanced Search"],
        ["Amount from:", "NA", "To", "NA"],
        ["Cheque number from:", "NA", "To", "NA"],
        ["Transaction remarks:"],
        # A filter label is not proof of a filter: deposits are still present.
        ["Transaction type:", "DR"],
        [], STATEMENT_HEADER,
    ]
    for line in meta:
        sheet.append(line)
    for row in rows:
        when = datetime.combine(row["date"], datetime.min.time()) + timedelta(minutes=row["minute"])
        printed = row["date"].strftime("%d/%b/%Y")
        sheet.append([str(row["number"]), row["tran_id"], printed, printed, when.strftime("%d/%m/%Y %I:%M:%S %p"), None,
                      row["narration"], None if row["deposit"] else indian(row["amount_cents"]),
                      indian(row["amount_cents"]) if row["deposit"] else None, indian(row["balance_cents"])])
    withdrawn = sum(-r["amount_cents"] for r in rows if r["amount_cents"] < 0)
    deposited = sum(r["amount_cents"] for r in rows if r["amount_cents"] > 0)
    sheet.append([])
    for line in (["Page Total"], ["Opening Bal:", indian(opening)], ["Withdrawls:", indian(withdrawn)],
                 ["Deposits:", indian(deposited)], ["Closing Bal:", indian(rows[-1]["balance_cents"])], [],
                 ["Legends Used in Account Statement"]):
        sheet.append(line)
    for number, (short, meaning) in enumerate([
            ("INF", "Internet Fund Transfer"), ("NEFT", "National Electronic Funds Transfer"),
            ("RTGS", "Real Time Gross Settlement"), ("IMPS", "Immediate Payment Service"),
            ("MMT", "Mobile Money Transfer"), ("INFT", "Internal Fund Transfer"), ("UPI", "Unified Payments Interface"),
            ("BIL", "Bill Payment"), ("ONL", "Online Payment"), ("CMS", "Cash Management Services"),
            ("CLG", "Clearing"), ("CHQ", "Cheque"), ("ATM", "ATM Withdrawal"), ("POS", "Point of Sale"),
            ("TDS", "Tax Deducted at Source"), ("INT", "Interest"), ("CHG", "Charges"), ("REV", "Reversal"),
            ("RTN", "Return"), ("NACH", "National Automated Clearing House"), ("ECS", "Electronic Clearing Service"),
            ("SI", "Standing Instruction"), ("DD", "Demand Draft"), ("PO", "Pay Order"), ("TRF", "Transfer"),
            ("BBPS", "Bharat Bill Payment System"), ("GST", "Goods and Services Tax"), ("MAB", "Minimum Average Balance"),
            ("NFS", "National Financial Switch"), ("VPS", "Visa POS")], 1):
        sheet.append([f"{number}. {short} - {meaning}"])
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
    families = {}
    for row in rows:
        families.setdefault(row["family"], [0, 0])[1 if row["deposit"] else 0] += 1
    return {"file": path.name, "header_row": 17, "transactions": len(rows),
            "withdrawals": sum(r["amount_cents"] < 0 for r in rows), "deposits": sum(r["amount_cents"] > 0 for r in rows),
            "opening_cents": opening, "closing_cents": rows[-1]["balance_cents"], "withdrawal_cents": withdrawn,
            "deposit_cents": deposited, "families": {k: {"withdrawals": v[0], "deposits": v[1]} for k, v in families.items()},
            "neft_returns": [{"utr": r["reference"], "date": r["date"].isoformat(), "amount_cents": r["amount_cents"]}
                             for r in rows if r["family"] == "NEFT-RETURN"],
            "educational_date_rows": sum(r["date"].day in (1, 2, 31) for r in rows),
            "distinct_payees": len({r["payee"] for r in rows if r["amount_cents"] < 0})}


# --- bills --------------------------------------------------------------------

BUYER = {"name": "MINKOPS SYNTHETIC INFRA PVT LTD", "state": "Andhra Pradesh", "code": "37",
         "address": ["Plot 7, Synthetic Industrial Estate", "Ongole, Andhra Pradesh 523001"]}
BUYER["gstin"] = gstin("37", "AAXCM4321K")
# The bank account belongs to the Rajasthan registration; bills route to another.
BANK_REGISTRATION = gstin("08", "AAXCM4321K")
BILLS = [
    {"file": "2901 SYNTHETIC OFFICE SUPPLIES SOS-077-25-26 999900001111 15.3.26.pdf",
     "case": "tax_inclusive_amount_column", "dmr": "2901", "received": "16/03/2026", "site_note": "Site 3 Store",
     "supplier": {"name": "SYNTHETIC OFFICE SUPPLIES", "gstin": gstin("37", "BXSPS7788M"), "state": "Andhra Pradesh",
                  "code": "37", "address": ["Shop 4, Test Market, Ongole", "Andhra Pradesh 523002"]},
     "number": "SOS/077/25-26", "date": "2026-03-15", "tax": "intra", "rate": 18,
     "lines": [("A4 Copier Paper 75 GSM (500 sheets)", "4802", 40, "Ream", "245.00"),
               ("Box File Heavy Duty", "4820", 60, "Nos", "118.50"),
               ("Whiteboard Marker (set of 4)", "9608", 25, "Set", "160.00"),
               ("Desk Organiser Tray", "3926", 12, "Nos", "395.00")]},
    {"file": "2916 SYNTHETIC MOVERS 25SM1153 6.3.26.pdf",
     "case": "goods_and_services_lines", "dmr": "2916", "received": "07/03/2026", "site_note": "Batch Plant Direct",
     "supplier": {"name": "SYNTHETIC MOVERS AND HANDLING", "gstin": gstin("36", "AAHFS2468P"), "state": "Telangana",
                  "code": "36", "address": ["14-2, Test Logistics Park", "Hyderabad, Telangana 500055"]},
     "number": "25SM1153", "date": "2026-03-06", "tax": "inter", "rate": 18,
     "lines": [("Hydraulic Bottle Jack 20 T", "8425", 2, "Nos", "18500.00"),
               ("Loading, Unloading and Handling Charges", "996719", 1, "Job", "2500.00")]},
]


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def bill_values(bill):
    lines = [{"description": d, "hsn": h, "quantity": q, "unit": u, "rate": r,
              "taxable": str(money(Decimal(r) * q))} for d, h, q, u, r in bill["lines"]]
    taxable = sum(Decimal(line["taxable"]) for line in lines)
    tax = money(taxable * bill["rate"] / 100)
    if bill["tax"] == "intra":
        halves = money(taxable * bill["rate"] / 200)
        taxes = [{"head": "cgst", "rate": bill["rate"] / 2, "amount": str(halves)},
                 {"head": "sgst", "rate": bill["rate"] / 2, "amount": str(halves)}]
        tax = halves * 2
    else:
        taxes = [{"head": "igst", "rate": bill["rate"], "amount": str(tax)}]
    exact = taxable + tax
    total = exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return {"lines": lines, "taxable": str(taxable), "taxes": taxes, "tax": str(tax),
            "round_off": str(total - exact), "total": str(total)}


def signed_qr(payload, private_key):
    """A JWS shaped like an IRP signed QR, signed with a throwaway test key."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    def b64(raw):
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "RS256", "kid": "SYNTHETIC-TEST-KEY", "typ": "JWT"}).encode())
    body = b64(json.dumps({"data": json.dumps(payload, separators=(",", ":")), "iss": "NIC Synthetic"}).encode())
    signature = private_key.sign(f"{header}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{body}.{b64(signature)}"


def render_bill(bill, values, qr_text, rng):
    """Two A4 pages at 200 DPI: tax invoice, then the e-way bill."""
    import qrcode
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1654, 2339

    def font(size):
        return ImageFont.load_default(size=size)

    def page():
        image = Image.new("RGB", (width, height), (252, 251, 247))
        return image, ImageDraw.Draw(image)

    supplier = bill["supplier"]
    invoice, draw = page()
    y = 70
    draw.text((80, y), supplier["name"], font=font(46), fill=(20, 20, 20))
    for line in [*supplier["address"], f"GSTIN/UIN: {supplier['gstin']}", f"State Name: {supplier['state']}, Code: {supplier['code']}"]:
        y += 52
        draw.text((80, y), line, font=font(28), fill=(30, 30, 30))
    draw.text((80, y + 80), "TAX INVOICE", font=font(44), fill=(10, 10, 10))
    irn = values["irn"]
    draw.text((80, y + 150), f"IRN : {irn[:32]}", font=font(24), fill=(30, 30, 30))
    draw.text((80, y + 182), f"      {irn[32:]}", font=font(24), fill=(30, 30, 30))
    draw.text((80, y + 214), f"Ack No. : {values['ack_no']}    Ack Date : {values['ack_date']}", font=font(24), fill=(30, 30, 30))
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=4, border=2)
    code.add_data(qr_text)
    code.make(fit=True)
    invoice.paste(code.make_image(fill_color="black", back_color="white").convert("RGB").resize(
        (520, 520), Image.Resampling.NEAREST), (1080, 40))
    y += 280
    issued = date.fromisoformat(bill["date"]).strftime("%d-%b-%y")
    draw.rectangle((70, y, 1584, y + 120), outline=(40, 40, 40), width=2)
    draw.text((90, y + 14), f"Invoice No.  {bill['number']}", font=font(30), fill=(10, 10, 10))
    draw.text((900, y + 14), f"Dated  {issued}", font=font(30), fill=(10, 10, 10))
    draw.text((90, y + 66), "Mode/Terms of Payment  30 Days", font=font(24), fill=(30, 30, 30))
    draw.text((900, y + 66), f"Buyer's Order No.  PO-{rng.randrange(1000, 9999)}", font=font(24), fill=(30, 30, 30))
    y += 140
    draw.text((90, y), "Buyer (Bill to)", font=font(26), fill=(30, 30, 30))
    for offset, line in enumerate([BUYER["name"], *BUYER["address"], f"GSTIN/UIN : {BUYER['gstin']}",
                                   f"State Name : {BUYER['state']}, Code : {BUYER['code']}"], 1):
        draw.text((90, y + offset * 38), line, font=font(28 if offset == 1 else 24), fill=(20, 20, 20))
    y += 260
    columns = [90, 160, 760, 930, 1080, 1230, 1330, 1584]
    titles = ["Sl", "Description of Goods and Services", "HSN/SAC", "Quantity", "Rate", "per", "Amount"]
    draw.rectangle((70, y, 1584, y + 60), outline=(40, 40, 40), width=2)
    for x, title in zip(columns, titles, strict=False):
        draw.text((x, y + 16), title, font=font(24), fill=(10, 10, 10))
    y += 70
    inclusive = bill["case"] == "tax_inclusive_amount_column"
    for number, line in enumerate(values["lines"], 1):
        # One supplier prints each line's Amount including GST.
        shown = money(Decimal(line["taxable"]) * (100 + bill["rate"]) / 100) if inclusive else Decimal(line["taxable"])
        for x, text in zip(columns, [str(number), line["description"], line["hsn"], f"{line['quantity']} {line['unit']}",
                                     line["rate"], line["unit"], f"{shown:,.2f}"], strict=False):
            draw.text((x, y), text, font=font(24), fill=(20, 20, 20))
        y += 52
    y += 30
    labels = [("Taxable Value", values["taxable"])] + [(f"{t['head'].upper()} @ {t['rate']:g}%", t["amount"]) for t in values["taxes"]]
    if Decimal(values["round_off"]):
        labels.append(("Round Off", values["round_off"]))
    labels.append(("Total", values["total"]))
    for label, figure in labels:
        draw.text((930, y), label, font=font(26), fill=(10, 10, 10))
        draw.text((1330, y), f"{Decimal(figure):,.2f}", font=font(26), fill=(10, 10, 10))
        y += 46
    draw.text((90, y + 30), "Amount Chargeable (in words): as per total above", font=font(24), fill=(30, 30, 30))
    draw.text((90, y + 80), f"Company's Bank Details: SYNTHETIC BANK, A/c No. 99990000{rng.randrange(1000, 9999)}", font=font(22), fill=(30, 30, 30))
    draw.text((1100, y + 200), f"for {supplier['name']}", font=font(24), fill=(20, 20, 20))
    draw.text((1180, y + 300), "Authorised Signatory", font=font(24), fill=(20, 20, 20))
    stamp(invoice, bill, rng)
    eway, draw = page()
    draw.text((80, 80), "e-Way Bill", font=font(48), fill=(10, 10, 10))
    issued_on = date.fromisoformat(bill["date"])
    fields = [("E-Way Bill No", values["eway_no"]), ("E-Way Bill Date", f"{issued_on:%d/%m/%Y} 10:41 AM"),
              ("Generated By", supplier["gstin"]), ("Valid Upto", f"{issued_on + timedelta(days=3):%d/%m/%Y}"),
              ("Mode", "1 - Road"), ("Approx Distance", f"{rng.randrange(40, 900)} km"),
              ("GSTIN of Supplier", supplier["gstin"]), ("Place of Dispatch", supplier["address"][-1]),
              ("GSTIN of Recipient", BUYER["gstin"]), ("Place of Delivery", BUYER["address"][-1]),
              ("Document No.", bill["number"]), ("Document Date", f"{issued_on:%d/%m/%Y}"),
              ("Value of Goods", f"{Decimal(values['total']):,.2f}"), ("HSN Code", values["lines"][0]["hsn"]),
              ("Reason for Transportation", "Supply"), ("Vehicle No.", f"AP{rng.randrange(10, 39)}TX{rng.randrange(1000, 9999)}")]
    for index, (label, value) in enumerate(fields):
        draw.text((90, 200 + index * 72), label, font=font(28), fill=(40, 40, 40))
        draw.text((760, 200 + index * 72), value, font=font(28), fill=(10, 10, 10))
    return [scan(invoice, rng), scan(eway, rng)]


def stamp(image, bill, rng):
    """The client's own marks: a receipt-register stamp, a signature and a site note."""
    from PIL import Image, ImageDraw, ImageFont

    ink = (35, 55, 150)
    mark = Image.new("RGBA", (560, 250), (0, 0, 0, 0))
    draw = ImageDraw.Draw(mark)
    draw.rounded_rectangle((6, 6, 554, 244), radius=24, outline=ink + (215,), width=6)
    draw.text((40, 26), "RECEIVED", font=ImageFont.load_default(size=44), fill=ink + (215,))
    draw.text((40, 96), f"DMR No. {bill['dmr']}", font=ImageFont.load_default(size=40), fill=ink + (215,))
    draw.text((40, 160), f"Date {bill['received']}", font=ImageFont.load_default(size=36), fill=ink + (215,))
    mark = mark.rotate(rng.uniform(-9, -4), expand=True, resample=Image.Resampling.BICUBIC)
    image.paste(mark, (980, 1640), mark)
    pen = ImageDraw.Draw(image)
    x, y = 1200, 2000
    for _ in range(14):
        nx, ny = x + rng.randrange(12, 30), y + rng.randrange(-28, 28)
        pen.line((x, y, nx, ny), fill=(25, 30, 90), width=4)
        x, y = nx, ny
    note = Image.new("RGBA", (700, 120), (0, 0, 0, 0))
    ImageDraw.Draw(note).text((10, 20), bill["site_note"], font=ImageFont.load_default(size=58), fill=(20, 25, 110, 235))
    note = note.rotate(rng.uniform(4, 9), expand=True, resample=Image.Resampling.BICUBIC)
    image.paste(note, (120, 1880), note)


def scan(image, rng):
    """Mild skew, tint, blur and noise, like a phone or office scan."""
    from PIL import Image, ImageFilter

    skewed = image.rotate(rng.uniform(-1.2, 1.2), resample=Image.Resampling.BICUBIC, fillcolor=(236, 234, 226))
    noise = Image.effect_noise(skewed.size, 14).convert("RGB")
    return Image.blend(skewed, noise, 0.06).filter(ImageFilter.GaussianBlur(0.6))


def write_bills(directory, seed=7):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    rng = random.Random(seed)
    directory.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    # Only the public half is kept, so the fixtures can verify but never sign.
    (directory / "irp-test-public-key.pem").write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    answers = []
    for bill in BILLS:
        values = bill_values(bill)
        values["irn"] = "".join(rng.choice("0123456789abcdef") for _ in range(64))
        values["ack_no"] = str(rng.randrange(10**14, 10**15))
        values["ack_date"] = f"{date.fromisoformat(bill['date']):%d-%b-%y} 12:{rng.randrange(10, 59)}"
        values["eway_no"] = str(rng.randrange(10**11, 10**12))
        payload = {"SellerGstin": bill["supplier"]["gstin"], "BuyerGstin": BUYER["gstin"], "DocNo": bill["number"],
                   "DocTyp": "INV", "DocDt": f"{date.fromisoformat(bill['date']):%d/%m/%Y}",
                   "TotInvVal": float(values["total"]), "ItemCnt": len(values["lines"]),
                   "MainHsnCode": values["lines"][0]["hsn"], "Irn": values["irn"], "IrnDt": f"{bill['date']} 12:00:00"}
        pages = render_bill(bill, values, signed_qr(payload, key), rng)
        pages[0].save(directory / bill["file"], "PDF", resolution=200, save_all=True, append_images=pages[1:], quality=72)
        answers.append({"file": bill["file"], "case": bill["case"], "dmr": bill["dmr"], "site_note": bill["site_note"],
                        "supplier": bill["supplier"]["name"], "supplier_gstin": bill["supplier"]["gstin"],
                        "buyer_gstin": BUYER["gstin"], "bank_registration_gstin": BANK_REGISTRATION,
                        "invoice_number": bill["number"], "date": bill["date"], "tax_mode": bill["tax"],
                        "qr": payload, **{k: values[k] for k in ("lines", "taxable", "taxes", "tax", "round_off", "total")}})
    return answers


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    statement = sub.add_parser("statement")
    statement.add_argument("output", type=Path)
    bills = sub.add_parser("bills")
    bills.add_argument("output", type=Path)
    for command in (statement, bills):
        command.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    if args.command == "statement":
        summary = write_statement(args.output, args.seed)
        args.output.with_suffix(".expected.json").write_text(json.dumps(summary, indent=2) + "\n")
    else:
        answers = write_bills(args.output, args.seed)
        (args.output / "expected.json").write_text(json.dumps(answers, indent=2) + "\n")


if __name__ == "__main__":
    main()
