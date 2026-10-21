"""Statement entry on runs, end to end on PostgreSQL with the fake Agents API.

Sessions are scripted like a model would work: read the rows they were given,
call the real lookup tools, and propose. Everything after that is the real
path: proofs, checks, pairing, approvals, writes and receipts.
"""

import json
import os
import time
from datetime import date
from pathlib import Path

import pytest
from fake_agents import FakeAgents, Script

from minkops_platform import lanes, work
from minkops_platform.accounts import statement_entry, sync
from minkops_platform.runtime import openai_hosted
from minkops_platform.workflows import load_definition

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")
DEFINITION = load_definition(Path(__file__).resolve().parents[2] / "employees/accounts-desk/workflows/statement-entry")
ICICI = b"""Account Number,000405001234
Statement period,01/09/2026 to 30/09/2026
Date,Narration,Ref,Withdrawal,Deposit,Balance
01/09/2026,NEFT ACME STEEL UTR111222,UTR111222,1180.00,,98820.00
01/09/2026,BANK CHARGES,,118.00,,98702.00
02/09/2026,TRANSFER TO HDFC,TRF1,5000.00,,93702.00
15/09/2026,NEFT RETURN UTR111222,UTR111222R,,1180.00,94882.00
"""
HDFC = b"""Date,Description,Debit,Credit,Balance
02/09/2026,TRANSFER FROM ICICI,,5000.00,15000.00
16/09/2026,HDFC CHARGES,59.00,,14941.00
"""
ICICI_LAYOUT = {"header_row": 3, "columns": {
    "date": {"column": 1, "order": "dmy"}, "amount": {"mode": "debit_credit", "debit": 4, "credit": 5},
    "balance": {"column": 6}, "reference": {"column": 3}, "narration": {"columns": [2]}, "account": None,
    "routing_hint": None}, "row_order": "oldest_first", "rows": {},
    "details": [{"kind": "account_number", "row": 1, "column": 2}], "evidence": "Headings on row 3; balances chain."}
HDFC_LAYOUT = {**ICICI_LAYOUT, "header_row": 1, "details": [], "columns": {
    **ICICI_LAYOUT["columns"], "amount": {"mode": "debit_credit", "debit": 3, "credit": 4}, "balance": {"column": 5},
    "reference": None}}


def ledger(guid, name, parent, **extra):
    return {"type": "LEDGER", "data": {"@_NAME": name, "GUID": guid, "PARENT": parent, "ALTERID": "1", **extra}}


def vtype(guid, name):
    return {"type": "VOUCHERTYPE", "data": {"@_NAME": name, "@_RESERVEDNAME": name, "GUID": guid, "PARENT": name,
                                            "ALTERID": "1", "ISACTIVE": "Yes"}}


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(openai_hosted.time, "sleep", lambda seconds: None)


@pytest.fixture
def desk():
    """A client business with one authorised company on one PC, its books mirrored."""
    import factory
    with factory.connect() as db:
        tenant = factory.tenant(db)
        operator = factory.user(db, tenant, role="admin")
        client = factory.client(db, tenant)
        device = factory.device(db, tenant, operator)
        company = factory.company(db, tenant, device, client, name="Rehearsal Infra")
        factory.books(db, company, [
            {"type": "COMPANY", "data": {"@_NAME": company["name"], "GUID": company["guid"], "BOOKSFROM": "20260401"}},
            ledger("g-icici", "ICICI Current A/c", "Bank Accounts", BANKDETAILS="000405001234"),
            ledger("g-hdfc", "HDFC Current A/c", "Bank Accounts", BANKDETAILS="50200012345678"),
            ledger("g-acme", "Acme Steel", "Sundry Creditors"),
            ledger("g-charges", "Bank Charges", "Indirect Expenses"),
            vtype("g-payment", "Payment"), vtype("g-receipt", "Receipt"), vtype("g-contra", "Contra")])
        flow = {**factory.workflow(db, tenant, key="statement-entry"), "config_values": {"review_mode": "all_outputs"}}
        db.commit()
        yield {"db": db, "tenant": tenant, "operator": operator, "client": client, "device": device,
               "company": company, "workflow": flow}


def launch(desk, files, **config):
    import factory
    uploaded = factory.upload(desk["db"], desk["tenant"], desk["operator"], files)
    run = statement_entry.launch(desk["db"], tenant=desk["tenant"], user=desk["operator"], client=desk["client"],
                                 workflow=desk["workflow"], definition=DEFINITION,
                                 body={"file_ids": [f["id"] for f in uploaded], "config": config,
                                       "request_key": __import__("uuid").uuid4()})
    desk["db"].commit()
    return run


