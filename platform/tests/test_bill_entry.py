"""Bill entry on runs, end to end on PostgreSQL with the fake Agents API.

Sessions are scripted like a model would work: read the pages they were
given, call the real lookup tools, and propose. Everything after that is the
real path: the gate, repeats across files, approvals, supplier creation,
native writes and readback receipts.
"""

import base64
import copy
import io
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import factory
import pytest
from fake_agents import FakeAgents, Script
from PIL import Image

from minkops_platform import desktop, lanes, run_controls, work
from minkops_platform.accounts import bill_entry, supplier_gst, sync
from minkops_platform.errors import ServiceError
from minkops_platform.runtime import openai_hosted
from minkops_platform.workflows import load_definition

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")
DEFINITION = load_definition(Path(__file__).resolve().parents[2] / "employees/accounts-desk/workflows/bill-entry")


def gstin(stem):
    """A checksum-valid synthetic GSTIN from its first fourteen characters."""
    total, factor = 0, 2
    for character in reversed(stem):
        product = supplier_gst.ALPHABET.index(character) * factor
        total += product // 36 + product % 36
        factor = 3 - factor
    return stem + supplier_gst.ALPHABET[(36 - total % 36) % 36]


BUYER, SUNRISE, CABINS = gstin("37ABCPR1234Q1Z"), gstin("37SUNPS5678K1Z"), gstin("37CABFC2610A1Z")


def ledger(guid, name, parent, **extra):
    return {"type": "LEDGER", "data": {"@_NAME": name, "GUID": guid, "PARENT": parent, "ALTERID": "1", **extra}}


def vtype(guid, name):
    return {"type": "VOUCHERTYPE", "data": {"@_NAME": name, "@_RESERVEDNAME": name, "GUID": guid, "PARENT": name,
                                            "ALTERID": "1", "ISACTIVE": "Yes"}}


def masters(company):
    return [
        {"type": "COMPANY", "data": {"@_NAME": company["name"], "GUID": company["guid"], "BOOKSFROM": "20260401",
                                     "STATENAME": "Andhra Pradesh", "GSTREGISTRATIONNUMBER": BUYER}},
        # A same-company Regular GST creditor: the template a new supplier's ledger is modelled on.
        ledger("g-sunrise", "Sunrise Office Systems", "Sundry Creditors", PARTYGSTIN=SUNRISE,
               GSTREGISTRATIONTYPE="Regular", LEDSTATENAME="Andhra Pradesh"),
        ledger("g-cabins", "Office Cabins", "Fixed Assets"), ledger("g-repairs", "Repairs and Maintenance", "Indirect Expenses"),
        ledger("g-cgst", "Input CGST 9%", "Duties & Taxes"), ledger("g-sgst", "Input SGST 9%", "Duties & Taxes"),
        ledger("g-round", "Round Off", "Indirect Expenses"), vtype("g-purchase", "Purchase"),
        vtype("g-journal", "Journal")]


# How the client booked Sunrise's last bill: the precedent a clean proposal follows.
PRIOR = {"GUID": "v-prior", "MASTERID": "5", "ALTERID": "3", "DATE": "20260710", "VOUCHERTYPENAME": "Purchase",
         "REFERENCE": "SOS/26/0007", "PARTYLEDGERNAME": "Sunrise Office Systems", "NARRATION": "Cabin",
         "ALLLEDGERENTRIES.LIST": [{"LEDGERNAME": "Sunrise Office Systems", "AMOUNT": "59000.00"},
                                   {"LEDGERNAME": "Office Cabins", "AMOUNT": "-50000.00"},
                                   {"LEDGERNAME": "Input CGST 9%", "AMOUNT": "-4500.00"},
                                   {"LEDGERNAME": "Input SGST 9%", "AMOUNT": "-4500.00"}]}


def invoice(supplier="Sunrise Office Systems", supplier_gstin=SUNRISE, number="SOS/26/0412", day="01-Sep-2026",
            taxable="160,000.00", tax="14,400.00", total="188,800.00", extra=()):
    return ["TAX INVOICE", supplier, f"GSTIN: {supplier_gstin}", f"Invoice No.: {number} Date: {day}",
            f"Billed to: Rehearsal Infra Private Limited GSTIN: {BUYER}",
            f"MS fabricated office cabin 1 {taxable} {taxable}", f"Taxable value {taxable}", f"CGST 9% {tax}",
            f"SGST 9% {tax}", *extra, f"Invoice total {total}", "1 / 1"]


B01 = factory.text_pdf(invoice())
B05 = factory.text_pdf(invoice(taxable="161,000.00", tax="14,490.00", total="189,980.00"))
B06 = factory.text_pdf(invoice(number="SOS/26/0413", day="02-Sep-2026", total="188,801.00"))
CABIN_DETAILS = ["GST Registration Type: Regular | State: Andhra Pradesh | State Code: 37",
                 "Address: Plot 12, Auto Nagar, Guntur 522001", "Place of supply: Andhra Pradesh (37)"]
B03 = factory.text_pdf(invoice(supplier="Cabin Services UAT", supplier_gstin=CABINS, number="CS/26/0001",
                               day="02-Sep-2026", taxable="7,500.00", tax="675.00", total="8,850.00",
                               extra=CABIN_DETAILS))
B03_NEXT = factory.text_pdf(invoice(supplier="Cabin Services UAT", supplier_gstin=CABINS, number="CS/26/0002",
                                    day="02-Sep-2026", taxable="1,000.00", tax="90.00", total="1,180.00",
                                    extra=CABIN_DETAILS))


def line(role, ledger_guid, amount, *, side="debit", tax=None):
    return {"role": role, "ledger_guid": ledger_guid, "side": side, "amount": amount, "cost_centre_guid": None,
            "cost_category_guid": None, "tax": tax, "tds": None, "evidence": f"Printed {role} {amount}"}


def proposal(company, n=1, **changes):
    """The scripted model's reading of B01: taxable 160,000.00, CGST and SGST 14,400.00 each, total 188,800.00."""
    entry = {
        "bill": n, "company_guid": company, "company_evidence": f"Billed to GSTIN {BUYER}.",
        "document": {"kind": "invoice", "number": "SOS/26/0412", "date": "2026-09-01", "total": 188800.0,
                     "supplier_name": "Sunrise Office Systems", "supplier_gstin": SUNRISE, "origin": "domestic",
                     "taxable": 160000.0, "tax": None, "receipt_register": None},
        "voucher": {"family": "purchase", "voucher_type_guid": "g-purchase",
                    "party": {"ledger_guid": "g-sunrise", "new_supplier": False, "evidence": "GSTIN matches."},
                    "lines": [line("expense", "g-cabins", 160000.0),
                              line("tax", "g-cgst", 14400.0, tax={"head": "cgst", "rate": 9, "taxable": 160000.0}),
                              line("tax", "g-sgst", 14400.0, tax={"head": "sgst", "rate": 9, "taxable": 160000.0})]},
        "supplier_details": None, "exception": None, "rules": [],
        "evidence": [{"field": "supplier_name", "page": 1, "quote": "Sunrise Office Systems"},
                     {"field": "total", "page": 1, "quote": "Invoice total 188,800.00"}]}
    for path, value in changes.items():
        target = entry
        *parents, last = path.split(".")
        for key in parents:
            target = target[int(key)] if key.isdigit() else target[key]
        target[int(last) if last.isdigit() else last] = value
    return entry


