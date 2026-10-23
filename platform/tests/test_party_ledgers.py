"""Party ledgers a person approves: the form in Tally's terms, what the server accepts, and what it trusts back."""

from datetime import date

import pytest

from minkops_platform.accounts import party_ledgers

COMPANY = {"name": "Test", "guid": "company", "books_from": date(2026, 4, 1)}
OWN, STEEL, NEW = "27AAPFU0939F1ZV", "08AABCM1256F1ZR", "08AABCT2468P1ZR"


def group(name, parent):
    return {"type": "GROUP", "data": {"@_NAME": name, "GUID": f"g-{name}", "PARENT": parent}}


def view(*, dated=True):
    """A company whose creditors include a steel sub-group, and whose existing supplier is kept in Tally's dated
    shape (or the older one)."""
    steel = {"@_NAME": "Steel Mart", "GUID": "l-steel", "PARENT": "Creditors - Steel", "ALTERID": "4"}
    steel.update({"LEDGSTREGDETAILS.LIST": {"GSTIN": STEEL, "GSTREGISTRATIONTYPE": "Regular"}} if dated
                 else {"PARTYGSTIN": STEEL, "GSTREGISTRATIONTYPE": "Regular"})
    return {"identity": {"@_NAME": "Test", "GUID": "company", "GSTREGISTRATIONNUMBER": OWN},
            "masters": {"records": [
                group("Sundry Creditors", "Current Liabilities"), group("Creditors - Steel", "Sundry Creditors"),
                group("Staff Advances", "Loans & Advances (Asset)"), group("Capital Account", ""),
                {"type": "LEDGER", "data": steel}]}}


def submitted(**changes):
    """A new supplier's form as a person approves it."""
    value = {"name": "Cabin Services", "under": "Sundry Creditors", "billwise": True, "credit_period": 30,
             "mailing": {"address": ["Plot 12, Auto Nagar"], "state": "Rajasthan", "country": "India",
                         "pincode": "322001"},
             "gst": {"registration_type": "Regular", "gstin": NEW}}
    value.update(changes)
    return value


def test_a_suppliers_form_starts_from_what_the_bill_prints_and_how_the_company_keeps_its_suppliers():
    printed = {"gstin": NEW.lower(), "registration_type": "Regular", "state": "Rajasthan (08)",
               "address": ["Plot 12, Auto Nagar"], "pincode": "322001"}
    form = party_ledgers.form(view(), kind="supplier", name="Cabin Services", printed=printed, billwise=0.8)
    assert form == {"name": "Cabin Services", "under": "Sundry Creditors",
                    "groups": ["Sundry Creditors", "Creditors - Steel"], "billwise": True, "credit_period": None,
                    "mailing": {"address": ["Plot 12, Auto Nagar"], "state": "Rajasthan", "country": "India",
                                "pincode": "322001"},
                    "gst": {"registration_type": "Regular", "gstin": NEW}}
    # Most suppliers kept otherwise, or none yet: the form follows the books, or leaves the choice to the person.
    assert party_ledgers.form(view(), kind="supplier", name="X", billwise=0.2)["billwise"] is False
    assert party_ledgers.form(view(), kind="supplier", name="X")["billwise"] is None
    # Printing no GSTIN, the party is unregistered until the person says otherwise.
    assert party_ledgers.form(view(), kind="supplier", name="X")["gst"] == {"registration_type": "Unregistered",
                                                                             "gstin": None}


def test_a_bank_payees_form_offers_only_the_groups_its_books_use_for_such_parties_most_used_first():
    used = party_ledgers.form(view(), kind="counterparty", name="Ramesh Kumar", used=["Staff Advances", "Sundry Creditors"])
    assert (used["under"], used["groups"]) == ("Staff Advances", [
        "Staff Advances", "Sundry Creditors", "Sundry Debtors", "Loans & Advances (Asset)", "Current Liabilities",
        "Creditors - Steel"])
    # Books too new to say: every safe group, none chosen. Capital, bank or expense groups are never offered.
    fresh = party_ledgers.form(view(), kind="counterparty", name="Ramesh Kumar")
    assert fresh["under"] is None and "Capital Account" not in fresh["groups"]


def test_no_party_goes_under_duties_and_taxes_though_current_liabilities_holds_it():
    taxed = view()
    taxed["masters"]["records"] += [group("Duties & Taxes", "Current Liabilities"), group("GST Payable", "Duties & Taxes"),
                                    group("Provisions", "Current Liabilities")]
    offered = party_ledgers.groups(taxed, "counterparty")
    assert "Provisions" in offered and not {"Duties & Taxes", "GST Payable"} & set(offered)
    for under in ("Duties & Taxes", "GST Payable"):
        with pytest.raises(ValueError, match="Choose a group a party ledger may go under"):
            party_ledgers.plan(taxed, COMPANY, submitted(name="Ramesh Kumar", under=under, gst=None), kind="counterparty")