def items(desk, run):
    desk["db"].commit()
    return desk["db"].execute("SELECT * FROM run_items WHERE run_id=%s ORDER BY ordinal", (run["id"],)).fetchall()


def records(desk, run):
    desk["db"].commit()
    return desk["db"].execute("""SELECT r.* FROM run_records r JOIN run_items i ON i.id=r.item_id WHERE r.run_id=%s
                                 ORDER BY i.ordinal, r.position""", (run["id"],)).fetchall()


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


def host(desk, fake, **options):
    return lanes.Host(os.environ["TEST_DATABASE_URL"], client=fake, tenant_id=desk["tenant"]["id"],
                      **{"lanes": 2, "heartbeat_seconds": 0.2, "poll_seconds": 0.3, "close_seconds": 0.1, **options})


def rows_of(session):
    """The rows a chunk session was given, as the model reads them."""
    return [json.loads(line) for line in session.content[0]["text"].splitlines()[2:]]


def layouts(answers, session):
    """A layout session declares the reading that fits the sheet it was shown."""
    preview = json.loads(session.content[0]["text"])
    return [("propose_layout", {"layout": HDFC_LAYOUT if preview["file"].startswith("hdfc") else ICICI_LAYOUT})]


def booked(row, company):
    """How the scripted model books each row of the fixtures."""
    narration = row.get("narration", "")
    base = {"ref": row["ref"], "company_guid": company, "voucher_type_guid": "g-payment", "evidence": "Fixture."}
    bank = "g-hdfc" if "HDFC" in narration or "ICICI" in narration and "FROM" in narration else "g-icici"
    if "ACME" in narration:
        return {**base, "bank_ledger_guid": "g-icici", "counter_ledger_guid": "g-acme"}
    if "RETURN" in narration:
        return {**base, "bank_ledger_guid": "g-icici", "counter_ledger_guid": "g-acme", "voucher_type_guid": "g-receipt"}
    if "CHARGES" in narration:
        return {**base, "bank_ledger_guid": bank, "counter_ledger_guid": "g-charges"}
    raise AssertionError(narration)


def test_a_new_format_is_learned_once_and_its_rows_wait_for_the_pc_to_refresh(desk):
    fake = FakeAgents(script_for=lambda metadata, content: Script(layouts))
    run = launch(desk, {"icici-sep.csv": ICICI})
    assert [i["kind"] for i in items(desk, run)] == ["layout"]
    with host(desk, fake):
        until(lambda: [i["kind"] for i in items(desk, run)] == ["layout", "chunk"])
        until(lambda: items(desk, run)[0]["state"] == "done")
    layout, chunk = items(desk, run)
    # Rows are read through the proven layout, and wait until the PC's books are current.
    assert (chunk["state"], chunk["waiting_on"]) == ("waiting", sync.blocker(desk["device"]["id"]))
    assert chunk["source"]["details"] == {"account_number": "000405001234"}
    rows = records(desk, run)
    assert [(r["facts"]["date"], r["facts"]["amount_cents"], r["status"]) for r in rows] == [
        ("2026-09-01", -118000, "pending"), ("2026-09-01", -11800, "pending"), ("2026-09-02", -500000, "pending"),
        ("2026-09-15", 118000, "pending")]
    # The same bank format in a later run reads with no layout session at all.
    again = launch(desk, {"icici-oct.csv": ICICI.replace(b"/09/2026", b"/10/2026")})
    assert [i["kind"] for i in items(desk, again)] == ["chunk"]
    assert len(fake.created) == 1


def is_chunk(content):
    return "rows follow" in content[0]["text"]


def answer(session, name):
    """The last answer a scripted session received from one tool, parsed."""
    return json.loads(next(a["text"] for a in reversed(session.answers) if a["name"] == name))


def learned(desk, run, fake):
    """Run the layout sessions, then let the PC refresh so the rows can be routed."""
    with host(desk, fake):
        until(lambda: all(i["state"] in ("done", "waiting") for i in items(desk, run))
              and any(i["kind"] == "chunk" for i in items(desk, run)))
    refreshed(desk)


