"""The versioned Tally mirror: a run pins a version and sees exactly that version."""

import os

import pytest

from minkops_platform.accounts import mirror

DB = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")
GSTIN = "37AAXCM4321K1ZX"


def ledger(guid, name, *, alter=1, parent="Sundry Creditors", **extra):
    return {"type": "LEDGER", "data": {"@_NAME": name, "GUID": guid, "PARENT": parent, "ALTERID": f" {alter}",
                                       "ISBILLWISEON": "No", "EMPTY": "   ", "NESTED.LIST": "  ", **extra}}


def voucher(guid, date, *, alter=1, kind="Purchase", party="Supplier", amount="-1180.00", **extra):
    return {"GUID": guid, "MASTERID": " 5", "ALTERID": f" {alter}", "DATE": date, "VOUCHERTYPENAME": kind,
            "VOUCHERNUMBER": "7", "REFERENCE": "INV-1", "PARTYLEDGERNAME": party, "NARRATION": "Bill INV-1",
            "ALLLEDGERENTRIES.LIST": [{"LEDGERNAME": party, "AMOUNT": amount.lstrip("-"),
                                       "BILLALLOCATIONS.LIST": {"NAME": "INV-1", "BILLTYPE": "New Ref",
                                                                "AMOUNT": amount.lstrip("-")}},
                                      {"LEDGERNAME": "Purchases", "AMOUNT": amount}], **extra}


class TestNativeRows:
    def test_compaction_drops_only_empty_native_fields(self):
        assert mirror.compact({"A": "", "B": "  ", "C": "No", "D": {"E": " "}, "F": [{"G": ""}, "x"], "H": "0"}) == \
            {"C": "No", "F": ["x"], "H": "0"}

    def test_a_ledger_row_lifts_search_fields_without_losing_its_record(self):
        row = mirror.master_row(ledger("g-1", "Acme  Cement", alter=12, PARTYGSTIN=GSTIN,
                                       **{"LANGUAGENAME.LIST": {"NAME.LIST": {"NAME": ["Acme  Cement", "ACME"]}}}))
        assert (row["guid"], row["name_key"], row["alter_id"], row["gstin"], row["aliases"]) == \
            ("g-1", "acme cement", 12, GSTIN, ["ACME"])
        assert "EMPTY" not in row["data"] and row["data"]["ISBILLWISEON"] == "No"

    def test_bank_and_stock_details_become_searchable(self):
        bank = mirror.master_row(ledger("g-2", "ICICI Current", parent="Bank Accounts",
                                        BANKDETAILS="A/c 9999 0500 1234", IFSCODE="ICIC0009999"))
        assert (bank["bank_account"], bank["ifsc"]) == ("999905001234", "ICIC0009999")
        item = mirror.master_row({"type": "STOCKITEM", "data": {"@_NAME": "Cement OPC 53", "GUID": "s-1",
                                  "HSNDETAILS.LIST": [{"APPLICABLEFROM": "20250401", "HSNCODE": "2523"}]}})
        assert item["hsn"] == "2523"

    def test_a_voucher_row_keeps_flags_ledgers_and_bill_references(self):
        row = mirror.voucher_row(voucher("v-1", "20260901", ISCANCELLED="Yes"))
        assert (row["date"].isoformat(), row["cancelled"], row["optional"], row["party_key"]) == \
            ("2026-09-01", True, False, "supplier")
        assert row["ledgers"] == ["Purchases", "Supplier"]
        assert row["bill_refs"] == [{"ledger": "Supplier", "ledger_key": "supplier", "name": "INV-1",
                                     "bill_type": "New Ref", "amount_cents": 118000, "date": row["date"]}]

    def test_a_deleted_or_retained_deleted_voucher_is_not_a_live_row(self):
        assert mirror.voucher_row(voucher("v-1", "20260901", ISDELETED="Yes")) is None
        assert mirror.voucher_row(voucher("v-1", "20260901", ISDELETEDVCHRETAINED="Yes")) is None


@pytest.fixture
def company():
    import factory
    with factory.connect() as db:
        tenant = factory.tenant(db)
        owner = factory.user(db, tenant, role="admin")
        client = factory.client(db, tenant)
        row = factory.company(db, tenant, factory.device(db, tenant, owner), client)
        yield db, row
        db.rollback()


def build(db, company, *, kind="delta", masters=(), vouchers=(), tombstones=(), coverage=None):
    version = mirror.begin(db, company, kind=kind, reason="test", markers={"alt_mst_id": 1, "alt_vch_id": 1},
                           coverage=coverage or {"from": "2026-04-01", "to": "2027-03-31"})
    mirror.upsert_masters(db, version, list(masters))
    mirror.upsert_vouchers(db, version, list(vouchers))
    if tombstones:
        mirror.tombstone(db, version, "vouchers", list(tombstones))
    return mirror.publish(db, version)