def revised(company, n=1):
    """B05: the same supplier, number and date as B01, with other amounts."""
    entry = proposal(company, n, **{"document.total": 189980.0, "document.taxable": 161000.0})
    entry["voucher"]["lines"] = [
        line("expense", "g-cabins", 161000.0),
        line("tax", "g-cgst", 14490.0, tax={"head": "cgst", "rate": 9, "taxable": 161000.0}),
        line("tax", "g-sgst", 14490.0, tax={"head": "sgst", "rate": 9, "taxable": 161000.0})]
    return entry


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(openai_hosted.time, "sleep", lambda seconds: None)


@pytest.fixture
def desk():
    """A client business with one authorised company on one PC, its books mirrored with one prior bill."""
    with factory.connect() as db:
        tenant = factory.tenant(db)
        operator = factory.user(db, tenant, role="admin")
        client = factory.client(db, tenant)
        device = factory.device(db, tenant, operator)
        company = factory.company(db, tenant, device, client, name="Rehearsal Infra Private Limited")
        factory.books(db, company, masters(company), [PRIOR])
        flow = {**factory.workflow(db, tenant), "config_values": {"review_mode": "all_outputs"}}
        db.commit()
        yield {"db": db, "tenant": tenant, "operator": operator, "client": client, "device": device,
               "company": company, "workflow": flow}


def launch(desk, files, **config):
    uploaded = factory.upload(desk["db"], desk["tenant"], desk["operator"], files)
    run = bill_entry.launch(desk["db"], tenant=desk["tenant"], user=desk["operator"], client=desk["client"],
                            workflow=desk["workflow"], definition=DEFINITION,
                            body={"file_ids": [f["id"] for f in uploaded], "config": config, "request_key": uuid4()})
    desk["db"].commit()
    return run


def items(desk, run):
    desk["db"].commit()
    return desk["db"].execute("SELECT * FROM run_items WHERE run_id=%s ORDER BY ordinal", (run["id"],)).fetchall()


def records(desk, run):
    desk["db"].commit()
    return desk["db"].execute("""SELECT r.* FROM run_records r JOIN run_items i ON i.id=r.item_id WHERE r.run_id=%s
                                 ORDER BY i.ordinal, r.position""", (run["id"],)).fetchall()


def record(desk, row):
    desk["db"].commit()
    return work.get_record(desk["db"], desk["tenant"]["id"], row["id"])


def refreshed(desk):
    """The PC finished the refresh the launch asked for."""
    db = desk["db"]
    db.execute("UPDATE desktop_jobs SET state='completed' WHERE device_id=%s AND operation='tally.sync'",
               (desk["device"]["id"],))
    work.release(db, desk["tenant"]["id"], sync.blocker(desk["device"]["id"]))
    db.commit()


def until(check, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.05)
    raise AssertionError("Timed out")


def read(desk, fake, run):
    """Refresh the PC's books, then run every file's session to its end."""
    refreshed(desk)
    with lanes.Host(os.environ["TEST_DATABASE_URL"], client=fake, tenant_id=desk["tenant"]["id"], lanes=2,
                    heartbeat_seconds=0.2, poll_seconds=0.3, close_seconds=0.1):
        until(lambda: all(i["state"] in ("done", "failed") for i in items(desk, run)))


def header(session):
    return json.loads(session.content[0]["text"])


def answers(session, name):
    """Every answer a scripted session received from one tool, parsed where it was not refused."""
    return [json.loads(a["text"]) if a["success"] else a["text"] for a in session.answers if a["name"] == name]


def by_file(**scripts):
    """Each session follows the script for the file it was given."""
    return FakeAgents(script_for=lambda metadata, content: Script(*scripts[json.loads(content[0]["text"])["file"]]))


def readback(plan, guid="tally-1", lines=None):
    """What the companion reads back from Tally for this bill: the plan's voucher, or one with other lines.

    Tally signs debits negative, an inward item's amounts included.
    """
    sign = lambda side: 1 if side == "credit" else -1  # noqa: E731
    return {"guid": guid, "master_id": "71", "date": plan["header"]["date"].replace("-", ""),
            "voucher_type": plan["voucher_type"]["NAME"], "family": plan["family"], "reference": plan["header"]["reference"],
            "number": "", "narration": plan["header"]["narration"], "party_ledger": plan["header"]["party_ledger"],
            "tag": None, "fingerprint": f"fp-{guid}", "allocations": [],
            "bills": [{"ledger": ln["ledger"], "name": bill.get("name"), "type": bill["type"],
                       "amount_cents": sign(ln["side"]) * bill["amount_cents"]}
                      for ln in plan["lines"] for bill in ln.get("bills") or []],
            "inventory": [{**{key: e[key] for key in ("item", "unit", "quantity", "rate", "ledger")},
                           "amount_cents": sign(e["side"]) * e["amount_cents"],
                           "godowns": [{**g, "amount_cents": sign(e["side"]) * g["amount_cents"]} for g in e["godowns"]]}
                          for e in plan.get("inventory") or []],
            "lines": lines or [{"ledger": ln["ledger"], "amount_cents": sign(ln["side"]) * ln["amount_cents"]}
                               for ln in plan["lines"]]}


def saved(operation, plan):
    return {"outcome": "saved", "company_guid": plan["company_guid"], "current": readback(plan)}


def companion(desk, respond=saved):
    """The PC claims its next native write, fetches the stored plan, and reports `respond(operation, plan)`."""
    db = desk["db"]
    device = db.execute("SELECT * FROM desktop_devices WHERE id=%s", (desk["device"]["id"],)).fetchone()
    job = desktop.claim(db, device, desktop.companion_report("0.10.0", "Rehearsal PC", "console"))
    if job is None or job["operation"] not in ("tally.write", "tally.supplier"):
        db.rollback()
        return None
    plan = desktop.plan(db, device, job["id"], job["claim_token"], 6)
    desktop.finish(db, device, job["id"], {"claim_token": job["claim_token"], "result": respond(job["operation"], plan)})
    db.commit()
    return job["operation"], plan