def test_each_row_is_checked_as_it_is_proposed_and_a_rejection_says_why(desk):
    company = desk["company"]["guid"]

    def first(answers, session):
        rows = rows_of(session)
        not_a_bank = {**booked(rows[0], company), "bank_ledger_guid": "g-acme"}
        unsure = {"ref": rows[1]["ref"], "exception": {"code": "classification_uncertain",
                                                       "detail": "Bank charges or interest?"}}
        return [("find_ledger", {"company": company, "subjects": ["XXXXXXXX1234", "acme steel"]}),
                ("find_ledger", {"subjects": ["000405001234"]}),
                ("propose", {"rows": [not_a_bank, unsure]})]

    def corrected(answers, session):
        return [("propose", {"rows": [booked(rows_of(session)[0], company)]})]

    fake = FakeAgents(script_for=lambda m, content: Script(first, corrected) if is_chunk(content) else Script(layouts))
    run = launch(desk, {"icici-sep.csv": ICICI})
    learned(desk, run, fake)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, run)))
    chunk = next(s for s in fake.created if is_chunk(s.content))
    lookups = [json.loads(a["text"])["results"] for a in chunk.answers if a["name"] == "find_ledger"]
    # A masked account number matches its bank ledger by the last digits; names match on every word.
    assert [[ledger["name"] for ledger in result["ledgers"]] for result in lookups[0]] == [["ICICI Current A/c"],
                                                                                           ["Acme Steel"]]
    # Without a company, every company in scope is searched and each match names its company.
    assert [(ledger["name"], ledger["company_guid"]) for ledger in lookups[1][0]["ledgers"]] == [
        ("ICICI Current A/c", company)]
    proposed = [json.loads(a["text"]) for a in chunk.answers if a["name"] == "propose"]
    assert proposed[0]["rejected"][0]["reason"] == "The bank ledger must belong to the discovered Bank Accounts group."
    assert proposed[0]["held"] == [rows_of(chunk)[1]["ref"]] and proposed[1]["accepted"] == [rows_of(chunk)[0]["ref"]]
    rows = records(desk, run)
    assert [(r["status"], r["hold_codes"]) for r in rows] == [
        ("proposed", []), ("held", ["classification_uncertain"]), ("held", ["statement_interpretation"]),
        ("held", ["statement_interpretation"])]
    assert rows[0]["proposal"]["resolved"]["data"]["counter_ledger"] == "Acme Steel" and rows[0]["checks"] == {
        "submissions": 2}
    assert rows[1]["review_reasons"] == ["Bank charges or interest?"]
    assert rows[2]["review_reasons"] == ["No ledger interpretation was returned for this transaction."]
    assert work.get_run(desk["db"], desk["tenant"]["id"], run["id"])["state"] == "review"


def transfers(answers, session):
    """Round one: ask which rows could be the other leg of each transfer."""
    refs = [row["ref"] for row in rows_of(session) if "TRANSFER" in row["narration"]]
    return [("find_transfer", {"refs": refs})] if refs else []


def routed(company):
    def propose(answers, session):
        legs = {result["ref"]: result["candidates"][0]["ref"] for result in answer(session, "find_transfer")["results"]
                if result["candidates"]} if any(a["name"] == "find_transfer" for a in session.answers) else {}
        entries = []
        for row in rows_of(session):
            if "TRANSFER" in row["narration"]:
                to_hdfc = "TO HDFC" in row["narration"]
                entries.append({"ref": row["ref"], "company_guid": company, "family": "contra",
                                "bank_ledger_guid": "g-icici" if to_hdfc else "g-hdfc",
                                "counter_ledger_guid": "g-hdfc" if to_hdfc else "g-icici",
                                "voucher_type_guid": "g-contra", "evidence": "Own transfer.",
                                **({"pair": legs[row["ref"]]} if row["ref"] in legs else {})})
            else:
                entries.append(booked(row, company))
        return [("propose", {"rows": entries})]
    return propose


def readback(plan, guid="tally-1"):
    """What the companion reads back from Tally after saving exactly this plan."""
    return {"guid": guid, "master_id": "71", "date": plan["header"]["date"].replace("-", ""),
            "voucher_type": plan["voucher_type"]["NAME"], "family": plan["family"],
            "reference": plan["header"]["reference"], "number": "", "narration": plan["header"]["narration"],
            "party_ledger": "", "tag": plan["remote_id"], "fingerprint": f"fp-{guid}", "allocations": [],
            "lines": [{"ledger": line["ledger"],
                       "amount_cents": line["amount_cents"] * (1 if line["side"] == "credit" else -1)}
                      for line in plan["lines"]]}