@DB
def test_a_pinned_version_never_sees_later_changes(company):
    db, row = company
    first = build(db, row, kind="full", masters=[ledger("g-1", "Acme")], vouchers=[voucher("v-1", "20260901")])
    second = build(db, row, masters=[ledger("g-1", "Acme Cement", alter=2), ledger("g-2", "New")],
                   tombstones=["v-1"])
    assert (first["version"], second["version"]) == (1, 2)
    old = {m["guid"]: m["name"] for m in mirror.masters(db, row["id"], 1)}
    new = {m["guid"]: m["name"] for m in mirror.masters(db, row["id"], 2)}
    assert (old, new) == ({"g-1": "Acme"}, {"g-1": "Acme Cement", "g-2": "New"})
    assert [v["guid"] for v in mirror.vouchers(db, row["id"], 1)] == ["v-1"]
    assert mirror.vouchers(db, row["id"], 2) == []
    assert mirror.latest(db, row["id"])["version"] == 2
    assert mirror.pins(db, [row["id"]]) == {str(row["id"]): 2}


@DB
def test_an_identical_record_is_seen_not_copied(company):
    db, row = company
    build(db, row, kind="full", masters=[ledger("g-1", "Acme")])
    build(db, row, masters=[ledger("g-1", "Acme")])
    stored = db.execute("SELECT synced_in,seen_in,superseded_in FROM mirror_masters WHERE company_id=%s",
                        (row["id"],)).fetchall()
    assert stored == [{"synced_in": 1, "seen_in": 2, "superseded_in": None}]


@DB
def test_a_full_rebuild_tombstones_what_it_did_not_see(company):
    db, row = company
    build(db, row, kind="full", masters=[ledger("g-1", "Acme"), ledger("g-2", "Gone")],
          vouchers=[voucher("v-1", "20260901"), voucher("v-2", "20260902")])
    build(db, row, kind="full", masters=[ledger("g-1", "Acme")], vouchers=[voucher("v-1", "20260901")])
    assert [m["guid"] for m in mirror.masters(db, row["id"], 2)] == ["g-1"]
    assert [v["guid"] for v in mirror.vouchers(db, row["id"], 2)] == ["v-1"]
    assert {m["guid"] for m in mirror.masters(db, row["id"], 1)} == {"g-1", "g-2"}


@DB
def test_what_a_later_copy_lacks_is_counted_only_on_dates_both_copies_cover(company):
    db, row = company
    before = build(db, row, kind="full", coverage={"from": "2025-04-01", "to": "2026-03-31"}, vouchers=[
        voucher("v-old", "20250901"), voucher("v-gone", "20260110"), voucher("v-edit", "20260201", alter=5),
        voucher("v-kept", "20260301"), voucher("v-late", "20260315")])
    # A year later the window moved on: September 2025 is no longer read, so its absence says nothing.
    after = build(db, row, kind="full", coverage={"from": "2026-01-01", "to": "2027-03-31"}, vouchers=[
        voucher("v-edit", "20260201", alter=3, NARRATION="An earlier edit"), voucher("v-kept", "20260301"),
        voucher("v-new", "20260401")])
    lost = mirror.lost(db, row["id"], before, after)
    assert (lost["missing"], lost["older"]) == (2, 1)
    assert [v["guid"] for v in lost["examples"]] == ["v-late", "v-gone"]
    assert mirror.lost(db, row["id"], after, after) == {"missing": 0, "older": 0, "examples": []}


@DB
def test_an_abandoned_build_leaves_no_trace(company):
    db, row = company
    build(db, row, kind="full", masters=[ledger("g-1", "Acme")])
    version = mirror.begin(db, row, kind="delta", reason="test", markers={}, coverage={"from": "2026-04-01", "to": "2027-03-31"})
    mirror.upsert_masters(db, version, [ledger("g-1", "Renamed", alter=5), ledger("g-3", "Half")])
    mirror.abandon(db, version)
    current = db.execute("SELECT guid,name,synced_in,superseded_in FROM mirror_masters WHERE company_id=%s",
                         (row["id"],)).fetchall()
    assert current == [{"guid": "g-1", "name": "Acme", "synced_in": 1, "superseded_in": None}]
    assert mirror.latest(db, row["id"])["version"] == 1
    # The next build reuses nothing from the abandoned one and gets a new number.
    assert mirror.begin(db, row, kind="delta", reason="test", markers={},
                        coverage={"from": "2026-04-01", "to": "2027-03-31"})["version"] == 3


@DB
def test_only_one_version_builds_at_a_time(company):
    import psycopg
    db, row = company
    mirror.begin(db, row, kind="full", reason="test", markers={}, coverage={"from": "2026-04-01", "to": "2027-03-31"})
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        mirror.begin(db, row, kind="delta", reason="test", markers={}, coverage={"from": "2026-04-01", "to": "2027-03-31"})


def settling(guid, date, bill, amount, *, kind="Agst Ref", alter=1, **flags):
    """A payment to the supplier that settles `amount` of one bill (or pays an Advance ahead of one)."""
    return {"GUID": guid, "MASTERID": "8", "ALTERID": str(alter), "DATE": date, "VOUCHERTYPENAME": "Payment",
            "ALLLEDGERENTRIES.LIST": [{"LEDGERNAME": "Supplier", "AMOUNT": f"-{amount}", "BILLALLOCATIONS.LIST": {
                "NAME": bill, "BILLTYPE": kind, "AMOUNT": f"-{amount}"}}, {"LEDGERNAME": "Bank", "AMOUNT": amount}],
            **flags}


