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
    # Ten suppliers, and two staff whose advances are paid from the bank too.
    suppliers = [{"type": "LEDGER", "data": {"@_NAME": f"Payee {n}", "GUID": f"l-{n}",
                                             "PARENT": "Sundry Creditors" if n < 10 else "Staff Advances",
                                             "ISBILLWISEON": "Yes" if n < 3 else "No"}} for n in range(12)]
    vouchers = [purchase(n, narration=f"DMR No. {4000 + n} goods received", reference=f"INV-{n}") for n in range(12)]
    vouchers += [payment(n, f"Payee {n}") for n in range(12)]
    findings, _ = found(books, masters(*suppliers), vouchers)
    assert findings["receipt_register"].value == {"recorded_in": "narration"}
    assert findings["invoice_number_field"].value == {"fields": ["REFERENCE"]}
    # Payees have ledgers of their own; a new one is offered under the groups theirs sit under, most used first.
    assert findings["bank_payments"].value == {"style": "party_ledgers", "groups": [
        {"group": "Sundry Creditors", "share": 0.83}, {"group": "Staff Advances", "share": 0.17}]}
    assert findings["billwise"].value == {"in_use": True, "share": 0.3}
    assert findings["receipt_notes"].value == findings["purchase_orders"].value == {"in_use": False}
    # One order in the books says the company tracks them.
    order = {"type": "VOUCHERTYPE", "data": {"@_NAME": "Purchase Order", "@_RESERVEDNAME": "Purchase Order",
                                             "GUID": "vt-po", "PARENT": "Purchase Order", "ISACTIVE": "Yes"}}
    findings, _ = found(books, masters(*suppliers, order), [*vouchers, {
        **purchase(99), "GUID": "po-1", "VOUCHERTYPENAME": "Purchase Order"}])
    assert findings["purchase_orders"].value == {"in_use": True}


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


def test_a_question_reaches_the_people_who_run_the_workflow_its_answer_changes(books):
    """Asked per company, a question changes one workflow's entries: it reaches admins, and the members who run that
    workflow. A member running only statements neither sees nor answers how bills are booked."""
    from minkops_platform import attention
    from minkops_platform.errors import ServiceError
    db, company = books["db"], books["company"]
    assert set(practice.SERVES) == set(practice.QUESTIONS)
    _, version = found(books, masters(), [purchase(1)])
    practice.probe(db, company, version, books["job"])
    tenant = {"id": company["tenant_id"]}

    def shown(workflows):
        return {item["target_probe"] for item in (
            {**row, "target_probe": db.execute("SELECT probe FROM practice_questions WHERE attention_item_id=%s",
                                               (row["id"],)).fetchone()["probe"]}
            for row in attention.listing(db, tenant["id"], workflows=workflows) if row["kind"] == "practice")}

    every = shown(None)
    assert {"receipt_register", "invoice_number_field", "bank_payments"} <= every
    assert shown(["statement-entry"]) == {"bank_payments"}
    assert shown(["bill-entry"]) == every - {"bank_payments"}
    assert shown([]) == set()
    assert attention.pending_count(db, tenant["id"], workflows=["statement-entry"]) == 1
    bills = db.execute("""SELECT a.id FROM attention_items a JOIN practice_questions q ON q.attention_item_id=a.id
                          WHERE q.company_id=%s AND q.probe='invoice_number_field'""", (company["id"],)).fetchone()
    with pytest.raises(ServiceError) as hidden:
        attention.decide(db, tenant, books["owner"], bills["id"], "NARRATION", workflows=["statement-entry"])
    assert hidden.value.kind == "not_found"


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


def test_books_that_settle_a_fact_differently_later_change_its_entry(books):
    db, company = books["db"], books["company"]

    def synced(bill_by_bill):
        """A sync of books where this many of twelve suppliers keep bill-by-bill balances."""
        suppliers = [{"type": "LEDGER", "data": {"@_NAME": f"Payee {n}", "GUID": f"l-{n}", "PARENT": "Sundry Creditors",
                                                 "ISBILLWISEON": "Yes" if n < bill_by_bill else "No"}}
                     for n in range(12)]
        _, version = found(books, masters(*suppliers), [purchase(n, reference=f"INV-{n}") for n in range(12)])
        practice.probe(db, company, version, books["job"])
        return memory.live(db, company["tenant_id"], company["client_id"], company_id=company["id"],
                           kind="practice", subject="billwise")

    first, later = synced(0), synced(3)
    assert (first["value"], later["value"]) == ({"in_use": False, "share": 0.0}, {"in_use": True, "share": 0.25})
    # The same entry, at its next version, still settled by the books rather than by a person.
    assert (later["id"], later["version"], later["status"], later["confirmed_by"]) == (
        first["id"], first["version"] + 1, "confirmed", None)