def companion(desk, outcome="saved"):
    """The PC claims its next job, fetches the stored plan, and reports a receipt."""
    from minkops_platform import desktop
    db = desk["db"]
    device = db.execute("SELECT * FROM desktop_devices WHERE id=%s", (desk["device"]["id"],)).fetchone()
    job = desktop.claim(db, device)
    if job is None or job["operation"] != "tally.write":
        db.rollback()
        return None
    plan = desktop.plan(db, device, job["id"], job["claim_token"], 5)
    receipt = ({"outcome": outcome, "current": readback(plan)} if outcome in ("saved", "duplicate")
               else {"outcome": "attention", "hold": outcome, "message": "Tally is not running."})
    desktop.finish(db, device, job["id"], {"claim_token": job["claim_token"], "result": receipt})
    db.commit()
    return plan


def decide(desk, record, action):
    from minkops_platform.accounts.statement_entry import HANDLER
    db = desk["db"]
    run = work.get_run(db, desk["tenant"]["id"], record["run_id"])
    receipt = work.decide(db, tenant_id=desk["tenant"]["id"], record_id=record["id"], version=record["version"],
                          actor_id=desk["operator"]["id"], action=action,
                          apply=lambda current: HANDLER.decide(db, run, current, action, {},
                                                               {"user": desk["operator"]}))
    db.commit()
    return receipt


def test_a_transfer_between_own_accounts_is_written_once_for_both_rows(desk):
    company = desk["company"]["guid"]
    fake = FakeAgents(script_for=lambda m, content: Script(transfers, routed(company)) if is_chunk(content)
                      else Script(layouts))
    run = launch(desk, {"icici-sep.csv": ICICI, "hdfc-sep.csv": HDFC})
    learned(desk, run, fake)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, run)))
    rows = {r["facts"]["narration"]: r for r in records(desk, run)}
    out, back = rows["TRANSFER TO HDFC"], rows["TRANSFER FROM ICICI"]
    assert out["proposal"]["transfer"] == {"role": "writes", "other": str(back["id"])}
    assert back["proposal"]["transfer"] == {"role": "covered", "by": str(out["id"])}
    # Write ready rows approves the one Contra that writes both legs, and every other row.
    db = desk["db"]
    approved = statement_entry.HANDLER.approve_ready(db, work.get_run(db, desk["tenant"]["id"], run["id"]),
                                                     desk["operator"]["id"])
    db.commit()
    assert approved == {"approved": 6}
    plans = []
    while plan := companion(desk):
        plans.append(plan)
    plan = next(p for p in plans if p["family"] == "contra")
    assert len(plans) == 5  # four rows of their own, and one Contra for the two transfer legs
    assert (plan["family"], plan["identity"]["rule"], len(plan["identity"]["legs"])) == ("contra", "transfer_pair", 2)
    assert [(line["ledger"], line["side"], line["amount_cents"]) for line in plan["lines"]] == [
        ("ICICI Current A/c", "credit", 500000), ("HDFC Current A/c", "debit", 500000)]
    rows = {r["facts"]["narration"]: r for r in records(desk, run)}
    assert (rows["TRANSFER TO HDFC"]["status"], rows["TRANSFER FROM ICICI"]["status"]) == ("saved", "duplicate")
    assert rows["TRANSFER TO HDFC"]["current"]["tag"] == plan["remote_id"]
    assert desk["db"].execute("""SELECT count(*) FILTER (WHERE plan->>'family'='contra') AS contra, count(*) AS n
                                 FROM native_writes WHERE run_id=%s""", (run["id"],)).fetchone() == {"contra": 1, "n": 5}