def decide(desk, row, action):
    db = desk["db"]
    current = record(desk, row)
    run = work.get_run(db, desk["tenant"]["id"], current["run_id"])
    try:
        receipt = work.decide(db, tenant_id=desk["tenant"]["id"], record_id=current["id"], version=current["version"],
                              actor_id=desk["operator"]["id"], action=action,
                              apply=lambda locked: bill_entry.HANDLER.decide(db, run, locked, action, {},
                                                                             {"user": desk["operator"]}))
    except ServiceError:
        db.rollback()
        raise
    db.commit()
    return receipt


def actions(row):
    return [a["action"] for a in bill_entry.HANDLER.summarize(None, row).get("actions", [])]


def test_a_bill_waits_for_the_refresh_then_is_read_from_its_pages_and_checked_as_it_is_proposed(desk):
    company = desk["company"]["guid"]

    def misread(answers_so_far, session):
        # The total is read as 188,000.00: no such figure is printed, so it cannot be the bill's total.
        return [("propose", {"count": 1, "bills": [proposal(company, **{"document.total": 188000.0})]})]

    fake = by_file(**{"sunrise-0412.pdf": [
        [("find_company", {"subjects": [BUYER]}), ("find_ledger", {"subjects": [SUNRISE]}),
         ("check_gstin", {"values": [SUNRISE, SUNRISE[:-1] + ("A" if SUNRISE[-1] != "A" else "B")]}),
         ("party_history", {"company": company, "ledgers": ["g-sunrise", "Sunrise"]})],
        misread, [("propose", {"count": 1, "bills": [proposal(company)]})]]})
    run = launch(desk, {"sunrise-0412.pdf": B01})
    [item] = items(desk, run)
    [waiting] = records(desk, run)
    # Nothing is read until the PC's Tally copy is current.
    assert (item["state"], item["waiting_on"]) == ("waiting", sync.blocker(desk["device"]["id"]))
    assert (waiting["status"], waiting["facts"]) == ("pending", {"file": "sunrise-0412.pdf", "bill": 1})
    read(desk, fake, run)
    [session] = fake.created
    assert header(session) == {"file": "sunrise-0412.pdf", "pages": 1, "company_mode": "infer", "companies": [
        {"name": "Rehearsal Infra Private Limited", "guid": company, "books_from": "2026-04-01"}]}
    # Each page arrives as its text layer and as an image the model reads either way.
    assert session.content[1]["text"].startswith("Page 1 of 1. Text layer:\nTAX INVOICE\nSunrise Office Systems")
    assert session.content[2]["image_url"].startswith("data:image/jpeg;base64,")
    [found] = answers(session, "find_company")
    assert (found["companies"][0]["gstins"], found["companies"][0]["matches"]) == ([BUYER], [BUYER])
    assert [ln["name"] for ln in answers(session, "find_ledger")[0]["results"][0]["ledgers"]] == ["Sunrise Office Systems"]
    assert [r["valid"] for r in answers(session, "check_gstin")[0]["results"]] == [True, False]
    # History is asked for by the GUIDs find_ledger gives; a subject that is no ledger is named, never dropped.
    [history] = answers(session, "party_history")
    assert ([v["reference"] for v in history["vouchers"]], history["unknown_ledgers"]) == (["SOS/26/0007"], ["Sunrise"])
    first, second = answers(session, "propose")
    assert first == {"bills": [{"bill": 1, "status": "rejected", "reason": (
        "The bill's text does not print 188000.00 as its total. Use the figure the bill prints.")}],
        "still_pending": [1]}
    # The corrected reading is accepted, and the change after a refusal is shown to the reviewer.
    assert second["bills"][0]["status"] == "accepted"
    [bill] = records(desk, run)
    assert bill["status"] == "proposed" and bill["checks"]["submissions"] == 2
    assert bill["review_reasons"] == ["The bill was read differently after a refusal: total 188000.0 became 188800.0."]
    assert bill["proposal"]["preview"] == {
        "company": "Rehearsal Infra Private Limited", "voucher_type": "Purchase", "family": "purchase",
        "date": "2026-09-01", "number": "SOS/26/0412", "party": "Sunrise Office Systems", "total": 188800.0,
        "lines": [{"ledger": "Sunrise Office Systems", "side": "credit", "amount": 188800.0},
                  {"ledger": "Office Cabins", "side": "debit", "amount": 160000.0},
                  {"ledger": "Input CGST 9%", "side": "debit", "amount": 14400.0},
                  {"ledger": "Input SGST 9%", "side": "debit", "amount": 14400.0}]}
    assert actions(bill) == ["approve", "nothing"]
    assert work.get_run(desk["db"], desk["tenant"]["id"], run["id"])["state"] == "review"


def test_an_approved_bill_is_saved_once_and_tally_holding_another_version_is_never_overwritten(desk):
    company = desk["company"]["guid"]
    fake = by_file(**{"sunrise.pdf": [[("propose", {"count": 1, "bills": [proposal(company)]})]],
                      "sunrise-resubmitted.pdf": [[("propose", {"count": 1, "bills": [proposal(company)]})]],
                      "sunrise-revised.pdf": [[("propose", {"count": 1, "bills": [revised(company)]})]]})
    first = launch(desk, {"sunrise.pdf": B01})
    read(desk, fake, first)
    [bill] = records(desk, first)
    assert decide(desk, bill, "approve")["status"] == "writing"
    # A companion that predates protocol 6 is refused the plan before it touches Tally.
    db = desk["db"]
    device = db.execute("SELECT * FROM desktop_devices WHERE id=%s", (desk["device"]["id"],)).fetchone()
    job = desktop.claim(db, device, desktop.companion_report("0.10.0", "Rehearsal PC", "console"))
    with pytest.raises(ServiceError, match="Update Minkops on this PC"):
        desktop.plan(db, device, job["id"], job["claim_token"], 5)
    db.rollback()
    operation, plan = companion(desk)
    assert (operation, plan["format_version"], plan["family"], plan["voucher_type"]["NAME"]) == (
        "tally.write", 6, "purchase", "Purchase")
    assert plan["header"]["reference"] == "SOS/26/0412" and plan["header"]["party_ledger"] == "Sunrise Office Systems"
    assert plan["duplicate"]["window"] == {"from": "2026-04-01", "to": "2027-03-31"}
    bill = record(desk, bill)
    assert (bill["status"], bill["current"]["invoice_number"], bill["current"]["guid"]) == ("saved", "SOS/26/0412",
                                                                                            "tally-1")
    # Submitted again in a later run, Tally already has exactly this bill: it is verified, not added.
    again = launch(desk, {"sunrise-resubmitted.pdf": B01})
    read(desk, fake, again)
    [copy_] = records(desk, again)
    decide(desk, copy_, "approve")
    companion(desk, lambda operation, plan: {"outcome": "duplicate", "current": readback(plan)})
    assert record(desk, copy_)["status"] == "duplicate"
    # A revised version under the same number meets the saved one: it holds, and nothing is overwritten.
    revision = launch(desk, {"sunrise-revised.pdf": B05})
    read(desk, fake, revision)
    [changed] = records(desk, revision)
    decide(desk, changed, "approve")
    existing = readback(plan)
    companion(desk, lambda operation, revised_plan: {"outcome": "correction", "current": existing})
    changed = record(desk, changed)
    assert (changed["status"], changed["hold_codes"]) == ("held", ["save_held"])
    # The reviewer is told what differs, so the voucher can be checked in Tally at a glance.
    assert changed["review_reasons"] == ["Tally's voucher for SOS/26/0412 comes to 188800.00, not 189980.00, with other "
                                         "amounts for Input CGST 9%, Input SGST 9%, Office Cabins. Review it there; "
                                         "Minkops did not add a second voucher."]
    assert changed["current"]["entries"][0] == {"ledger": "Sunrise Office Systems", "amount": 18880000}
    assert actions(changed) == ["retry_save", "nothing"]
    assert desk["db"].execute("SELECT count(*) AS n FROM native_writes WHERE company_id=%s",
                              (desk["company"]["id"],)).fetchone()["n"] == 3