def test_an_answer_settles_the_practice_and_no_later_sync_asks_again(books):
    from minkops_platform import attention
    from minkops_platform.errors import ServiceError
    db, company = books["db"], books["company"]
    _, version = found(books, masters(), [purchase(1)])
    practice.probe(db, company, version, books["job"])
    card = db.execute("""SELECT a.* FROM attention_items a JOIN practice_questions q ON q.attention_item_id=a.id
                         WHERE q.company_id=%s AND q.probe='invoice_number_field'""", (company["id"],)).fetchone()
    tenant = {"id": company["tenant_id"]}
    assert practice.settled(db, company, "invoice_number_field") is None
    # The card offers its answers with their labels; only those settle it.
    assert practice.question(card["target"])["options"] == [
        {"action": "REFERENCE", "label": "In Supplier Invoice No. (reference)"},
        {"action": "NARRATION", "label": "In the narration"}]
    with pytest.raises(ServiceError, match="offered answers"):
        attention.decide(db, tenant, books["owner"], card["id"], "BOTH")
    assert attention.decide(db, tenant, books["owner"], card["id"], "NARRATION")["status"] == "answered"
    assert practice.settled(db, company, "invoice_number_field") == {"fields": ["NARRATION"]}
    assert db.execute("SELECT status FROM attention_items WHERE id=%s", (card["id"],)).fetchone()["status"] == "done"
    practice.probe(db, company, version, books["job"])
    assert db.execute("""SELECT count(*) AS n FROM practice_questions WHERE company_id=%s
                         AND probe='invoice_number_field' AND status='open'""", (company["id"],)).fetchone()["n"] == 0


def ledger(name, guid, parent="Duties & Taxes", **extra):
    return {"type": "LEDGER", "data": {"@_NAME": name, "GUID": guid, "PARENT": parent, **extra}}


DUTY = ledger("Input CGST 9% - UAT", "l-duty", TAXTYPE="GST", GSTDUTYHEAD="CGST", RATEOFTAXCALCULATION="9")
NAMED = ledger("QA18 Input CGST 9%", "l-named")
DISCOUNT = ledger("Trade Discount Received", "l-discount", parent="Indirect Incomes")
TAXES = ("Duties & Taxes", "Current Liabilities")


def posting(n, *ledgers):
    """A purchase posting to these ledgers besides the supplier's and the purchase ledger."""
    return {"GUID": f"p-{n}", "ALTERID": str(n), "DATE": "20260901", "VOUCHERTYPENAME": "Purchase",
            "PARTYLEDGERNAME": "Supplier", "ALLLEDGERENTRIES.LIST": [
                {"LEDGERNAME": "Supplier", "AMOUNT": "118"}, {"LEDGERNAME": "Purchases", "AMOUNT": "-100"},
                *({"LEDGERNAME": name, "AMOUNT": "-9"} for name in ledgers)]}


def with_taxes(*extra):
    return [{"type": "GROUP", "data": {"@_NAME": TAXES[0], "GUID": "grp-taxes", "PARENT": TAXES[1]}}, *masters(*extra)]


def test_where_a_company_posts_gst_is_read_from_its_books_and_asked_once_when_they_show_both(books):
    duty_only, _ = found(books, with_taxes(DUTY), [posting(1, "Input CGST 9% - UAT")])
    assert (duty_only["gst_ledgers"].value, duty_only["gst_ledgers"].question) == ({"use": "gst_duty"}, None)
    # No ledger is set up as a GST duty: the ledgers named for the tax are all there is.
    named_only, _ = found(books, with_taxes(NAMED), [posting(1, "QA18 Input CGST 9%")])
    assert named_only["gst_ledgers"].value == {"use": "history"}
    # Both kinds, and the books post to the named one: only the client can say which new bills use.
    both, _ = found(books, with_taxes(DUTY, NAMED), [posting(n, "QA18 Input CGST 9%") for n in range(12)])
    assert both["gst_ledgers"].value is None
    assert [option["value"] for option in both["gst_ledgers"].question["options"]] == ["gst_duty", "history"]
    assert both["gst_ledgers"].evidence == {"duty_ledgers": 1, "named_ledgers": 1, "purchases_to_duty": 0,
                                            "purchases_to_named": 12}
    # Both kinds, but every purchase of many uses the duty ledgers: the books settle it.
    settled, _ = found(books, with_taxes(DUTY, NAMED), [posting(n, "Input CGST 9% - UAT") for n in range(12)])
    assert settled["gst_ledgers"].value == {"use": "gst_duty"}
    # A company with no GST ledgers has nothing to settle.
    assert "gst_ledgers" not in found(books, masters(), [posting(1)])[0]


def test_how_a_company_books_a_printed_discount_is_read_from_its_books_and_asked_once_when_they_cannot_say(books):
    # No discount ledger: a purchase can only be booked net of its discount.
    net, _ = found(books, masters(), [posting(1)])
    assert net["discounts"].value == {"booked": "net"}
    used, _ = found(books, masters(DISCOUNT), [posting(1, "Trade Discount Received"), posting(2)])
    assert used["discounts"].value == {"booked": "separately", "ledger_guid": "l-discount",
                                       "ledger": "Trade Discount Received"}
    # A discount the client allows its customers is the sales side, and says nothing about purchases.
    allowed = ledger("Discount Allowed", "l-allowed", parent="Indirect Expenses")
    assert found(books, masters(allowed), [posting(1)])[0]["discounts"].value == {"booked": "net"}
    # A discount ledger the purchases never use: either is possible.
    unused, _ = found(books, masters(DISCOUNT), [posting(n) for n in range(12)])
    assert unused["discounts"].value is None
    assert [option["value"] for option in unused["discounts"].question["options"]] == ["net", "separately"]