def test_an_approved_row_writes_once_and_an_interrupted_save_is_never_resent(desk):
    company = desk["company"]["guid"]
    fake = FakeAgents(script_for=lambda m, content: Script(transfers, routed(company)) if is_chunk(content)
                      else Script(layouts))
    run = launch(desk, {"icici-sep.csv": ICICI, "hdfc-sep.csv": HDFC})
    learned(desk, run, fake)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, run)))
    rows = {r["facts"]["narration"]: r for r in records(desk, run)}
    acme = rows["NEFT ACME STEEL UTR111222"]
    decide(desk, acme, "approve")
    # The same transaction in another run cannot be written while this write is pending.
    rerun = launch(desk, {"icici-copy.csv": ICICI})
    with host(desk, fake):
        until(lambda: any(i["kind"] == "chunk" for i in items(desk, rerun)))
    refreshed(desk)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, rerun)))
    copy = next(r for r in records(desk, rerun) if r["facts"]["narration"] == "NEFT ACME STEEL UTR111222")
    assert decide(desk, copy, "approve")["status"] == "held"
    assert work.get_record(desk["db"], desk["tenant"]["id"], copy["id"])["hold_codes"] == ["statement_save_waiting"]
    # The PC reports the save could not be confirmed: the row holds and nothing is re-sent on its own.
    companion(desk, outcome="not_running")
    held = work.get_record(desk["db"], desk["tenant"]["id"], acme["id"])
    assert (held["status"], held["hold_codes"]) == ("held", ["not_running"])
    assert companion(desk) is None
    # Retry save sends the same plan again; this time it saves and verifies.
    decide(desk, held, "retry_save")
    first, second = desk["db"].execute("SELECT plan FROM native_writes WHERE record_id=%s ORDER BY created_at",
                                       (acme["id"],)).fetchall()
    plan = companion(desk)
    assert plan["remote_id"] == first["plan"]["remote_id"] == second["plan"]["remote_id"]
    saved = work.get_record(desk["db"], desk["tenant"]["id"], acme["id"])
    assert (saved["status"], saved["current"]["guid"]) == ("saved", "tally-1")


def test_an_unsettled_date_order_waits_for_one_answer_then_reads_the_rows(desk):
    # Every date reads both ways, and both readings are in the past: only a person can say which.
    early = ICICI.replace(b"01/09/2026", b"01/02/2026").replace(b"02/09/2026", b"02/03/2026").replace(
        b"15/09/2026", b"03/04/2026")
    fake = FakeAgents(script_for=lambda m, content: Script(layouts))
    run = launch(desk, {"icici-sep.csv": early})
    with host(desk, fake):
        until(lambda: items(desk, run)[0]["state"] == "waiting")
    [layout] = items(desk, run)
    card = desk["db"].execute("SELECT * FROM attention_items WHERE tenant_id=%s AND kind='layout'",
                              (desk["tenant"]["id"],)).fetchone()
    assert (card["label"], card["target"]["actions"]) == ("Choose date order", ["dmy", "mdy"])
    assert layout["waiting_on"] == {"kind": "layout", "ref": card["target"]["profile_id"]}
    from minkops_platform.accounts import statement_layouts
    statement_layouts.decide(desk["db"], desk["tenant"], desk["operator"], card, "mdy")
    desk["db"].commit()
    with host(desk, fake):
        until(lambda: [i["kind"] for i in items(desk, run)] == ["layout", "chunk"])
    # Read month-first, as answered; no second session was needed.
    assert [r["facts"]["date"] for r in records(desk, run)] == ["2026-01-02", "2026-01-02", "2026-02-03", "2026-03-04"]
    assert len(fake.created) == 1


def test_balances_that_refute_a_reading_are_explained_and_never_kept(desk):
    swapped = {**ICICI_LAYOUT, "columns": {**ICICI_LAYOUT["columns"], "amount": {
        "mode": "debit_credit", "debit": 5, "credit": 4}}}
    fake = FakeAgents(Script([("propose_layout", {"layout": swapped})], [("propose_layout", {"layout": swapped})],
                             [("propose_layout", {"layout": swapped})], [("propose_layout", {"layout": swapped})]))
    run = launch(desk, {"icici-sep.csv": ICICI})
    with host(desk, fake):
        until(lambda: items(desk, run)[0]["state"] == "done")
    [session] = fake.sessions or fake.created
    texts = [a["text"] for a in session.answers]
    # The first row chains from its own implied opening; the second shows the swapped columns.
    assert texts[0] == ("The balances refute this reading. Row 5: The running balance cannot be verified against the "
                        "preceding balance and transaction.")
    assert texts[3] == "No more attempts: this sheet will be held for review."
    [sheet] = records(desk, run)
    assert (sheet["kind"], sheet["status"], sheet["hold_codes"]) == ("statement_sheet", "held",
                                                                     ["statement_layout_unknown"])
    assert desk["db"].execute("SELECT count(*) AS n FROM client_profiles WHERE tenant_id=%s",
                              (desk["tenant"]["id"],)).fetchone()["n"] == 0