def scan(text_colour=(0, 0, 0)):
    """A photographed bill: one image with no text layer."""
    image = Image.new("RGB", (1200, 1600), (255, 255, 255))
    image.putpixel((10, 10), text_colour)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_a_bill_in_several_files_is_written_once_and_different_printed_versions_all_hold(desk):
    company = desk["company"]["guid"]
    # The scan's session books the same bill to another expense ledger; the first file's reading is the one written.
    scanned = proposal(company, **{"voucher.lines.0.ledger_guid": "g-repairs"})
    fake = by_file(**{"a-sunrise.pdf": [[("propose", {"count": 1, "bills": [proposal(company)]})]],
                      "b-sunrise-copy.pdf": [[("propose", {"count": 1, "bills": [proposal(company)]})]],
                      "c-sunrise-scan.png": [[("propose", {"count": 1, "bills": [scanned]})]],
                      "d-sunrise-revised.pdf": [[("propose", {"count": 1, "bills": [revised(company)]})]]})
    run = launch(desk, {"a-sunrise.pdf": B01, "b-sunrise-copy.pdf": B01, "c-sunrise-scan.png": scan()})
    read(desk, fake, run)
    original, copy_, photo = records(desk, run)
    assert photo["proposal"]["repeat_of"] == copy_["proposal"]["repeat_of"] == str(original["id"])
    assert copy_["review_reasons"] == ["This bill is also in a-sunrise.pdf; it is entered once."]
    # Approving any copy approves the one record that writes the bill.
    decide(desk, photo, "approve")
    assert record(desk, original)["status"] == "writing"
    operation, plan = companion(desk)
    assert [ln["ledger"] for ln in plan["lines"]] == ["Sunrise Office Systems", "Office Cabins", "Input CGST 9%",
                                                      "Input SGST 9%"]
    assert companion(desk) is None
    assert [record(desk, r)["status"] for r in (original, copy_, photo)] == ["saved", "duplicate", "duplicate"]
    assert record(desk, photo)["current"]["guid"] == "tally-1"
    # Files printing different versions of one bill all hold: neither can be chosen silently.
    conflict = launch(desk, {"a-sunrise.pdf": B01, "d-sunrise-revised.pdf": B05})
    read(desk, fake, conflict)
    assert [(r["status"], r["hold_codes"], r["review_reasons"]) for r in records(desk, conflict)] == [
        ("held", ["source_values_conflict"], ["Selected files print different versions of this bill."])] * 2


def new_supplier(company, n=1, number="CS/26/0001", total=8850.0):
    taxable, tax = round(total / 1.18, 2), round((total - total / 1.18) / 2, 2)
    entry = proposal(company, n, **{
        "document.number": number, "document.date": "2026-09-02", "document.total": total,
        "document.taxable": taxable, "document.supplier_name": "Cabin Services UAT", "document.supplier_gstin": CABINS,
        "voucher.party": {"ledger_guid": None, "new_supplier": True, "evidence": "No ledger has this GSTIN or name."}})
    entry["voucher"]["lines"] = [
        line("expense", "g-repairs", taxable),
        line("tax", "g-cgst", tax, tax={"head": "cgst", "rate": 9, "taxable": taxable}),
        line("tax", "g-sgst", tax, tax={"head": "sgst", "rate": 9, "taxable": taxable})]
    entry["evidence"] = [{"field": "supplier_name", "page": 1, "quote": "Cabin Services UAT"}]
    entry["supplier_details"] = {
        "gstin": CABINS, "registration_type": "Regular", "state": "Andhra Pradesh", "state_code": "37",
        "place_of_supply": "Andhra Pradesh (37)", "address": ["Plot 12, Auto Nagar, Guntur"], "pincode": "522001",
        "evidence": [{"field": "gstin", "page": 1, "quote": f"GSTIN: {CABINS}"},
                     {"field": "registration_type", "page": 1, "quote": "GST Registration Type: Regular"},
                     {"field": "state", "page": 1, "quote": "State: Andhra Pradesh | State Code: 37"},
                     {"field": "place_of_supply", "page": 1, "quote": "Place of supply: Andhra Pradesh (37)"},
                     {"field": "address", "page": 1, "quote": "Address: Plot 12, Auto Nagar, Guntur 522001"}]}
    return entry


def created(details_state="Andhra Pradesh"):
    """The companion created the ledger, read Tally's masters back, and exported the new ledger's GST details."""
    def respond(operation, plan):
        assert operation == "tally.supplier"
        return {"company_guid": plan["company_guid"], "current": None,
                "ledgers": [{"@_NAME": "Sunrise Office Systems", "GUID": "g-sunrise", "PARENT": "Sundry Creditors"},
                            {"@_NAME": plan["vendor"], "GUID": "g-new", "PARENT": "Sundry Creditors", "ALTERID": "7"}],
                "supplier": {"@_NAME": plan["vendor"], "GUID": "g-new", "PARENT": "Sundry Creditors",
                             "LEDGSTREGDETAILS.LIST": {"GSTIN": CABINS, "GSTREGISTRATIONTYPE": "Regular",
                                                       "PLACEOFSUPPLY": "Andhra Pradesh"},
                             "LEDMAILINGDETAILS.LIST": {"STATE": details_state, "PINCODE": "522001",
                                                        "ADDRESS.LIST": {"ADDRESS": ["Plot 12, Auto Nagar, Guntur"]}}}}
    return respond


