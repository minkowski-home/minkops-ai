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


def build(db, company, *, kind="delta", masters=(), vouchers=(), tombstones=()):
    version = mirror.begin(db, company, kind=kind, reason="test", markers={"alt_mst_id": 1, "alt_vch_id": 1},
                           coverage={"from": "2026-04-01", "to": "2027-03-31"})
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


@DB
def test_bill_references_follow_their_voucher(company):
    db, row = company
    build(db, row, kind="full", vouchers=[voucher("v-1", "20260901")])
    build(db, row, vouchers=[voucher("v-1", "20260901", alter=2, amount="-2360.00")])
    refs = lambda version: [(r["name"], r["amount_cents"]) for r in mirror.bill_refs(db, row["id"], version, ["supplier"])]  # noqa: E731
    assert (refs(1), refs(2)) == ([("INV-1", 118000)], [("INV-1", 236000)])


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