def test_a_transaction_in_overlapping_statements_is_written_once(desk):
    company = desk["company"]["guid"]
    fake = FakeAgents(script_for=lambda m, content: Script(transfers, routed(company)) if is_chunk(content)
                      else Script(layouts))
    run = launch(desk, {"icici-sep.csv": ICICI, "icici-sep-again.csv": ICICI})
    learned(desk, run, fake)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, run)))
    acme = [r for r in records(desk, run) if r["facts"]["narration"] == "NEFT ACME STEEL UTR111222"]
    first, repeat = sorted(acme, key=lambda r: r["facts"]["file"])
    assert repeat["proposal"]["repeat_of"] == str(first["id"]) and repeat["review_reasons"]
    decide(desk, repeat, "approve")
    companion(desk)
    assert [work.get_record(desk["db"], desk["tenant"]["id"], r["id"])["status"] for r in (first, repeat)] == [
        "saved", "duplicate"]
    assert desk["db"].execute("SELECT count(*) AS n FROM native_writes WHERE run_id=%s",
                              (run["id"],)).fetchone()["n"] == 1


def test_overlapping_statements_that_route_one_transaction_differently_both_hold(desk):
    company = desk["company"]["guid"]

    def disagree(answers, session):
        entries = []
        for row in rows_of(session):
            entry = booked(row, company) if "TRANSFER" not in row["narration"] else None
            if entry and "again" in session.content[0]["text"].split("\n")[0] and "ACME" in row["narration"]:
                entry = {**entry, "counter_ledger_guid": "g-charges"}
            if entry:
                entries.append(entry)
        return [("propose", {"rows": entries})]

    fake = FakeAgents(script_for=lambda m, content: Script(disagree) if is_chunk(content) else Script(layouts))
    run = launch(desk, {"icici-sep.csv": ICICI, "icici-sep-again.csv": ICICI})
    learned(desk, run, fake)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, run)))
    acme = [r for r in records(desk, run) if r["facts"]["narration"] == "NEFT ACME STEEL UTR111222"]
    assert [(r["status"], r["hold_codes"]) for r in acme] == [("held", ["statement_conflict"])] * 2


def test_a_gap_from_the_previous_statement_raises_one_attention_item(desk):
    company = desk["company"]["guid"]

    def october_unsure(answers, session):
        """Route every row, but hold October's bank charges for review."""
        [(name, arguments)] = routed(company)(answers, session)
        given = {row["ref"]: row for row in rows_of(session)}
        rows = [{"ref": entry["ref"], "exception": {"code": "classification_uncertain", "detail": "Charges?"}}
                if "CHARGES" in given[entry["ref"]]["narration"] and given[entry["ref"]]["date"].startswith("2026-10")
                else entry for entry in arguments["rows"]]
        return [(name, {"rows": rows})]

    fake = FakeAgents(script_for=lambda m, content: Script(transfers, october_unsure) if is_chunk(content)
                      else Script(layouts))
    september = launch(desk, {"icici-sep.csv": ICICI})
    learned(desk, september, fake)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, september)))
    # October opens at 90,000.00, but September closed at 94,882.00.
    october = ICICI.replace(b"/09/2026", b"/10/2026").replace(b"98820.00", b"88820.00").replace(
        b"98702.00", b"88702.00").replace(b"93702.00", b"83702.00").replace(b"94882.00", b"84882.00")
    run = launch(desk, {"icici-oct.csv": october})
    refreshed(desk)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, run)))
    gaps = desk["db"].execute("SELECT * FROM attention_items WHERE tenant_id=%s AND label='Transactions missing'",
                              (desk["tenant"]["id"],)).fetchall()
    assert len(gaps) == 1 and "closed at 94882.00 on 2026-09-15" in gaps[0]["target"]["reason"]
    assert "opens at 90000.00 on 2026-10-01" in gaps[0]["target"]["reason"]
    assert [r["status"] for r in records(desk, run)] == ["proposed", "held", "proposed", "proposed"]
    # A row held for its ledger still chains by its balance: the span runs from the first row to the last.
    spans = desk["db"].execute("SELECT date_from, date_to FROM statement_spans WHERE run_id=%s", (run["id"],)).fetchall()
    assert [(s["date_from"].isoformat(), s["date_to"].isoformat()) for s in spans] == [("2026-10-01", "2026-10-15")]