def test_a_new_supplier_is_created_only_on_approval_and_its_bills_then_follow(desk):
    company = desk["company"]["guid"]
    lookup = [("find_ledger", {"subjects": [CABINS, "Cabin Services"]})]
    fake = by_file(**{"cabins-1.pdf": [lookup, [("propose", {"count": 1, "bills": [new_supplier(company)]})]],
                      "cabins-2.pdf": [[("propose", {"count": 1, "bills": [new_supplier(company, number="CS/26/0002",
                                                                                         total=1180.0)]})]]})
    run = launch(desk, {"cabins-1.pdf": B03, "cabins-2.pdf": B03_NEXT})
    read(desk, fake, run)
    session = next(s for s in fake.created if header(s)["file"] == "cabins-1.pdf")
    assert answers(session, "find_ledger")[0]["results"][0]["ledgers"] == []
    first, second = records(desk, run)
    # The gate holds a bill whose supplier has no ledger at its first proposal: only a person may create one.
    assert answers(session, "propose")[0]["bills"][0]["status"] == "held" and first["checks"]["submissions"] == 1
    assert (first["hold_codes"], first["review_reasons"]) == (["supplier_missing"], [
        "Supplier 'Cabin Services UAT' has no ledger in Rehearsal Infra Private Limited. Create it, then this bill "
        "can be saved."])
    assert actions(first) == ["supplier", "nothing", "retry"]
    detail = bill_entry.HANDLER.detail(desk["db"], work.get_run(desk["db"], desk["tenant"]["id"], run["id"]), first)
    assert (detail["new_supplier"]["name"], detail["new_supplier"]["gstin"]) == ("Cabin Services UAT", CABINS)
    assert desk["db"].execute("SELECT count(*) AS n FROM native_writes WHERE run_id=%s", (run["id"],)).fetchone()["n"] == 0
    # The readback disagrees with the bill's GST details: nothing is written and the bill keeps its offer.
    assert decide(desk, first, "supplier")["status"] == "writing"
    operation, plan = companion(desk, created(details_state="Telangana"))
    assert (plan["kind"], plan["vendor"], plan["gst_supplier"]["gstin"]) == ("supplier", "Cabin Services UAT", CABINS)
    assert plan["gst_supplier"]["template"]["name"] == "Sunrise Office Systems"
    first = record(desk, first)
    assert (first["status"], first["hold_codes"], first["review_reasons"]) == (
        "held", ["supplier_missing"], ["The supplier's GST details in Tally differ from the bill. Review the ledger "
                                       "there."])
    assert actions(first) == ["supplier", "nothing", "retry"] and companion(desk) is None
    # Verified, the new ledger becomes the party: this bill is written, and the other bill from it is proposed.
    decide(desk, first, "supplier")
    companion(desk, created())
    operation, plan = companion(desk)
    assert (operation, plan["header"]["party_ledger"]) == ("tally.write", "Cabin Services UAT")
    assert plan["references"]["ledgers"]["Cabin Services UAT"] == {"GUID": "g-new", "PARENT": "Sundry Creditors",
                                                                   "ALTERID": "7"}
    assert record(desk, first)["status"] == "saved"
    second = record(desk, second)
    assert (second["status"], second["review_reasons"]) == ("proposed", [bill_entry.UNPRECEDENTED])
    assert second["proposal"]["preview"]["party"] == "Cabin Services UAT"


def test_exceptions_hold_with_their_reasons_and_a_best_guess_must_still_pass_the_gate(desk):
    company = desk["company"]["guid"]
    unaddressed = {"bill": 1, "document": None, "company_guid": None, "company_evidence": None, "voucher": None,
                   "supplier_details": None, "rules": [],
                   "evidence": [{"field": "buyer", "page": 1, "quote": "Billed to: Unknown"}],
                   "exception": {"code": "company_unresolved", "detail": "The buyer is none of the client's companies."}}
    unsure = proposal(company, exception={"code": "classification_uncertain", "detail": "Asset or repairs?"})
    early = proposal(company, **{"document.date": "2026-03-31"})
    # Told the date is before the books begin, the model tries to hold the bill for something weaker.
    reframed = proposal(company, **{"document.date": "2026-03-31"},
                        exception={"code": "classification_uncertain", "detail": "How to book a bill outside the books?"})
    unbalanced = proposal(company, **{"document.number": "SOS/26/0413", "document.date": "2026-09-02",
                                      "document.total": 188801.0})
    # Told the lines fall a rupee short, the model invents a round-off: no round-off line prints one.
    invented = copy.deepcopy(unbalanced)
    invented["voucher"]["lines"].append(line("round_off", "g-round", 1.0))
    conflict = {**unbalanced, "exception": {"code": "source_values_conflict", "detail": "Total is 188,801.00."}}
    fake = by_file(**{"unaddressed.pdf": [[("propose", {"count": 1, "bills": [unaddressed]})]],
                      "unsure.pdf": [[("propose", {"count": 1, "bills": [unsure]})]],
                      "early.pdf": [[("propose", {"count": 1, "bills": [early]})],
                                    [("propose", {"count": 1, "bills": [reframed]})]],
                      "unbalanced.pdf": [[("propose", {"count": 1, "bills": [unbalanced]})],
                                         [("propose", {"count": 1, "bills": [invented]})],
                                         [("propose", {"count": 1, "bills": [conflict]})]]})
    run = launch(desk, {"unaddressed.pdf": B01, "unsure.pdf": B01, "early.pdf": B01, "unbalanced.pdf": B06})
    read(desk, fake, run)
    nobody, guessable, before_books, contradicted = records(desk, run)
    assert (nobody["hold_codes"], nobody["review_reasons"], actions(nobody)) == (
        ["company_unresolved"], ["The buyer is none of the client's companies."], ["nothing", "retry"])
    # A complete candidate held for its treatment may be written as a best guess; the gate has checked it.
    assert (guessable["hold_codes"], actions(guessable)) == (["classification_uncertain"], ["guess", "nothing", "retry"])
    # A date before the books begin holds at once: no resubmission can change a printed date, nor recast the hold.
    assert (before_books["hold_codes"], before_books["checks"]["submissions"]) == (["date_before_books"], 1)
    session = next(s for s in fake.created if header(s)["file"] == "early.pdf")
    assert answers(session, "propose")[1]["bills"][0]["status"] == "held"
    session = next(s for s in fake.created if header(s)["file"] == "unbalanced.pdf")
    refusals = [result["bills"][0] for result in answers(session, "propose")]
    assert refusals[0]["reason"].startswith("The lines come to 188800.00, but the bill's printed total is 188801.00.")
    assert refusals[1]["reason"] == "The bill's text does not print 1.00 as its round-off. Use the figure the bill prints."
    assert (contradicted["hold_codes"], contradicted["review_reasons"]) == (["source_values_conflict"],
                                                                            ["Total is 188,801.00."])
    assert actions(contradicted) == ["nothing", "retry"]
    decide(desk, guessable, "guess")
    companion(desk)
    guessed = record(desk, guessable)
    assert (guessed["status"], guessed["review_reasons"]) == ("saved", [bill_entry.GUESSED])
    with pytest.raises(ServiceError, match="not available"):
        decide(desk, nobody, "guess")