@pytest.mark.parametrize(("changes", "why"), [
    ({"name": "Steel Mart"}, "Steel Mart is already a ledger or group in Test"),
    ({"name": "creditors - steel"}, "is already a ledger or group"),
    ({"under": "Capital Account"}, "Choose a group a supplier ledger may go under"),
    ({"billwise": None}, "Choose whether the ledger's balances are kept bill by bill"),
    ({"billwise": False}, "for a ledger whose balances are kept bill by bill"),
    ({"credit_period": 400}, "0 to 365 days"),
    ({"gst": {"registration_type": "Regular", "gstin": NEW[:-1] + "A"}}, "The GSTIN is not valid"),
    ({"mailing": {"state": "Maharashtra"}}, "registered in Rajasthan, not Maharashtra"),
    ({"gst": {"registration_type": "Regular", "gstin": STEEL}}, f"{STEEL} is already in this company's books"),
    ({"gst": {"registration_type": "Regular", "gstin": OWN}, "mailing": None}, f"{OWN} is already in this company's"),
    ({"gst": {"registration_type": "Unregistered", "gstin": NEW}}, "An unregistered party has no GSTIN"),
    ({"mailing": {"pincode": "12345"}}, "A PIN code is six digits"),
])
def test_a_form_the_server_cannot_accept_says_what_to_correct(changes, why):
    with pytest.raises(ValueError, match=why):
        party_ledgers.plan(view(), COMPANY, submitted(**changes), kind="supplier")


def test_the_plan_writes_exactly_the_approved_fields_in_the_shape_the_companys_tally_keeps():
    plan = party_ledgers.plan(view(), COMPANY, submitted(), kind="supplier")
    assert plan == {"kind": "ledger", "protocol": 8, "company": "Test", "company_guid": "company", "shape": "dated",
                    "ledger": {"name": "Cabin Services", "under": "Sundry Creditors", "billwise": True,
                               "credit_period": 30, "applicable_from": "2026-04-01",
                               "mailing": {"address": ["Plot 12, Auto Nagar"], "state": "Rajasthan",
                                           "country": "India", "pincode": "322001"},
                               "gst": {"registration_type": "Regular", "gstin": NEW, "state": "Rajasthan",
                                       "applicable_from": "2026-04-01"}},
                    "destination_key": "ledger:company", "identity": {"hash": NEW}}
    assert party_ledgers.plan(view(dated=False), COMPANY, submitted(), kind="supplier")["shape"] == "legacy"
    # A bank payee under a group its books use, unregistered and with no address: only what was given is written.
    payee = party_ledgers.plan(view(), COMPANY, {"name": "Ramesh Kumar", "under": "Staff Advances", "billwise": False,
                                                 "gst": {"registration_type": "Unregistered"}}, kind="counterparty")
    assert payee["ledger"] == {"name": "Ramesh Kumar", "under": "Staff Advances", "billwise": False,
                                    "credit_period": None, "mailing": None, "gst": None, "applicable_from": "2026-04-01"}
    assert payee["identity"] == {"hash": "ramesh kumar"}


def readback(plan, **changes):
    """The ledger as the companion reads it back from Tally after creating exactly this plan."""
    ledger = plan["ledger"]
    master = {"@_NAME": ledger["name"], "GUID": "new-guid", "ALTERID": "9", "PARENT": ledger["under"],
              "ISBILLWISEON": "Yes" if ledger["billwise"] else "No", "BILLCREDITPERIOD": "30 Days",
              "LEDGSTREGDETAILS.LIST": {"GSTIN": NEW, "GSTREGISTRATIONTYPE": "Regular"},
              "LEDMAILINGDETAILS.LIST": {"STATE": "Rajasthan", "PINCODE": "322001",
                                         "ADDRESS.LIST": {"ADDRESS": ["Plot 12, Auto Nagar"]}}}
    master.update(changes)
    return {"company_guid": plan["company_guid"], "ledger": master}


def test_only_a_readback_showing_every_approved_field_is_trusted():
    plan = party_ledgers.plan(view(), COMPANY, submitted(), kind="supplier")
    # Trusted, the ledger is kept as Tally holds it, so the bill entered with it sees its bill-by-bill balances and GST.
    master, problem = party_ledgers.verified(plan, readback(plan))
    assert (problem, master["GUID"], master["ISBILLWISEON"], master["LEDGSTREGDETAILS.LIST"]["GSTIN"]) == (
        None, "new-guid", "Yes", NEW)
    master, problem = party_ledgers.verified(plan, readback(plan, PARENT="Creditors - Steel", BILLCREDITPERIOD="45 Days",
                                                            ISBILLWISEON="No"))
    assert (master, problem) == (None, "The ledger Cabin Services in Tally differs from what was approved: it is under "
                                       "Creditors - Steel, its bill-by-bill setting, its credit period. Review it there.")
    assert party_ledgers.verified(plan, readback(plan, **{"LEDGSTREGDETAILS.LIST": {"GSTIN": STEEL}}))[1].endswith(
        "its GSTIN, its GST registration type. Review it there.")
    assert party_ledgers.verified(plan, {**readback(plan), "company_guid": "other"}) == (
        None, "Tally answered for another company, so the ledger was not verified.")
    assert party_ledgers.verified(plan, {"outcome": "attention", "message": "Tally is busy."}) == (None, "Tally is busy.")