def test_a_returned_payment_is_found_in_the_run_and_in_tally(desk):
    import factory
    company = desk["company"]
    factory.books(desk["db"], company, [], [{
        "GUID": "v-old", "MASTERID": "9", "ALTERID": "2", "DATE": "20260820", "VOUCHERTYPENAME": "Payment",
        "VOUCHERNUMBER": "12", "REFERENCE": "UTR999888", "NARRATION": "NEFT to Acme Steel UTR999888",
        "ALLLEDGERENTRIES.LIST": [{"LEDGERNAME": "Acme Steel", "AMOUNT": "-2500.00"},
                                  {"LEDGERNAME": "ICICI Current A/c", "AMOUNT": "2500.00"}]}])
    desk["db"].commit()

    def lookup(answers, session):
        return [("pair_return", {"utrs": ["UTR111222", "UTR999888"]})]

    fake = FakeAgents(script_for=lambda m, content: Script(lookup) if is_chunk(content) else Script(layouts))
    run = launch(desk, {"icici-sep.csv": ICICI})
    learned(desk, run, fake)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, run)))
    chunk = next(s for s in fake.created if is_chunk(s.content))
    in_run, in_tally = answer(chunk, "pair_return")["results"]
    assert [r["narration"] for r in in_run["rows"]] == ["NEFT ACME STEEL UTR111222", "NEFT RETURN UTR111222"]
    assert in_tally["tally"] == [{"company": "Rehearsal Infra", "date": "2026-08-20", "type": "Payment", "number": "12",
                                  "reference": "UTR999888", "narration": "NEFT to Acme Steel UTR999888",
                                  "entries": [{"ledger": "Acme Steel", "debit": "2500.00"},
                                              {"ledger": "ICICI Current A/c", "credit": "2500.00"}]}]


def test_standing_approval_writes_clean_rows_and_leaves_exceptions_for_review(desk):
    company = desk["company"]["guid"]
    fake = FakeAgents(script_for=lambda m, content: Script(transfers, routed(company)) if is_chunk(content)
                      else Script(layouts))
    run = launch(desk, {"icici-sep.csv": ICICI}, review_mode="only_exceptions", branch_mapping_file_id=None)
    learned(desk, run, fake)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, run)))
    by_status = {}
    for row in records(desk, run):
        by_status.setdefault(row["status"], []).append(row["facts"]["narration"])
    # One write at a time per PC: the first clean row is being written, the others wait their turn.
    assert sorted(by_status["writing"]) == ["BANK CHARGES", "NEFT ACME STEEL UTR111222", "NEFT RETURN UTR111222",
                                            "TRANSFER TO HDFC"]
    while companion(desk):
        pass
    assert {r["status"] for r in records(desk, run)} == {"saved"}


def test_stopping_holds_unsaved_rows_and_withdraws_writes_no_pc_has_started(desk):
    from minkops_platform.run_controls import task_control
    company = desk["company"]["guid"]
    fake = FakeAgents(script_for=lambda m, content: Script(transfers, routed(company)) if is_chunk(content)
                      else Script(layouts))
    run = launch(desk, {"icici-sep.csv": ICICI})
    learned(desk, run, fake)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, run)))
    rows = {r["facts"]["narration"]: r for r in records(desk, run)}
    decide(desk, rows["BANK CHARGES"], "approve")
    task_control(desk["db"], desk["tenant"]["id"], desk["operator"], run["task_id"], "stop")
    desk["db"].commit()
    assert {r["status"] for r in records(desk, run)} == {"held"}
    assert desk["db"].execute("SELECT outcome FROM native_writes WHERE run_id=%s", (run["id"],)).fetchone()["outcome"] \
        == "cancelled"
    assert companion(desk) is None


def test_a_rechecked_row_gets_a_fresh_proposal_in_a_new_attempt_of_its_chunk(desk):
    company = desk["company"]["guid"]
    attempts = []

    def once_unsure(answers, session):
        rows, first = rows_of(session), not attempts
        attempts.append(len(rows))
        return [("propose", {"rows": [
            {"ref": row["ref"], "exception": {"code": "ledger_unresolved", "detail": "Which supplier?"}}
            if first and "ACME" in row["narration"] else booked(row, company)
            for row in rows if "TRANSFER" not in row["narration"]]})]

    fake = FakeAgents(script_for=lambda m, content: Script(once_unsure) if is_chunk(content) else Script(layouts))
    run = launch(desk, {"icici-sep.csv": ICICI})
    learned(desk, run, fake)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, run)))
    acme = next(r for r in records(desk, run) if "ACME" in r["facts"]["narration"])
    assert acme["hold_codes"] == ["ledger_unresolved"]
    decide(desk, acme, "retry")
    with host(desk, fake):
        until(lambda: work.get_record(desk["db"], desk["tenant"]["id"], acme["id"])["status"] == "proposed")
    # Only the rechecked row went to the new session; the others kept their proposals.
    assert attempts == [4, 1]


