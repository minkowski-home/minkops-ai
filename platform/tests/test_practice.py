"""Practice probes settle what the mirror proves and ask once about the rest."""

import os

import pytest

from minkops_platform.accounts import memory, mirror, practice

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")


@pytest.fixture
def books():
    import factory
    with factory.connect() as db:
        tenant = factory.tenant(db)
        owner = factory.user(db, tenant, role="admin")
        device = factory.device(db, tenant, owner)
        client = factory.client(db, tenant)
        company = factory.company(db, tenant, device, client)
        task = db.execute("INSERT INTO tasks(tenant_id,title) VALUES (%s,'Sync') RETURNING id", (tenant["id"],)).fetchone()
        yield {"db": db, "company": company, "job": {"task_id": task["id"]}, "owner": owner}
        db.rollback()


def masters(*extra):
    groups = [("Sundry Creditors", "Current Liabilities"), ("Bank Accounts", "Current Assets")]
    rows = [{"type": "GROUP", "data": {"@_NAME": name, "GUID": f"grp-{i}", "PARENT": parent}}
            for i, (name, parent) in enumerate(groups)]
    rows += [{"type": "VOUCHERTYPE", "data": {"@_NAME": name, "@_RESERVEDNAME": name, "GUID": f"vt-{name}",
                                              "PARENT": name, "ISACTIVE": "Yes"}}
             for name in ("Purchase", "Payment", "Receipt Note")]
    rows += [{"type": "LEDGER", "data": {"@_NAME": "Bank", "GUID": "l-bank", "PARENT": "Bank Accounts"}}]
    return rows + list(extra)


def purchase(n, *, narration="", reference=""):
    return {"GUID": f"p-{n}", "ALTERID": str(n), "DATE": "20260901", "VOUCHERTYPENAME": "Purchase",
            "NARRATION": narration, "REFERENCE": reference, "PARTYLEDGERNAME": "Supplier",
            "ALLLEDGERENTRIES.LIST": [{"LEDGERNAME": "Supplier", "AMOUNT": "100"}, {"LEDGERNAME": "Purchases", "AMOUNT": "-100"}]}


def payment(n, party):
    return {"GUID": f"y-{n}", "ALTERID": str(100 + n), "DATE": "20260902", "VOUCHERTYPENAME": "Payment",
            "ALLLEDGERENTRIES.LIST": [{"LEDGERNAME": "Bank", "AMOUNT": "500"}, {"LEDGERNAME": party, "AMOUNT": "-500"}]}


def publish(db, company, records, vouchers):
    version = mirror.begin(db, company, kind="full", reason="test", markers={},
                           coverage={"from": "2026-04-01", "to": "2027-03-31"})
    mirror.upsert_masters(db, version, records)
    mirror.upsert_vouchers(db, version, vouchers)
    return mirror.publish(db, version)


def found(books, records, vouchers):
    version = publish(books["db"], books["company"], records, vouchers)
    return {f.probe: f for f in practice.findings(books["db"], books["company"], version["version"])}, version


def test_settled_practices_are_read_from_the_books(books):
    suppliers = [{"type": "LEDGER", "data": {"@_NAME": f"Payee {n}", "GUID": f"l-{n}", "PARENT": "Sundry Creditors",
                                             "ISBILLWISEON": "Yes" if n < 3 else "No"}} for n in range(12)]
    vouchers = [purchase(n, narration=f"DMR No. {4000 + n} goods received", reference=f"INV-{n}") for n in range(12)]
    vouchers += [payment(n, f"Payee {n}") for n in range(12)]
    findings, _ = found(books, masters(*suppliers), vouchers)
    assert findings["receipt_register"].value == {"recorded_in": "narration"}
    assert findings["invoice_number_field"].value == {"fields": ["REFERENCE"]}
    assert findings["bank_payments"].value == {"style": "party_ledgers"}
    assert findings["billwise"].value == {"in_use": True, "share": 0.25}
    assert findings["receipt_notes"].value == {"in_use": False}


def test_one_ledger_with_cost_centres_is_recognised(books):
    wages = {"type": "LEDGER", "data": {"@_NAME": "Site Wages", "GUID": "l-wages", "PARENT": "Indirect Expenses"}}
    vouchers = [{**payment(n, "Site Wages"), "ALLLEDGERENTRIES.LIST": [
        {"LEDGERNAME": "Bank", "AMOUNT": "500"},
        {"LEDGERNAME": "Site Wages", "AMOUNT": "-500", "CATEGORYALLOCATIONS.LIST": {
            "CATEGORY": "Sites", "COSTCENTREALLOCATIONS.LIST": {"NAME": f"Site {n % 3}", "AMOUNT": "-500"}}}]}
        for n in range(12)]
    findings, _ = found(books, masters(wages), vouchers)
    assert findings["bank_payments"].value == {"style": "one_ledger_cost_centres", "ledger_guid": "l-wages",
                                               "ledger": "Site Wages"}
    assert findings["bank_payments"].guids == ("l-wages",)


def test_too_little_history_becomes_one_question_per_company(books):
    db = books["db"]
    _, version = found(books, masters(), [purchase(1)])
    practice.probe(db, books["company"], version, books["job"])
    practice.probe(db, books["company"], version, books["job"])
    questions = db.execute("SELECT probe,status FROM practice_questions WHERE company_id=%s ORDER BY probe",
                           (books["company"]["id"],)).fetchall()
    assert {q["probe"] for q in questions} >= {"receipt_register", "invoice_number_field", "bank_payments"}
    assert len(questions) == len({q["probe"] for q in questions})  # No duplicate on a second sync.
    card = db.execute("SELECT * FROM attention_items WHERE tenant_id=%s AND kind='practice' LIMIT 1",
                      (books["company"]["tenant_id"],)).fetchone()
    assert card["label"] == "Practice question" and card["target"]["options"]


def test_a_settled_fact_is_a_confirmed_entry_and_a_persons_answer_is_never_overwritten(books):
    db, company = books["db"], books["company"]
    answered = memory.record(db, tenant_id=company["tenant_id"], client_id=company["client_id"],
                             company_id=company["id"], kind="practice", subject="receipt_notes",
                             value={"in_use": True}, evidence={"kind": "answer"}, status="confirmed",
                             actor_id=books["owner"]["id"])
    vouchers = [purchase(n, reference=f"INV-{n}") for n in range(12)]
    _, version = found(books, masters(), vouchers)
    practice.probe(db, company, version, books["job"])
    entry = memory.live(db, company["tenant_id"], company["client_id"], company_id=company["id"],
                        kind="practice", subject="receipt_notes")
    assert entry["id"] == answered["id"] and entry["value"] == {"in_use": True}
    assert entry["evidence"][-1]["kind"] == "probe"
    invoice = memory.live(db, company["tenant_id"], company["client_id"], company_id=company["id"],
                          kind="practice", subject="invoice_number_field")
    assert (invoice["status"], invoice["value"]) == ("confirmed", {"fields": ["REFERENCE"]})