SECOND = factory.text_pdf(invoice(), invoice(number="SOS/26/0420", day="02-Sep-2026", taxable="10,000.00",
                                             tax="900.00", total="11,800.00"))


def second_bill(company, n=2):
    """The file's second invoice: SOS/26/0420, taxable 10,000.00 and total 11,800.00."""
    entry = proposal(company, n, **{"document.number": "SOS/26/0420", "document.date": "2026-09-02",
                                    "document.total": 11800.0, "document.taxable": 10000.0})
    entry["voucher"]["lines"] = [
        line("expense", "g-cabins", 10000.0),
        line("tax", "g-cgst", 900.0, tax={"head": "cgst", "rate": 9, "taxable": 10000.0}),
        line("tax", "g-sgst", 900.0, tax={"head": "sgst", "rate": 9, "taxable": 10000.0})]
    return entry


def test_a_file_of_several_bills_keeps_its_decided_bills_through_a_recheck(desk):
    company = desk["company"]["guid"]
    unsure = proposal(company, exception={"code": "classification_uncertain", "detail": "Asset or repairs?"})
    # First taken for three bills, the file is read again as two: the third, untouched by anyone, goes.
    reading = [[("propose", {"count": 3, "bills": [unsure, second_bill(company), second_bill(company, 3)]})],
               [("propose", {"count": 2, "bills": [unsure]})]]
    recheck = [[("propose", {"count": 1, "bills": [proposal(company)]})],
               [("propose", {"count": 2, "bills": [proposal(company), second_bill(company)]})]]
    sessions = iter([reading, recheck])
    fake = FakeAgents(script_for=lambda metadata, content: Script(*next(sessions)))
    run = launch(desk, {"two-bills.pdf": SECOND})
    read(desk, fake, run)
    first, second = records(desk, run)
    assert [(r["facts"]["bill"], r["status"]) for r in (first, second)] == [(1, "held"), (2, "proposed")]
    decide(desk, second, "approve")
    companion(desk)
    assert record(desk, second)["status"] == "saved"
    # Recheck reads the whole file again; the saved bill keeps its number and stays as it is.
    assert decide(desk, first, "retry")["status"] == "pending"
    with lanes.Host(os.environ["TEST_DATABASE_URL"], client=fake, tenant_id=desk["tenant"]["id"], lanes=2,
                    heartbeat_seconds=0.2, poll_seconds=0.3, close_seconds=0.1):
        until(lambda: items(desk, run)[0]["state"] == "done" and record(desk, first)["status"] != "pending")
    session = fake.created[-1]
    assert header(session)["decided_bills"] == [{"bill": 2, "status": "saved", "supplier": "Sunrise Office Systems",
                                                 "number": "SOS/26/0420", "date": "2026-09-02"}]
    refused, answered = answers(session, "propose")
    assert refused == "Bill 2 of this file is already saved, so the file holds at least 2 bills."
    assert answered["bills"] == [{"bill": 1, "status": "accepted"},
                                 {"bill": 2, "status": "saved", "reason": "Already decided."}]
    assert [(r["facts"]["bill"], r["status"]) for r in records(desk, run)] == [(1, "proposed"), (2, "saved")]


def test_a_locked_run_enters_bills_into_its_company_and_a_year_split_routes_by_date(desk):
    db, company = desk["db"], desk["company"]
    # The same company's previous year, split off in Tally: one GUID, books beginning a year earlier.
    earlier = factory.company(db, desk["tenant"], desk["device"], desk["client"], name="Rehearsal Infra (2025-26)",
                              guid=company["guid"], books_from="2025-04-01")
    factory.books(db, earlier, masters(earlier))
    sister = factory.company(db, desk["tenant"], desk["device"], desk["client"], name="Sister Infra")
    factory.books(db, sister, masters(sister))
    db.commit()
    march = proposal(company["guid"], **{"document.date": "2026-03-02"})
    elsewhere = proposal(sister["guid"])
    held = {**elsewhere, "exception": {"code": "company_unresolved", "detail": "Addressed to Sister Infra."}}
    fake = by_file(**{"march.pdf": [[("propose", {"count": 1, "bills": [march]})]],
                      "sister.pdf": [[("propose", {"count": 1, "bills": [elsewhere]})],
                                     [("propose", {"count": 1, "bills": [held]})]]})
    run = launch(desk, {"march.pdf": B01, "sister.pdf": B01}, company_mode="locked",
                 locked_company_guid=company["guid"])
    read(desk, fake, run)
    session = next(s for s in fake.created if header(s)["file"] == "march.pdf")
    assert header(session)["locked_company_guid"] == company["guid"]
    assert sorted((c["name"], c["books_from"]) for c in header(session)["companies"]) == [
        ("Rehearsal Infra (2025-26)", "2025-04-01"), ("Rehearsal Infra Private Limited", "2026-04-01"),
        ("Sister Infra", "2026-04-01")]
    in_march, to_sister = records(desk, run)
    # A bill from March belongs to the part whose books cover it.
    assert (in_march["status"], in_march["company_id"], in_march["facts"]["company"]) == (
        "proposed", earlier["id"], "Rehearsal Infra (2025-26)")
    sister_session = next(s for s in fake.created if header(s)["file"] == "sister.pdf")
    assert answers(sister_session, "propose")[0]["bills"][0]["reason"].startswith(
        "This run enters every bill into its locked company.")
    assert (to_sister["status"], to_sister["hold_codes"]) == ("held", ["company_unresolved"])
    with pytest.raises(ServiceError, match="Choose one of this client's companies"):
        launch(desk, {"any.pdf": B01}, company_mode="locked", locked_company_guid="not-a-company")