def test_a_mapping_file_is_consulted_through_its_tool_and_never_read_as_transactions(desk):
    import factory
    branched = (b"Account Number,000405001234\nStatement period,Sep 2026\nDate,Narration,Ref,Withdrawal,Deposit,Balance,"
                b"Branch\n01/09/2026,NEFT ACME STEEL UTR1,UTR1,1180.00,,98820.00,DBM Plant\n"
                b"15/09/2026,BANK CHARGES,,118.00,,98702.00,Head Office\n")
    layout = {**ICICI_LAYOUT, "columns": {**ICICI_LAYOUT["columns"],
                                          "routing_hint": {"column": 7, "label": "Branch"}}}
    [mapping] = factory.upload(desk["db"], desk["tenant"], desk["operator"], {
        "branches.csv": b"Branch,Meaning\nDBM Plant,Site expenses of the DBM plant\nHead Office,Administration\n"})

    def consult(answers, session):
        return [("mapping", {"labels": [row["hint"] for row in rows_of(session)]})]

    fake = FakeAgents(script_for=lambda m, content: Script(consult) if is_chunk(content)
                      else Script([("propose_layout", {"layout": layout})]))
    run = launch(desk, {"icici-branches.csv": branched}, branch_mapping_file_id=str(mapping["id"]))
    assert [i["kind"] for i in items(desk, run)] == ["layout"]  # the mapping is not a statement
    learned(desk, run, fake)
    with host(desk, fake):
        until(lambda: all(i["state"] == "done" for i in items(desk, run)))
    chunk = next(s for s in fake.created if is_chunk(s.content))
    assert json.loads(chunk.content[0]["text"].splitlines()[0])["routing_hint_column"] == "Branch"
    [plant, office] = answer(chunk, "mapping")["results"]
    assert plant["sheets"] == [{"sheet": "", "header": ["Branch", "Meaning"],
                                "rows": [["DBM Plant", "Site expenses of the DBM plant"]]}]
    assert office["sheets"][0]["rows"] == [["Head Office", "Administration"]]


def test_a_saved_layout_a_new_statement_refutes_is_retired_and_learned_again(desk):
    fake = FakeAgents(script_for=lambda m, content: Script(layouts, layouts, layouts, layouts))
    first = launch(desk, {"icici-sep.csv": ICICI})
    with host(desk, fake):
        until(lambda: items(desk, first)[0]["state"] == "done")
    broken = ICICI.replace(b"98702.00", b"98700.00")  # same bank export, but its balances no longer chain
    run = launch(desk, {"icici-oct.csv": broken})
    [layout] = items(desk, run)
    assert (layout["kind"], layout["source"]["changed"]) == ("layout", True)
    with host(desk, fake):
        until(lambda: items(desk, run)[0]["state"] == "done")
    [sheet] = records(desk, run)
    assert (sheet["status"], sheet["hold_codes"]) == ("held", ["statement_layout_changed"])
    statuses = desk["db"].execute("SELECT status FROM client_profiles WHERE tenant_id=%s ORDER BY version",
                                  (desk["tenant"]["id"],)).fetchall()
    assert [s["status"] for s in statuses] == ["invalidated"]


def test_a_refutation_names_the_broken_balance_before_the_summary_it_upsets(desk):
    from minkops_platform.accounts import statement_layouts
    controlled = ICICI.replace(b"98702.00", b"98701.00") + b"Closing Balance,,,,,94882.00\n"
    [file] = __import__("factory").upload(desk["db"], desk["tenant"], desk["operator"], {"icici.csv": controlled})
    [entry] = statement_layouts.sheets([file])
    layout = {**ICICI_LAYOUT, "rows": {"closing": [{"column": 1, "starts_with": "Closing Balance"}]}}
    outcome = statement_layouts.prove(desk["db"], desk["tenant"]["id"], entry, layout, today=date(2026, 10, 21),
                                      actor=desk["operator"]["id"], provenance={})
    # Row 5's balance is one rupee off, which also upsets the next row and the closing balance.
    assert outcome == {"status": "refuted", "reason": "Row 5: The running balance cannot be verified against the "
                                                      "preceding balance and transaction."}
