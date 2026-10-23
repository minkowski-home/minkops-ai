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
from references import by_reference, looked_up, named

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


def names_of(*companies):
    """What the fixtures' masters are called, each company's own included, for a scripted model to look them up."""
    return named([record for company in companies for record in masters(company)] + STORES + STOCK)


def proposing(names, *bills, count=1):
    """A scripted model's rounds for these bills, written by GUID: it looks up what they cite, then proposes."""
    return looked_up("propose", {"count": count, "bills": list(bills)}, names)


def reproposing(names, *bills, count=1):
    """Proposing these bills again, by the references the session's earlier lookups gave it."""
    return by_reference("propose", {"count": count, "bills": list(bills)}, names)


def line(role, ledger_guid, amount, *, side="debit", tax=None, supply=None):
    return {"role": role, "ledger_guid": ledger_guid, "side": side, "amount": amount, "cost_centre_guid": None,
            "cost_category_guid": None, "tax": tax, "tds": None, "gst_rate": None, "supply": supply,
            "evidence": f"Printed {role} {amount}"}


def proposal(company, n=1, **changes):
    """The scripted model's reading of B01: taxable 160,000.00, CGST and SGST 14,400.00 each, total 188,800.00."""
    entry = {
        "bill": n, "company_guid": company, "company_evidence": f"Billed to GSTIN {BUYER}.",
        "document": {"kind": "invoice", "number": "SOS/26/0412", "date": "2026-09-01", "total": 188800.0,
                     "supplier_name": "Sunrise Office Systems", "supplier_gstin": SUNRISE, "origin": "domestic",
                     "buyer_gstin": BUYER, "place_of_supply": None, "taxable": 160000.0, "tax": None,
                     "receipt_register": None, "adjustments": None,
                     "cost_split": None},
        "voucher": {"family": "purchase", "voucher_type_guid": "g-purchase",
                    "party": {"ledger_guid": "g-sunrise", "new_supplier": False, "evidence": "GSTIN matches."},
                    "lines": [line("expense", "g-cabins", 160000.0, supply="goods"),
                              line("tax", "g-cgst", 14400.0, tax={"head": "cgst", "rate": 9, "taxable": 160000.0}),
                              line("tax", "g-sgst", 14400.0, tax={"head": "sgst", "rate": 9, "taxable": 160000.0})],
                    "items": None},
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


def gst_masters(company):
    """The company's books with GST switched on, as TallyPrime keeps a registered company's."""
    found = masters(company)
    for record in found:
        data = record["data"]
        if record["type"] == "COMPANY":
            data["ISGSTON"] = "Yes"
        if data.get("GUID") in ("g-cgst", "g-sgst"):
            data.update(TAXTYPE="GST", GSTDUTYHEAD="CGST" if data["GUID"] == "g-cgst" else "SGST/UTGST",
                        RATEOFTAXCALCULATION="9")
        if data.get("GUID") == "g-sunrise":
            data["LEDGSTREGDETAILS.LIST"] = {"APPLICABLEFROM": "20170701", "GSTIN": SUNRISE, "GSTREGISTRATIONTYPE": "Regular"}
            data["LEDMAILINGDETAILS.LIST"] = {"APPLICABLEFROM": "20170701", "STATE": "Andhra Pradesh", "COUNTRY": "India"}
    return [*found, {"type": "TAXUNIT", "data": {"@_NAME": company["name"], "GUID": "g-taxunit", "GSTREGNUMBER": BUYER}}]


@pytest.fixture
def desk(request):
    """A client business with one authorised company on one PC, its books mirrored with one prior bill.

    Marked `gst`, the company has GST switched on in Tally.
    """
    books = gst_masters if request.node.get_closest_marker("gst") else masters
    with factory.connect() as db:
        tenant = factory.tenant(db)
        operator = factory.user(db, tenant, role="admin")
        client = factory.client(db, tenant)
        device = factory.device(db, tenant, operator)
        company = factory.company(db, tenant, device, client, name="Rehearsal Infra Private Limited")
        factory.books(db, company, books(company), [PRIOR])
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
    """Every answer a scripted session received from one tool, parsed where it was not refused.

    A proposal is the session's final answer, so its verdicts are the ones the worker logged for each turn.
    """
    if name == bill_entry.PROPOSAL.tool.name:
        with factory.connect() as db:
            return [json.loads(row["answer"]) if row["success"] else row["answer"] for row in db.execute(
                """SELECT success, answer FROM tool_calls WHERE session_id=%s AND call_id LIKE 'answer:%%'
                   ORDER BY created_at""", (session.id,))]
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
    job = desktop.claim(db, device, desktop.companion_report("0.11.0", "Rehearsal PC", "console"))
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
    company, names = desk["company"]["guid"], names_of(desk["company"])
    # The total is read as 188,000.00: no such figure is printed, so it cannot be the bill's total.
    misread = proposal(company, **{"document.total": 188000.0})
    fake = by_file(**{"sunrise-0412.pdf": [
        [("find_company", {"subjects": [BUYER]}), ("find_ledger", {"subjects": [SUNRISE]}),
         ("check_gstin", {"values": [SUNRISE, SUNRISE[:-1] + ("A" if SUNRISE[-1] != "A" else "B")]}),
         # A bill printing no GSTIN has none to check: an empty list is answered, not refused.
         ("check_gstin", {"values": []}),
         ("party_history", {"company": "C1", "ledgers": ["L1", "Sunrise"]})],
        *proposing(names, misread), reproposing(names, proposal(company))]})
    run = launch(desk, {"sunrise-0412.pdf": B01})
    [item] = items(desk, run)
    [waiting] = records(desk, run)
    # Nothing is read until the PC's Tally copy is current.
    assert (item["state"], item["waiting_on"]) == ("waiting", sync.blocker(desk["device"]["id"]))
    assert (waiting["status"], waiting["facts"]) == ("pending", {"file": "sunrise-0412.pdf", "bill": 1})
    read(desk, fake, run)
    [session] = fake.created
    assert header(session) == {"file": "sunrise-0412.pdf", "pages": 1, "company_mode": "infer", "companies": [
        {"name": "Rehearsal Infra Private Limited", "ref": "C1", "books_from": "2026-04-01"}]}
    # Each page arrives as its text layer and as an image the model reads either way.
    assert session.content[1]["text"].startswith("Page 1 of 1. Text layer:\nTAX INVOICE\nSunrise Office Systems")
    assert session.content[2]["image_url"].startswith("data:image/jpeg;base64,")
    [found] = answers(session, "find_company")
    assert (found["companies"][0]["gstins"], found["companies"][0]["matches"]) == ([BUYER], [BUYER])
    # Searching every company, a ledger names its company; each master is a reference, never its GUID.
    assert answers(session, "find_ledger")[0]["results"][0]["ledgers"] == [{
        "name": "Sunrise Office Systems", "ref": "L1", "group": "Sundry Creditors", "gstin": SUNRISE,
        "company": "Rehearsal Infra Private Limited", "company_ref": "C1"}]
    checked, nothing = answers(session, "check_gstin")
    assert ([r["valid"] for r in checked["results"]], nothing) == ([True, False], {"results": []})
    # History is asked for by the references find_ledger gives; a subject that is no ledger is named, never dropped.
    [history] = answers(session, "party_history")
    assert ([v["reference"] for v in history["vouchers"]], history["unknown_ledgers"]) == (["SOS/26/0007"], ["Sunrise"])
    first, second = answers(session, "propose")
    assert first == {"bills": [{"bill": 1, "status": "rejected", "reason": (
        "The bill's text does not print 1,88,000.00 as its total. Use the figure the bill prints.")}],
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


def test_a_date_written_day_first_is_sent_back_to_be_read_again_never_held_as_before_the_books(desk):
    """B01 prints 01-Sep-2026. Read into a year-first date as 0901-01-26, it contradicts the session's own quote;
    with no quote, a year no bill carries is implausible. Each is refused, so the bill is read again, not held."""
    company, names = desk["company"]["guid"], names_of(desk["company"])
    quoted = [{"field": "date", "page": 1, "quote": "Invoice No.: SOS/26/0412 Date: 01-Sep-2026"}]
    scrambled = proposal(company, **{"document.date": "0901-01-26"})
    scrambled["evidence"] += quoted
    distant = proposal(company, **{"document.date": "3126-09-01"})
    fake = by_file(**{"sunrise-0412.pdf": [*proposing(names, scrambled), reproposing(names, distant),
                                           reproposing(names, proposal(company))]})
    run = launch(desk, {"sunrise-0412.pdf": B01})
    read(desk, fake, run)
    [session] = fake.created
    first, second, third = answers(session, "propose")
    assert first["bills"][0] == {"bill": 1, "status": "rejected", "reason": (
        "The bill prints its date as \u201cInvoice No.: SOS/26/0412 Date: 01-Sep-2026\u201d, which is 2026-09-01, "
        "not 0901-01-26. Write the date year first, as YYYY-MM-DD.")}
    assert second["bills"][0] == {"bill": 1, "status": "rejected", "reason": (
        "3126-09-01 is not a plausible bill date. Read the date the bill prints again, and write it year first, "
        "as YYYY-MM-DD.")}
    assert third["bills"][0]["status"] == "accepted"
    [bill] = records(desk, run)
    assert (bill["status"], bill["facts"]["date"]) == ("proposed", "2026-09-01")
    assert bill["review_reasons"] == ["The bill was read differently after a refusal: date 0901-01-26 became 2026-09-01."]


def test_printed_dates_are_read_day_first_and_month_first_where_the_print_allows_both():
    assert bill_entry.printed_dates("Invoice date 31-Aug-2026") == {"2026-08-31"}
    assert bill_entry.printed_dates("DATE : 02.10.26 / Due 01/11/2026") == {"2026-10-02", "2026-02-10", "2026-11-01",
                                                                                  "2026-01-11"}
    assert bill_entry.printed_dates("Oct 1, 2026") == {"2026-10-01"}
    assert bill_entry.printed_dates("RA No. 011 / 02-Oct-2026") == {"2026-10-02"}
    assert bill_entry.printed_dates("2026-09-01") == {"2026-09-01"}
    # A day past the month's end, or a bare number, is no date.
    assert bill_entry.printed_dates("31/09/2026 and FX26/011") == set()


def test_a_bill_cites_only_masters_its_session_was_given(desk):
    """Tally numbers masters in sequence, so a guessed GUID can name another real ledger: a session cites only the
    references its own lookups gave it."""
    db, company = desk["db"], desk["company"]
    sister = factory.company(db, desk["tenant"], desk["device"], desk["client"], name="Sister Infra")
    factory.books(db, sister, masters(sister))
    db.commit()
    names = names_of(company, sister)
    lookups, right = proposing(names, proposal(company["guid"]))

    def citing(ledger):
        def round_(answers, session):
            [(tool, arguments)] = right(answers, session)
            arguments["bills"][0]["voucher"]["lines"][0]["ledger"] = ledger
            return [(tool, arguments)]
        return round_

    # Each bill has three submissions: one file tries a reference never given and one of another kind, the other
    # a ledger given from the other company.
    fake = by_file(**{"guessed.pdf": [lookups, citing("L99"), citing("T1"), right],
                      "elsewhere.pdf": [lookups, [("find_ledger", {"company": "C2", "subjects": ["Office Cabins"]})],
                                        citing("L5"), right]})
    run = launch(desk, {"guessed.pdf": B01, "elsewhere.pdf": B01})
    read(desk, fake, run)
    reasons = {}
    for session in fake.created:
        reasons[header(session)["file"]] = [a["bills"][0].get("reason") for a in answers(session, "propose")]
    assert reasons == {
        "guessed.pdf": ["L99 is not a reference this session was given. Look the ledger up with find_ledger, and use "
                        "the reference it gives.", "T1 is a voucher type, not a ledger.", None],
        "elsewhere.pdf": ["L5 is another company's ledger. Look it up in this company with find_ledger.", None]}
    session = next(s for s in fake.created if header(s)["file"] == "elsewhere.pdf")
    # The other company's Office Cabins was given as L5; this company's as L2.
    assert answers(session, "find_ledger")[1]["results"][0]["ledgers"][0]["ref"] == "L5"
    assert [r["status"] for r in records(desk, run)] == ["proposed", "proposed"]
    assert records(desk, run)[0]["proposal"]["preview"]["lines"][1]["ledger"] == "Office Cabins"
    # A GUID is no reference at all: the contract the answer is constrained to refuses it before any check.
    [(tool, arguments)] = right(session.answers, session)
    arguments["bills"][0]["voucher"]["lines"][0]["ledger"] = "g-cabins"
    from minkops_platform.runtime.tools import compute
    assert compute({tool: bill_entry.PROPOSAL.tool}, None, tool, arguments) == (
        False, "Invalid bills/0/voucher/lines/0/ledger: 'g-cabins' does not match '^[A-Z][1-9][0-9]{0,4}$'")


def stored(plan, status):
    """What a companion from 0.11.0 reads back of a GST save: the details it wrote, and Tally's verdict."""
    party = plan["gst"]["party"]
    return {"party_gstin": party["gstin"], "registration_type": party["registration_type"], "state": party["state"],
            "country": party["country"], "place_of_supply": party["place_of_supply"],
            "company_gstin": plan["gst"]["company_gstin"], "status": status}


@pytest.mark.gst
def test_a_bill_for_a_gst_registered_company_states_what_tallys_returns_need_and_says_when_tally_leaves_it_out(desk):
    names, company = names_of(desk["company"]), desk["company"]["guid"]
    fake = by_file(**{"sunrise.pdf": proposing(names, proposal(company)),
                      "next.pdf": proposing(names, proposal(company, **{"document.number": "SOS/26/0413",
                                                                       "document.date": "2026-09-02"}))})
    first = launch(desk, {"sunrise.pdf": B01})
    read(desk, fake, first)
    [bill] = records(desk, first)
    assert (bill["status"], bill["review_reasons"]) == ("proposed", [])
    decide(desk, bill, "approve")

    def uncertain(operation, plan):
        receipt = saved(operation, plan)
        return {**receipt, "current": {**receipt["current"], "gst": stored(plan, "uncertain")}}
    _, plan = companion(desk, uncertain)
    assert plan["gst"] == {"party": {"gstin": SUNRISE, "registration_type": "Regular", "state": "Andhra Pradesh",
                                     "country": "India", "place_of_supply": "Andhra Pradesh"},
                           "company_gstin": BUYER, "registration": None}
    assert {ln["ledger"]: ln.get("gst") for ln in plan["lines"]}["Office Cabins"] == {
        "taxability": "Taxable", "supply": "Goods", "rates": {"cgst": "9", "sgst": "9", "igst": "18", "cess": "0"}}
    # Saved and verified, but Tally leaves it out of its returns: the person is told, never left to find out.
    bill = record(desk, bill)
    assert (bill["status"], bill["current"]["gst"]["status"]) == ("saved", "uncertain")
    assert bill["review_reasons"] == [bill_entry.RETURNS_NOTES["uncertain"]]
    # Included, the save needs nothing more; a readback without what was written is never taken as saved.
    second = launch(desk, {"next.pdf": factory.text_pdf(invoice(number="SOS/26/0413", day="02-Sep-2026"))})
    read(desk, fake, second)
    [nxt] = records(desk, second)
    decide(desk, nxt, "approve")
    with pytest.raises(ServiceError, match="GST details Minkops wrote"):
        companion(desk)
    desk["db"].rollback()
    assert record(desk, nxt)["status"] == "writing"
    companion(desk, lambda operation, plan: {**saved(operation, plan),
                                             "current": {**readback(plan), "gst": stored(plan, "included")}})
    assert (record(desk, nxt)["status"], record(desk, nxt)["review_reasons"]) == ("saved", [])


def test_an_approved_bill_is_saved_once_and_tally_holding_another_version_is_never_overwritten(desk):
    names = names_of(desk["company"])
    company = desk["company"]["guid"]
    fake = by_file(**{"sunrise.pdf": proposing(names, proposal(company)),
                      "sunrise-resubmitted.pdf": proposing(names, proposal(company)),
                      "sunrise-revised.pdf": proposing(names, revised(company))})
    first = launch(desk, {"sunrise.pdf": B01})
    read(desk, fake, first)
    [bill] = records(desk, first)
    assert decide(desk, bill, "approve")["status"] == "writing"
    # A companion that predates protocol 6 is refused the plan before it touches Tally.
    db = desk["db"]
    device = db.execute("SELECT * FROM desktop_devices WHERE id=%s", (desk["device"]["id"],)).fetchone()
    job = desktop.claim(db, device, desktop.companion_report("0.11.0", "Rehearsal PC", "console"))
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
    assert changed["review_reasons"] == ["Tally's voucher for SOS/26/0412 comes to 1,88,800.00, not 1,89,980.00, with other "
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


def test_a_bill_held_in_one_file_and_proposed_in_another_names_its_copy_and_waits_for_a_person(desk):
    """Read twice, one copy held and one proposed: each says where the other is, and neither is approved unasked."""
    names = names_of(desk["company"])
    company = desk["company"]["guid"]
    unsure = proposal(company, exception={"code": "classification_uncertain", "detail": "Asset or repairs?"})
    fake = by_file(**{"a-sunrise.pdf": proposing(names, proposal(company)),
                      "b-sunrise-copy.pdf": proposing(names, unsure)})
    run = launch(desk, {"a-sunrise.pdf": B01, "b-sunrise-copy.pdf": B01}, review_mode="only_exceptions")
    read(desk, fake, run)
    proposed, held = records(desk, run)
    assert (proposed["status"], held["status"]) == ("proposed", "held")
    assert proposed["review_reasons"][-1] == ("This bill is also in b-sunrise-copy.pdf, held there: Asset or "
                                              "repairs?")
    assert held["review_reasons"] == ["Asset or repairs?",
                                      "This bill is also in a-sunrise.pdf, where it is proposed; it is entered once."]


def test_a_bill_held_in_two_files_names_its_copy_in_each(desk):
    """Both copies held, as a scanned duplicate often is: each still says where the other is, so neither is entered
    on its own after a person settles the first."""
    names = names_of(desk["company"])
    company = desk["company"]["guid"]
    unsure = proposal(company, exception={"code": "classification_uncertain", "detail": "Asset or repairs?"})
    fake = by_file(**{"a-sunrise.pdf": proposing(names, unsure), "b-sunrise-scan.pdf": proposing(names, unsure)})
    run = launch(desk, {"a-sunrise.pdf": B01, "b-sunrise-scan.pdf": B01})
    read(desk, fake, run)
    first, second = records(desk, run)
    assert (first["status"], second["status"]) == ("held", "held")
    assert first["review_reasons"] == ["Asset or repairs?",
                                       "This bill is also in b-sunrise-scan.pdf, held there too; it is entered once."]
    assert second["review_reasons"] == ["Asset or repairs?",
                                        "This bill is also in a-sunrise.pdf, held there too; it is entered once."]


def test_a_bill_held_for_its_own_exception_also_shows_what_the_checks_find_in_its_voucher(desk):
    """A person resolving the session's question sees every other problem with the proposed voucher at once."""
    names = names_of(desk["company"])
    company = desk["company"]["guid"]
    unsure = proposal(company, exception={"code": "classification_uncertain", "detail": "Asset or repairs?"},
                      **{"voucher.lines.1.ledger_guid": "g-sgst"})
    run = launch(desk, {"a-sunrise.pdf": B01})
    read(desk, by_file(**{"a-sunrise.pdf": proposing(names, unsure)}), run)
    [held] = records(desk, run)
    assert (held["status"], held["hold_codes"]) == ("held", ["classification_uncertain"])
    assert held["review_reasons"][0] == "Asset or repairs?"
    assert held["review_reasons"][1].startswith("Checking the proposed voucher: Input SGST 9% ")


def test_a_bill_in_several_files_is_written_once_and_different_printed_versions_all_hold(desk):
    names = names_of(desk["company"])
    company = desk["company"]["guid"]
    # The scan's session books the same bill to another expense ledger; the first file's reading is the one written.
    scanned = proposal(company, **{"voucher.lines.0.ledger_guid": "g-repairs"})
    fake = by_file(**{"a-sunrise.pdf": proposing(names, proposal(company)),
                      "b-sunrise-copy.pdf": proposing(names, proposal(company)),
                      "c-sunrise-scan.png": proposing(names, scanned),
                      "d-sunrise-revised.pdf": proposing(names, revised(company))})
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
    names = names_of(desk["company"])
    company = desk["company"]["guid"]
    lookup = [("find_ledger", {"subjects": [CABINS, "Cabin Services"]})]
    fake = by_file(**{"cabins-1.pdf": [lookup, *proposing(names, new_supplier(company))],
                      "cabins-2.pdf": proposing(names, new_supplier(company, number="CS/26/0002",
                                                                                         total=1180.0))})
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
    names = names_of(desk["company"])
    company = desk["company"]["guid"]
    unaddressed = {"bill": 1, "document": None, "company_guid": None, "company_evidence": None, "voucher": None,
                   "supplier_details": None, "rules": [],
                   "evidence": [{"field": "buyer", "page": 1, "quote": "Billed to: Unknown"}],
                   "exception": {"code": "company_unresolved", "detail": "The buyer is none of the client's companies."}}
    # The model writes its detail by reference; the reviewer reads names.
    unsure = proposal(company, exception={"code": "classification_uncertain", "detail": "L2 or repairs, in C1?"})
    early = proposal(company, **{"document.date": "2026-03-31"})
    # Told the date is before the books begin, the model tries to hold the bill for something weaker.
    reframed = proposal(company, **{"document.date": "2026-03-31"},
                        exception={"code": "classification_uncertain", "detail": "How to book a bill outside the books?"})
    unbalanced = proposal(company, **{"document.number": "SOS/26/0413", "document.date": "2026-09-02",
                                      "document.total": 188801.0})
    short = second_bill(company)
    short["document"]["total"] = 11801.0
    # Told the lines fall a rupee short, the model invents a round-off: no round-off line prints one.
    invented = copy.deepcopy(unbalanced)
    invented["voucher"]["lines"].append(line("round_off", "g-round", 1.0))
    conflict = {**unbalanced, "exception": {"code": "source_values_conflict", "detail": "Total is 188,801.00."}}
    fake = by_file(**{"unaddressed.pdf": proposing(names, unaddressed),
                      "unsure.pdf": proposing(names, unsure),
                      # The second bill is refused, and answering again the model tries to recast the first.
                      "early.pdf": [*proposing(names, early, short, count=2),
                                    reproposing(names, reframed, second_bill(company), count=2)],
                      # The invented round-off line cites a ledger the model looks up first.
                      "unbalanced.pdf": [*proposing(names, unbalanced), *proposing(names, invented),
                                         reproposing(names, conflict)]})
    run = launch(desk, {"unaddressed.pdf": B01, "unsure.pdf": B01, "early.pdf": SECOND, "unbalanced.pdf": B06})
    read(desk, fake, run)
    nobody, guessable, before_books, corrected, contradicted = records(desk, run)
    assert (nobody["hold_codes"], nobody["review_reasons"], actions(nobody)) == (
        ["company_unresolved"], ["The buyer is none of the client's companies."], ["nothing", "retry"])
    # A complete candidate held for its treatment may be written as a best guess; the gate has checked it.
    assert (guessable["hold_codes"], actions(guessable)) == (["classification_uncertain"], ["guess", "nothing", "retry"])
    assert guessable["review_reasons"] == ["Office Cabins or repairs, in Rehearsal Infra Private Limited?"]
    # A date before the books begin holds at once: no resubmission can change a printed date, nor recast the hold.
    assert (before_books["hold_codes"], before_books["checks"]["submissions"]) == (["date_before_books"], 1)
    session = next(s for s in fake.created if header(s)["file"] == "early.pdf")
    assert answers(session, "propose")[1]["bills"][0]["status"] == "held"
    assert record(desk, before_books)["hold_codes"] == ["date_before_books"] and corrected["status"] == "proposed"
    session = next(s for s in fake.created if header(s)["file"] == "unbalanced.pdf")
    refusals = [result["bills"][0] for result in answers(session, "propose")]
    assert refusals[0]["reason"].startswith("The lines come to 1,88,800.00, but the bill's printed total is 1,88,801.00.")
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
    names = names_of(desk["company"])
    company = desk["company"]["guid"]
    unsure = proposal(company, exception={"code": "classification_uncertain", "detail": "Asset or repairs?"})
    # First taken for three bills, the third refused as the file prints no such total; corrected, the file is read
    # as two: the third, untouched by anyone, goes.
    phantom = second_bill(company, 3)
    phantom["document"]["total"] = 11801.0
    reading = [*proposing(names, unsure, second_bill(company), phantom, count=3),
               reproposing(names, unsure, count=2)]
    recheck = [*proposing(names, proposal(company)), reproposing(names, proposal(company), second_bill(company), count=2)]
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
    names = names_of(company, earlier, sister)
    march = proposal(company["guid"], **{"document.date": "2026-03-02"})
    elsewhere = proposal(sister["guid"])
    held = {**elsewhere, "exception": {"code": "company_unresolved", "detail": "Addressed to Sister Infra."}}
    fake = by_file(**{"march.pdf": proposing(names, march),
                      "sister.pdf": [*proposing(names, elsewhere), reproposing(names, held)]})
    run = launch(desk, {"march.pdf": B01, "sister.pdf": B01}, company_mode="locked",
                 locked_company_guid=company["guid"])
    read(desk, fake, run)
    session = next(s for s in fake.created if header(s)["file"] == "march.pdf")
    # A year split's parts share one reference; the locked company is named by it.
    assert header(session)["locked_company"] == "C1"
    assert sorted((c["name"], c["ref"], c["books_from"]) for c in header(session)["companies"]) == [
        ("Rehearsal Infra (2025-26)", "C1", "2025-04-01"), ("Rehearsal Infra Private Limited", "C1", "2026-04-01"),
        ("Sister Infra", "C2", "2026-04-01")]
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


SISTER = gstin("37SISIF4321B1Z")


def registered_as(company, number):
    """The company's books, registered under this GSTIN without GST switched on in Tally."""
    found = masters(company)
    found[0]["data"]["GSTREGISTRATIONNUMBER"] = number
    return found


def test_a_bill_addressed_to_another_of_the_clients_companies_is_never_entered_into_this_one(desk):
    """The buyer's GSTIN routes a bill, even into a company Tally keeps without GST, whose own checks cannot see it."""
    db = desk["db"]
    sister = factory.company(db, desk["tenant"], desk["device"], desk["client"], name="Sister Infra")
    factory.books(db, sister, registered_as(sister, SISTER))
    db.commit()
    names = names_of(desk["company"], sister)
    wrong = proposal(desk["company"]["guid"], **{"document.buyer_gstin": SISTER})
    held = {**wrong, "exception": {"code": "company_unresolved", "detail": "Addressed to Sister Infra."}}
    fake = by_file(**{"sister.pdf": [*proposing(names, wrong), reproposing(names, held)]})
    run = launch(desk, {"sister.pdf": B01})
    read(desk, fake, run)
    assert answers(fake.created[-1], "propose")[0]["bills"][0]["reason"] == (
        f"The bill is addressed to GSTIN {SISTER}, which is Sister Infra's, not Rehearsal Infra Private Limited's. "
        "Choose Sister Infra with find_company.")
    (row,) = records(desk, run)
    assert (row["status"], row["hold_codes"]) == ("held", ["company_unresolved"])
    # Every company was available: nothing was left out of the run.
    assert db.execute("SELECT count(*) AS n FROM attention_items WHERE event_key=%s",
                      (f"run:{run['id']}:unavailable",)).fetchone()["n"] == 0


def test_a_run_names_the_books_a_disconnected_pc_held_and_holds_their_bills(desk):
    db = desk["db"]
    laptop = factory.device(db, desk["tenant"], desk["operator"])
    sister = factory.company(db, desk["tenant"], laptop, desk["client"], name="Sister Infra")
    factory.books(db, sister, registered_as(sister, SISTER))
    desktop.revoke(db, desk["tenant"], desk["operator"], laptop["id"])
    db.commit()
    names = names_of(desk["company"])
    # Without Sister Infra in the run, the session sees one company: the bill's GSTIN still names its buyer.
    wrong = proposal(desk["company"]["guid"], **{"document.buyer_gstin": SISTER})
    fake = by_file(**{"sister.pdf": proposing(names, wrong)})
    run = launch(desk, {"sister.pdf": B01})
    left = db.execute("SELECT * FROM attention_items WHERE event_key=%s", (f"run:{run['id']}:unavailable",)).fetchone()
    assert (left["identifier"], left["label"], left["task_id"]) == ("Sister Infra", "Books left out of this run",
                                                                   run["task_id"])
    assert left["target"]["reason"] == (
        f"Sister Infra was on {laptop['name']}, which was disconnected, so this run holds work addressed to it. "
        "Connect the PC that holds it now and continue it from its \"New company found\" card, then enter that work "
        "in a new run.")
    read(desk, fake, run)
    (row,) = records(desk, run)
    # Final at once: no reading of this run can reach books it does not hold.
    assert (row["status"], row["hold_codes"]) == ("held", ["company_unresolved"])
    assert row["review_reasons"] == [
        f"The bill is addressed to GSTIN {SISTER}, which is Sister Infra's, whose books were on {laptop['name']}, "
        "which was disconnected. Continue them on the PC that holds them now, then enter this bill in a new run."]


def test_a_scan_is_read_from_its_image_and_an_unreadable_file_holds_without_a_session(desk):
    names = names_of(desk["company"])
    company = desk["company"]["guid"]
    fake = by_file(**{"photo.jpg": proposing(names, proposal(company))})
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
          ledger("g-spares", "Spares Purchase", "Purchase Accounts", DESCRIPTION="Spares received into the site stores.",
                 AFFECTSSTOCK="Yes")]
# The stock Stores Depot's bills carry: an item counted in whole numbers, and two godowns.
STOCK = [{"type": "UNIT", "data": {"@_NAME": "Nos", "GUID": "u-nos", "DECIMALPLACES": "0", "ISSIMPLEUNIT": "Yes"}},
         {"type": "STOCKITEM", "data": {"@_NAME": "Bucket tooth", "GUID": "s-tooth", "ALTERID": "2", "PARENT": "Spares",
                                        "BASEUNITS": "Nos", "ISBATCHWISEON": "No",
                                        "HSNDETAILS.LIST": {"APPLICABLEFROM": "20250401", "HSNCODE": "84314990"}}},
         {"type": "GODOWN", "data": {"@_NAME": "Main Location", "GUID": "gd-main"}},
         {"type": "GODOWN", "data": {"@_NAME": "Site Stores", "GUID": "gd-site", "PARENT": "Main Location"}}]
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
    names = names_of(desk["company"])
    company = desk["company"]["guid"]
    factory.books(desk["db"], desk["company"], masters(desk["company"]) + STORES, [PRIOR, ITEM_WISE])
    plain = second_bill(company, 1)
    plain["document"].update(number="SD/26/0150", supplier_name="Stores Depot", supplier_gstin=DEPOT)
    plain["voucher"]["party"]["ledger_guid"] = "g-depot"
    plain["voucher"]["lines"][0]["ledger_guid"] = "g-spares"
    fake = by_file(**{"depot.pdf": [[("find_ledger", {"company": "C1", "subjects": ["Spares"]}),
                                     ("party_history", {"company": "C1", "ledgers": ["Stores Depot"]})],
                                    *proposing(names, plain)]})
    bill = factory.text_pdf(invoice(supplier="Stores Depot", supplier_gstin=DEPOT, number="SD/26/0150",
                                    day="02-Sep-2026", taxable="10,000.00", tax="900.00", total="11,800.00"))
    run = launch(desk, {"depot.pdf": bill}, review_mode="only_exceptions")
    read(desk, fake, run)
    [session] = fake.created
    # A ledger's description is the client's own note on what it records.
    found = answers(session, "find_ledger")[0]
    assert found["results"][0]["ledgers"] == [{"name": "Spares Purchase", "ref": "L1", "group": "Purchase Accounts",
                                               "description": "Spares received into the site stores."}]
    [history] = answers(session, "party_history")
    assert history["vouchers"][0]["items"] == [{"item": "Bucket tooth", "quantity": "50 Nos", "amount": "10000.00",
                                                "ledgers": ["Spares Purchase"]}]
    # Booked without the items this supplier's bills carried, the bill has no precedent: even under standing
    # approval it waits for a person.
    [proposed] = records(desk, run)
    # The note sets what the books did beside this booking.
    assert (proposed["status"], proposed["review_reasons"]) == ("proposed", [
        f"{bill_entry.UNPRECEDENTED} Its last bill, SD/26/0101, was a Purchase item-wise to Input CGST 9%, "
        "Input SGST 9%, Spares Purchase; this one is a Purchase to Spares Purchase."])


def depot(company):
    """Stores Depot's bill SD/26/0150 read item-wise: 50 bucket teeth at 200.00, split between two godowns."""
    entry = second_bill(company, 1)
    entry["document"].update(number="SD/26/0150", supplier_name="Stores Depot", supplier_gstin=DEPOT)
    entry["voucher"]["party"]["ledger_guid"] = "g-depot"
    entry["voucher"]["lines"] = entry["voucher"]["lines"][1:]
    entry["voucher"]["items"] = [{
        "item_guid": "s-tooth", "quantity": 50, "rate": 200.0, "amount": 10000.0, "ledger_guid": "g-spares",
        "godowns": [{"godown_guid": "gd-main", "quantity": 30, "amount": 6000.0},
                    {"godown_guid": "gd-site", "quantity": 20, "amount": 4000.0}],
        "evidence": "Bucket tooth 50 Nos 200.00 10,000.00"}]
    return entry


DEPOT_PDF = factory.text_pdf(invoice(supplier="Stores Depot", supplier_gstin=DEPOT, number="SD/26/0150",
                                     day="02-Sep-2026", taxable="10,000.00", tax="900.00", total="11,800.00"))


def settle_practice(desk, **values):
    """Practices the company's books settled, as a sync's probes record them."""
    from minkops_platform.accounts import memory
    company = desk["company"]
    for probe, value in values.items():
        memory.record(desk["db"], tenant_id=company["tenant_id"], client_id=company["client_id"],
                      company_id=company["id"], kind="practice", subject=probe, value=value,
                      evidence={"kind": "probe"}, status="confirmed")
    desk["db"].commit()


def test_an_item_wise_bill_carries_its_items_to_their_godowns_and_is_learnt_item_wise(desk):
    names = names_of(desk["company"])
    company, db = desk["company"]["guid"], desk["db"]
    factory.books(db, desk["company"], masters(desk["company"]) + STORES + STOCK, [PRIOR, ITEM_WISE])
    settle_practice(desk, receipt_notes={"in_use": False}, purchase_orders={"in_use": False})
    fake = by_file(**{"depot.pdf": [[("find_stock_item", {"company": "C1", "subjects": ["bucket tooth", "8431"]}),
                                     ("godowns", {"company": "C1"})],
                                    *proposing(names, depot(company))]})
    run = launch(desk, {"depot.pdf": DEPOT_PDF}, review_mode="only_exceptions")
    read(desk, fake, run)
    [session] = fake.created
    # Found by name and by HSN code, one item keeps one reference.
    by_name, by_hsn = answers(session, "find_stock_item")[0]["results"]
    assert by_name["items"] == by_hsn["items"] == [{"name": "Bucket tooth", "ref": "S1", "unit": "Nos",
                                                    "group": "Spares", "hsn": "84314990"}]
    assert answers(session, "godowns")[0] == {"godowns": [{"name": "Main Location", "ref": "G1", "under": None},
                                                          {"name": "Site Stores", "ref": "G2",
                                                           "under": "Main Location"}]}
    # Booked item-wise as this supplier's earlier bill was, it needs no review note; seen once, it waits for a person
    # even under standing approval.
    [bill] = records(desk, run)
    assert (bill["status"], bill["review_reasons"], bill["checks"]["precedents"]) == ("proposed", [], 1)
    decide(desk, bill, "approve")
    _, plan = companion(desk)
    assert plan["inventory"] == [{"item": "Bucket tooth", "unit": "Nos", "quantity": "50", "rate": "200", "side": "debit",
                                  "amount_cents": 1000000, "ledger": "Spares Purchase", "godowns": [
                                      {"godown": "Main Location", "quantity": "30", "amount_cents": 600000},
                                      {"godown": "Site Stores", "quantity": "20", "amount_cents": 400000}]}]
    assert [(ln["ledger"], ln["amount_cents"]) for ln in plan["lines"]] == [
        ("Stores Depot", 1180000), ("Spares Purchase", 1000000), ("Input CGST 9%", 90000), ("Input SGST 9%", 90000)]
    saved = record(desk, bill)
    assert (saved["status"], saved["current"]["inventory"][0]["godowns"][0]) == (
        "saved", {"godown": "Main Location", "quantity": "30", "amount_cents": -600000})
    # What the save teaches is an item-wise booking, apart from any booking of the same ledger without items.
    learnt = db.execute("SELECT value FROM memory_entries WHERE company_id=%s AND kind='booking'",
                        (desk["company"]["id"],)).fetchone()
    assert learnt["value"] == {"supplier": "Stores Depot", "voucher_type": "Purchase", "ledgers": ["Spares Purchase"],
                               "items": True}


def test_an_item_wise_bill_waits_on_open_practice_and_holds_where_orders_track_its_goods(desk):
    names = names_of(desk["company"])
    from minkops_platform import attention
    from minkops_platform.accounts import practice
    company, db = desk["company"]["guid"], desk["db"]
    version = factory.books(db, desk["company"], masters(desk["company"]) + STORES + STOCK, [PRIOR, ITEM_WISE])
    task = db.execute("INSERT INTO tasks(tenant_id,title) VALUES (%s,'Sync') RETURNING id",
                      (desk["tenant"]["id"],)).fetchone()
    # Two purchases settle neither whether Receipt Notes nor purchase orders are in use.
    practice.probe(db, desk["company"], version, {"task_id": task["id"]})
    db.commit()
    fake = by_file(**{"depot.pdf": proposing(names, depot(company))})
    run = launch(desk, {"depot.pdf": DEPOT_PDF})
    read(desk, fake, run)

    def answer(probe, choice):
        card = db.execute("""SELECT a.* FROM attention_items a JOIN practice_questions q ON q.attention_item_id=a.id
                             WHERE q.company_id=%s AND q.probe=%s""", (desk["company"]["id"], probe)).fetchone()
        attention.decide(db, desk["tenant"], desk["operator"], card["id"], choice)
        db.commit()

    [waiting] = records(desk, run)
    assert (waiting["hold_codes"], waiting["checks"]["practice"]) == (["practice_question"], "receipt_notes")
    answer("receipt_notes", "no")
    waiting = record(desk, waiting)
    assert (waiting["hold_codes"], waiting["checks"]["practice"]) == (["practice_question"], "purchase_orders")
    # Orders track its goods in Tally, so the bill is entered there; no later reading can recast it.
    answer("purchase_orders", "yes")
    held = record(desk, waiting)
    assert (held["status"], held["hold_codes"], held["checks"]["final"]) == ("held", ["unsupported_structure"], True)
    assert held["review_reasons"][0] == ("Purchase orders are in use in Rehearsal Infra Private Limited, so an item-wise "
                                         "purchase is matched to its order there. Enter this bill in Tally.")


def test_a_practice_the_books_settle_later_releases_the_bills_that_waited_on_it(desk):
    names = names_of(desk["company"])
    from minkops_platform.accounts import practice
    company, db = desk["company"]["guid"], desk["db"]
    factory.books(db, desk["company"], masters(desk["company"]) + STORES + STOCK, [PRIOR, ITEM_WISE])
    settle_practice(desk, receipt_notes={"in_use": False})
    fake = by_file(**{"depot.pdf": proposing(names, depot(company))})
    run = launch(desk, {"depot.pdf": DEPOT_PDF})
    read(desk, fake, run)
    [waiting] = records(desk, run)
    assert (waiting["hold_codes"], waiting["checks"]["practice"]) == (["practice_question"], "purchase_orders")
    # Ten more purchases, none of them against an order: the next sync settles the practice, and the bill goes on.
    later = [{**PRIOR, "GUID": f"v-later-{n}", "REFERENCE": f"SOS/26/1{n:02d}"} for n in range(10)]
    version = factory.books(db, desk["company"], masters(desk["company"]) + STORES + STOCK, [PRIOR, ITEM_WISE, *later])
    task = db.execute("INSERT INTO tasks(tenant_id,title) VALUES (%s,'Sync') RETURNING id",
                      (desk["tenant"]["id"],)).fetchone()
    practice.probe(db, desk["company"], version, {"task_id": task["id"]})
    db.commit()
    released = record(desk, waiting)
    assert (released["status"], released["hold_codes"], released["review_reasons"]) == ("proposed", [], [])


def einvoice_pdf(code):
    """A scanned bill page carrying a QR code: the image a session reads, with no text layer."""
    import qrcode
    page = Image.new("RGB", (1240, 1754), "white")
    page.paste(qrcode.make(code, box_size=4, border=4).get_image().convert("RGB"), (700, 1100))
    buffer = io.BytesIO()
    page.save(buffer, format="PDF", resolution=150)
    return buffer.getvalue()


def test_a_signed_e_invoice_pins_the_bill_it_registers(desk, monkeypatch):
    names = names_of(desk["company"])
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    from minkops_connectors import einvoice
    company = desk["company"]["guid"]
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(einvoice, "signers", lambda: (einvoice.Signer("Test IRP", key.public_key(), "CD" * 20,
                                                                      (None, None)),))

    def code(buyer=BUYER, total=188800, sign=True):
        encode = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()  # noqa: E731
        head = encode({"alg": "RS256", "kid": "CD" * 20, "typ": "JWT"})
        body = encode({"iss": "TEST", "data": json.dumps({
            "SellerGstin": SUNRISE, "BuyerGstin": buyer, "DocNo": "SOS/26/0412", "DocTyp": "INV", "DocDt": "01/09/2026",
            "TotInvVal": total, "ItemCnt": 1, "MainHsnCode": "9406", "Irn": "f" * 64, "IrnDt": "2026-09-01 11:00:00"})})
        # An altered code carries a signature made over other contents.
        signed_over = body if sign else encode({"iss": "TEST", "data": "{}"})
        signature = key.sign(f"{head}.{signed_over}".encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{head}.{body}." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

    misread = proposal(company, **{"document.total": 188000.0})
    fake = by_file(**{
        "registered.pdf": [*proposing(names, misread), reproposing(names, proposal(company))],
        "altered.pdf": proposing(names, proposal(company)),
        "elsewhere.pdf": proposing(names, proposal(company))})
    run = launch(desk, {"registered.pdf": einvoice_pdf(code()), "altered.pdf": einvoice_pdf(code(sign=False)),
                        "elsewhere.pdf": einvoice_pdf(code(buyer=gstin("37ZZZZZ9999Z1Z")))})
    read(desk, fake, run)
    session = next(s for s in fake.created if header(s)["file"] == "registered.pdf")
    # The session reads the bill against what the QR code registers.
    assert session.content[1]["text"].startswith("Page 1 carries a signed e-invoice QR code, verified as signed by "
                                                 "Test IRP. It registers {")
    assert answers(session, "propose")[0]["bills"][0] == {"bill": 1, "status": "rejected", "reason": (
        "The e-invoice QR code on page 1 says its total is 188800.00. Read the bill against it.")}
    registered, altered, elsewhere = records(desk, run)
    assert (registered["status"], registered["facts"]["einvoice"]) == (
        "proposed", {"status": "verified", "signer": "Test IRP", "irn": "f" * 64, "page": 1})
    # A code its signer's key does not verify holds at once: no later reading could clear it.
    assert (altered["status"], altered["hold_codes"], altered["checks"]["final"]) == (
        "held", ["source_values_conflict"], True)
    assert altered["review_reasons"][0].startswith("The e-invoice QR code on page 1 fails Test IRP's signature")
    assert (elsewhere["status"], elsewhere["hold_codes"]) == ("held", ["company_unresolved"])


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
    names = names_of(desk["company"])
    from minkops_platform.accounts import memory
    company, db = desk["company"]["guid"], desk["db"]

    def bill(number, **config):
        name = f"{number.replace('/', '-')}.pdf"
        fake = by_file(**{name: proposing(names, repairs(company, number))})
        run = launch(desk, {name: repairs_pdf(number)}, **config)
        read(desk, fake, run)
        return records(desk, run)[0]

    # A first booking for the supplier waits for a person; their approval and Tally's readback teach it.
    first = bill("SOS/26/0501")
    assert first["review_reasons"] == [
        f"{bill_entry.UNPRECEDENTED} Its last bill, SOS/26/0007, was a Purchase to Input CGST 9%, Input SGST 9%, "
        "Office Cabins; this one is a Purchase to Repairs and Maintenance."]
    decide(desk, first, "approve")
    companion(desk)
    learnt = db.execute("SELECT * FROM memory_entries WHERE company_id=%s AND kind='booking'",
                        (desk["company"]["id"],)).fetchone()
    # A booking is the treatment: the voucher type and expense ledgers, not the taxes the bill printed.
    assert (learnt["guids"][0], learnt["status"], learnt["uses"]) == ("g-sunrise", "confirmed", 1)
    assert learnt["value"] == {"supplier": "Sunrise Office Systems", "voucher_type": "Purchase",
                               "ledgers": ["Repairs and Maintenance"]}
    # One approval confirms the booking, so the next such bill needs no review note; but a booking seen once may be
    # a one-off, so standing approval leaves it for a person until it is seen twice.
    second = bill("SOS/26/0502", review_mode="only_exceptions")
    assert (second["status"], second["review_reasons"], second["checks"]["precedents"]) == ("proposed", [], 1)
    decide(desk, second, "approve")
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
    names = names_of(desk["company"])
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
    # Memory is asked about the supplier by the reference find_ledger gave it.
    fake = by_file(**{"stamped.pdf": [
        [("practice", {"company": "C1"}), ("rules", {}),
         ("find_ledger", {"company": "C1", "subjects": ["Sunrise Office Systems"]})],
        [("memory", {"company": "C1", "subjects": ["L1"]})],
        *proposing(names, unknown), reproposing(names, stamped)]})
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


@pytest.mark.gst
def test_a_taxed_bill_waits_while_its_company_has_not_said_which_gst_ledgers_it_uses_and_the_answer_releases_it(desk):
    """Books with GST duty ledgers and older ledgers named for the tax leave the choice to the client, once."""
    from minkops_platform import attention
    from minkops_platform.accounts import mirror, practice
    names, company, db = names_of(desk["company"]), desk["company"]["guid"], desk["db"]
    older = {"type": "LEDGER", "data": {"@_NAME": "Old Input CGST 9%", "GUID": "g-old-cgst", "PARENT": "Duties & Taxes",
                                       "ALTERID": "1"}}
    factory.books(db, desk["company"], [*gst_masters(desk["company"]), older], [PRIOR])
    task = db.execute("INSERT INTO tasks(tenant_id,title) VALUES (%s,'Sync') RETURNING id",
                      (desk["tenant"]["id"],)).fetchone()
    practice.probe(db, desk["company"], mirror.latest(db, desk["company"]["id"]), {"task_id": task["id"]})
    db.commit()
    fake = by_file(**{"sunrise.pdf": proposing(names, proposal(company))})
    run = launch(desk, {"sunrise.pdf": B01})
    read(desk, fake, run)
    [waiting] = records(desk, run)
    assert (waiting["status"], waiting["hold_codes"], waiting["checks"]["practice"]) == (
        "held", ["practice_question"], "gst_ledgers")
    card = db.execute("""SELECT a.* FROM attention_items a JOIN practice_questions q ON q.attention_item_id=a.id
                         WHERE q.company_id=%s AND q.probe='gst_ledgers'""", (desk["company"]["id"],)).fetchone()
    assert [option["action"] for option in practice.question(card["target"])["options"]] == ["gst_duty", "history"]
    assert attention.decide(db, desk["tenant"], desk["operator"], card["id"], "gst_duty")["status"] == "answered"
    db.commit()
    # The bill posts to the duty ledgers, as the answer says new bills do: it is released.
    assert (record(desk, waiting)["status"], record(desk, waiting)["hold_codes"]) == ("proposed", [])


def test_standing_approval_writes_only_bills_booked_as_before_and_stop_holds_the_rest(desk):
    names = names_of(desk["company"])
    company = desk["company"]["guid"]
    # Two earlier bills booked to cabins make a practice; one booked to repairs is a first.
    again = {**PRIOR, "GUID": "v-prior-2", "MASTERID": "6", "ALTERID": "4", "DATE": "20260801", "REFERENCE": "SOS/26/0008"}
    factory.books(desk["db"], desk["company"], masters(desk["company"]), [PRIOR, again])
    desk["db"].commit()
    first_time = second_bill(company, 1)
    first_time["voucher"]["lines"][0]["ledger_guid"] = "g-repairs"
    fake = by_file(**{"usual.pdf": proposing(names, proposal(company)),
                      "first-time.pdf": proposing(names, first_time)})
    run = launch(desk, {"usual.pdf": B01, "first-time.pdf": SECOND}, review_mode="only_exceptions")
    read(desk, fake, run)
    usual, unprecedented = records(desk, run)
    assert (usual["status"], usual["checks"]["precedents"]) == ("writing", 2)
    assert (unprecedented["status"], unprecedented["review_reasons"]) == ("proposed", [
        f"{bill_entry.UNPRECEDENTED} Its last bill, SOS/26/0008, was a Purchase to Input CGST 9%, Input SGST 9%, "
        "Office Cabins; this one is a Purchase to Repairs and Maintenance."])
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