def test_a_scan_is_read_from_its_image_and_an_unreadable_file_holds_without_a_session(desk):
    company = desk["company"]["guid"]
    fake = by_file(**{"photo.jpg": [[("propose", {"count": 1, "bills": [proposal(company)]})]]})
    photo = io.BytesIO()
    Image.open(io.BytesIO(scan())).save(photo, format="JPEG")
    run = launch(desk, {"photo.jpg": photo.getvalue(), "damaged.pdf": b"%PDF-1.7 truncated"})
    read(desk, fake, run)
    [session] = fake.created
    assert [part["type"] for part in session.content] == ["input_text", "input_text", "input_image"]
    assert session.content[1]["text"] == "Page 1 of 1. A scan with no text layer."
    assert Image.open(io.BytesIO(base64.b64decode(session.content[2]["image_url"].split(",", 1)[1]))).format == "JPEG"
    photographed, damaged = records(desk, run)
    # With no text layer, the figures read from the image stand; the gate still checks them.
    assert photographed["status"] == "proposed"
    assert (damaged["status"], damaged["hold_codes"], damaged["review_reasons"]) == (
        "held", ["source_unreadable"], ["The PDF could not be opened; it may be damaged or password-protected."])


DEPOT = gstin("37STRDP4321K1Z")
STORES = [ledger("g-depot", "Stores Depot", "Sundry Creditors"),
          ledger("g-spares", "Spares Purchase", "Purchase Accounts", DESCRIPTION="Spares received into the site stores.")]
# How the client booked Stores Depot's last bill: item-wise, its stock line posting to spares.
ITEM_WISE = {"GUID": "v-depot", "MASTERID": "6", "ALTERID": "4", "DATE": "20260801", "VOUCHERTYPENAME": "Purchase",
             "REFERENCE": "SD/26/0101", "PARTYLEDGERNAME": "Stores Depot", "NARRATION": "Spares",
             "ALLLEDGERENTRIES.LIST": [{"LEDGERNAME": "Stores Depot", "AMOUNT": "11800.00"},
                                       {"LEDGERNAME": "Input CGST 9%", "AMOUNT": "-900.00"},
                                       {"LEDGERNAME": "Input SGST 9%", "AMOUNT": "-900.00"}],
             "ALLINVENTORYENTRIES.LIST": [{"STOCKITEMNAME": "Bucket tooth", "BILLEDQTY": "50 Nos", "AMOUNT": "-10000.00",
                                           "ACCOUNTINGALLOCATIONS.LIST": [{"LEDGERNAME": "Spares Purchase",
                                                                           "AMOUNT": "-10000.00"}]}]}


def test_a_supplier_booked_item_wise_shows_its_items_and_a_plain_reading_waits_for_a_person(desk):
    company = desk["company"]["guid"]
    factory.books(desk["db"], desk["company"], masters(desk["company"]) + STORES, [PRIOR, ITEM_WISE])
    plain = second_bill(company, 1)
    plain["document"].update(number="SD/26/0150", supplier_name="Stores Depot", supplier_gstin=DEPOT)
    plain["voucher"]["party"]["ledger_guid"] = "g-depot"
    plain["voucher"]["lines"][0]["ledger_guid"] = "g-spares"
    fake = by_file(**{"depot.pdf": [[("find_ledger", {"company": company, "subjects": ["Spares"]}),
                                     ("party_history", {"company": company, "ledgers": ["g-depot"]})],
                                    [("propose", {"count": 1, "bills": [plain]})]]})
    bill = factory.text_pdf(invoice(supplier="Stores Depot", supplier_gstin=DEPOT, number="SD/26/0150",
                                    day="02-Sep-2026", taxable="10,000.00", tax="900.00", total="11,800.00"))
    run = launch(desk, {"depot.pdf": bill}, review_mode="only_exceptions")
    read(desk, fake, run)
    [session] = fake.created
    # A ledger's description is the client's own note on what it records.
    [found] = answers(session, "find_ledger")
    assert found["results"][0]["ledgers"] == [{"name": "Spares Purchase", "guid": "g-spares", "group": "Purchase Accounts",
                                               "description": "Spares received into the site stores."}]
    [history] = answers(session, "party_history")
    assert history["vouchers"][0]["items"] == [{"item": "Bucket tooth", "quantity": "50 Nos", "amount": "10000.00",
                                                "ledgers": ["Spares Purchase"]}]
    # Booked without the items this supplier's bills carried, the bill has no precedent: even under standing
    # approval it waits for a person.
    [proposed] = records(desk, run)
    assert (proposed["status"], proposed["review_reasons"]) == ("proposed", [bill_entry.UNPRECEDENTED])


def repairs(company, number):
    """A Sunrise bill of 10,000.00 and 9% CGST and SGST, booked to repairs: unlike Sunrise's earlier bills."""
    entry = second_bill(company, 1)
    entry["document"]["number"] = number
    entry["voucher"]["lines"][0]["ledger_guid"] = "g-repairs"
    return entry


def repairs_pdf(number):
    return factory.text_pdf(invoice(number=number, day="02-Sep-2026", taxable="10,000.00", tax="900.00",
                                    total="11,800.00"))


def test_an_approved_verified_booking_is_learnt_and_an_edit_in_tally_sends_its_next_bill_to_review(desk):
    from minkops_platform.accounts import memory
    company, db = desk["company"]["guid"], desk["db"]

    def bill(number, **config):
        name = f"{number.replace('/', '-')}.pdf"
        fake = by_file(**{name: [[("propose", {"count": 1, "bills": [repairs(company, number)]})]]})
        run = launch(desk, {name: repairs_pdf(number)}, **config)
        read(desk, fake, run)
        return records(desk, run)[0]

    # A first booking for the supplier waits for a person; their approval and Tally's readback teach it.
    first = bill("SOS/26/0501")
    assert first["review_reasons"] == [bill_entry.UNPRECEDENTED]
    decide(desk, first, "approve")
    companion(desk)
    learnt = db.execute("SELECT * FROM memory_entries WHERE company_id=%s AND kind='booking'",
                        (desk["company"]["id"],)).fetchone()
    # A booking is the treatment: the voucher type and expense ledgers, not the taxes the bill printed.
    assert (learnt["guids"][0], learnt["status"], learnt["uses"]) == ("g-sunrise", "confirmed", 1)
    assert learnt["value"] == {"supplier": "Sunrise Office Systems", "voucher_type": "Purchase",
                               "ledgers": ["Repairs and Maintenance"]}
    # One approval confirms the booking: under standing approval the next such bill is written unreviewed.
    second = bill("SOS/26/0502", review_mode="only_exceptions")
    assert (second["status"], second["review_reasons"]) == ("writing", [])
    companion(desk)
    # The same booking again is one entry, used twice.
    assert [row["uses"] for row in db.execute("SELECT uses FROM memory_entries WHERE company_id=%s AND kind='booking'",
                                               (desk["company"]["id"],))] == [2]
    # Someone rebooked the first bill to cabins in Tally: the next sync demotes what Minkops learnt.
    saved = {**PRIOR, "GUID": "tally-1", "ALTERID": "9", "REFERENCE": "SOS/26/0501", "DATE": "20260902",
             "ALLLEDGERENTRIES.LIST": [{"LEDGERNAME": "Sunrise Office Systems", "AMOUNT": "11800.00"},
                                       {"LEDGERNAME": "Office Cabins", "AMOUNT": "-10000.00"},
                                       {"LEDGERNAME": "Input CGST 9%", "AMOUNT": "-900.00"},
                                       {"LEDGERNAME": "Input SGST 9%", "AMOUNT": "-900.00"}]}
    version = factory.books(db, desk["company"], masters(desk["company"]), [PRIOR, saved])
    memory.revalidate(db, desk["company"], version)
    db.commit()
    third = bill("SOS/26/0503", review_mode="only_exceptions")
    assert (third["status"], third["review_reasons"]) == ("proposed", [bill_entry.DEMOTED])