@DB
def test_open_bills_balance_each_bill_from_its_origin_at_the_pinned_version(company):
    import factory
    db, row = company
    supplier = ledger("g-1", "Supplier", ISBILLWISEON="Yes", **{"BILLALLOCATIONS.LIST": [
        {"NAME": "OB-1", "BILLDATE": "20260331", "OPENINGBALANCE": "5000.00", "ISADVANCE": "No"},
        {"NAME": "OB-2", "BILLDATE": "20260330", "OPENINGBALANCE": "700.00"}]})
    payments = [settling("p-1", "20260905", "INV-1", "180.00"),
                settling("p-2", "20260906", "INV-1", "1000.00", ISCANCELLED="Yes"),
                settling("p-3", "20260907", "INV-1", "1000.00", ISOPTIONAL="Yes"),
                settling("p-4", "20260908", "OLD-9", "300.00"),
                settling("p-5", "20260909", "OB-1", "5000.00"),
                settling("p-6", "20260910", "ADV-1", "250.00", kind="Advance")]
    build(db, row, kind="full", masters=[supplier], vouchers=[voucher("v-1", "20260901"), *payments])
    bills = lambda version, company=row: [  # noqa: E731
        (b["name"], b["date"].isoformat(), b["balance_cents"], b["advance"])
        for b in mirror.open_bills(db, company["id"], version, ["supplier"])]
    # Credit balances are owed to the supplier, debit ones paid ahead. Cancelled and optional payments settle
    # nothing; a settled bill and one opened before the mirror's window (OLD-9) are not open bills.
    assert bills(1) == [("OB-2", "2026-03-30", 70000, False), ("INV-1", "2026-09-01", 100000, False),
                        ("ADV-1", "2026-09-10", -25000, True)]
    # Paying the rest of INV-1 settles it at the next version; a run pinned to the first still sees it open.
    build(db, row, vouchers=[settling("p-1", "20260905", "INV-1", "1180.00", alter=2)])
    assert [name for name, *_ in bills(2)] == ["OB-2", "ADV-1"] and bills(1)[1][0] == "INV-1"
    # When the books begin before the mirror's window, opening bills are stale: what settled them is not mirrored.
    tenant = factory.tenant(db)
    older = factory.company(db, tenant, factory.device(db, tenant, factory.user(db, tenant)), factory.client(db, tenant),
                            books_from="2025-04-01")
    build(db, older, kind="full", masters=[supplier], vouchers=[voucher("v-1", "20260901")])
    assert bills(1, older) == [("INV-1", "2026-09-01", 118000, False)]


@DB
def test_the_company_view_feeds_the_existing_voucher_gate(company):
    from minkops_platform.accounts.vouchers import Masters
    db, row = company
    build(db, row, kind="full", masters=[ledger("g-1", "Acme"), {"type": "VOUCHERTYPE", "data": {
        "@_NAME": "Purchase", "@_RESERVEDNAME": "Purchase", "GUID": "t-1", "PARENT": "Purchase", "ISACTIVE": "Yes"}}])
    view = mirror.company_view(db, row, 1)
    masters = Masters(view)
    assert masters.name(masters.one("LEDGER", "g-1", "x", "x")) == "Acme"
    assert masters.family(masters.one("VOUCHERTYPE", "t-1", "x", "x")) == "purchase"
    assert view["company_guid"] == row["guid"] and view["company"] == row["name"]


@DB
def test_a_name_is_found_whatever_punctuation_separates_its_words_and_a_number_matches_whole(company):
    """A narration or bill writes "AG Section-1" for the books' "QA18 AG Section 1"; it is never Section 2."""
    db, row = company
    version = build(db, row, kind="full", masters=[
        ledger("g-1", "QA18 AG Section 1", parent="Indirect Expenses"),
        ledger("g-2", "QA18 AG Section 2", parent="Indirect Expenses"),
        ledger("g-cgst9", "Input CGST 9%", parent="Duties & Taxes"),
        ledger("g-cgst25", "Input CGST 2.5%", parent="Duties & Taxes"),
        ledger("g-cabins", "Portable Site Cabins - UAT", parent="Fixed Assets")])["version"]

    def found(subject):
        return [m["name"] for m in mirror.search_masters(db, row["id"], version, ["LEDGER"], subject)]

    assert found("AG Section-1") == found("ag section 1") == found("AG/Section 1") == ["QA18 AG Section 1"]
    assert found("CGST 9%") == ["Input CGST 9%"] and found("CGST 2.5%") == ["Input CGST 2.5%"]
    # A word may still be part of one, as before: a cabin is among the cabins.
    assert found("site cabin") == ["Portable Site Cabins - UAT"]
    assert found("Section 3") == []