def test_a_bill_waits_on_its_companys_open_practice_and_the_answer_releases_it(desk):
    from minkops_platform import attention
    from minkops_platform.accounts import mirror, practice
    company, db = desk["company"]["guid"], desk["db"]
    # Too little history settles neither where this company types invoice numbers nor its receipt register.
    task = db.execute("INSERT INTO tasks(tenant_id,title) VALUES (%s,'Sync') RETURNING id",
                      (desk["tenant"]["id"],)).fetchone()
    practice.probe(db, desk["company"], mirror.latest(db, desk["company"]["id"]), {"task_id": task["id"]})
    rule = db.execute(
        """INSERT INTO memory_instructions(tenant_id,client_id,employee_key,workflow_key,text)
           VALUES (%s,%s,'accounts-desk','bill-entry','Cabin bills go to Office Cabins.') RETURNING *""",
        (desk["tenant"]["id"], desk["client"]["id"])).fetchone()
    db.commit()
    stamped = proposal(company, **{"document.receipt_register": {"label": "DMR", "number": "1811", "date": "2026-09-02"},
                                   "rules": [str(rule["id"])]})
    unknown = proposal(company, rules=["00000000-0000-4000-8000-000000000000"])
    fake = by_file(**{"stamped.pdf": [
        [("practice", {"company": company}), ("rules", {}),
         ("memory", {"company": company, "subjects": ["g-sunrise"]})],
        [("propose", {"count": 1, "bills": [unknown]})], [("propose", {"count": 1, "bills": [stamped]})]]})
    run = launch(desk, {"stamped.pdf": B01})
    read(desk, fake, run)
    [session] = fake.created
    [practices] = answers(session, "practice")
    assert {p["subject"]: p["value"] for p in practices["practices"]}["billwise"] == {"in_use": False, "share": 0.0}
    assert {q["subject"] for q in practices["open_questions"]} >= {"receipt_register", "invoice_number_field"}
    assert answers(session, "rules")[0]["rules"] == [{"id": str(rule["id"]), "version": 1,
                                                      "text": "Cabin bills go to Office Cabins."}]
    assert answers(session, "memory")[0] == {"entries": []}
    refused = answers(session, "propose")[0]["bills"][0]
    assert (refused["status"], refused["reason"]) == ("rejected", (
        "Rule 00000000-0000-4000-8000-000000000000 is not one of this client's active rules for this workflow. "
        "Cite only rules the rules lookup returns."))
    # The stamp's number goes where the company records it, which nobody has said yet: the bill waits.
    [waiting] = records(desk, run)
    assert (waiting["status"], waiting["hold_codes"], actions(waiting)) == ("held", ["practice_question"], ["nothing"])
    assert waiting["proposal"]["rules"] == [{"id": str(rule["id"]), "version": 1,
                                             "text": "Cabin bills go to Office Cabins."}]
    card = db.execute("""SELECT a.* FROM attention_items a JOIN practice_questions q ON q.attention_item_id=a.id
                         WHERE q.company_id=%s AND q.probe='receipt_register'""", (desk["company"]["id"],)).fetchone()
    assert attention.decide(db, desk["tenant"], desk["operator"], card["id"], "narration")["status"] == "answered"
    db.commit()
    released = record(desk, waiting)
    assert (released["status"], released["hold_codes"]) == ("proposed", [])
    decide(desk, released, "approve")
    _, plan = companion(desk)
    # The narration carries the register number; with the invoice field still open, duplicates are sought in both.
    assert plan["header"]["narration"] == "Minkops reviewed bill SOS/26/0412; DMR 1811 of 2026-09-02"
    assert plan["duplicate"]["number_fields"] == ["REFERENCE", "NARRATION"]


def test_standing_approval_writes_only_bills_booked_as_before_and_stop_holds_the_rest(desk):
    company = desk["company"]["guid"]
    # Booked to repairs, a first for this supplier: it waits for a person even under standing approval.
    first_time = second_bill(company, 1)
    first_time["voucher"]["lines"][0]["ledger_guid"] = "g-repairs"
    fake = by_file(**{"usual.pdf": [[("propose", {"count": 1, "bills": [proposal(company)]})]],
                      "first-time.pdf": [[("propose", {"count": 1, "bills": [first_time]})]]})
    run = launch(desk, {"usual.pdf": B01, "first-time.pdf": SECOND}, review_mode="only_exceptions")
    read(desk, fake, run)
    usual, unprecedented = records(desk, run)
    assert usual["status"] == "writing"
    assert (unprecedented["status"], unprecedented["review_reasons"]) == ("proposed", [bill_entry.UNPRECEDENTED])
    # The note is the reviewer's: the session only learns its bill was accepted, so it never bends a sound
    # proposal to avoid review.
    session = next(s for s in fake.created if header(s)["file"] == "first-time.pdf")
    assert answers(session, "propose") == [{"bills": [{"bill": 1, "status": "accepted"}]}]
    # Stop withdraws the write no PC has started, and every unsaved bill holds; Stop is final.
    db = desk["db"]
    task = work.get_run(db, desk["tenant"]["id"], run["id"])["task_id"]
    run_controls.task_control(db, desk["tenant"]["id"], desk["operator"], task, "stop")
    db.commit()
    assert [(r["status"], r["hold_codes"]) for r in records(desk, run)] == [("held", ["run_stopped"])] * 2
    assert actions(record(desk, usual)) == ["nothing"]
    assert companion(desk) is None
    assert db.execute("SELECT outcome FROM native_writes WHERE run_id=%s", (run["id"],)).fetchone()["outcome"] == (
        "cancelled")
