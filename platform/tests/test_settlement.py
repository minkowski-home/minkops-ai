"""Which bills a bank row settles: evident allocations are written, anything else waits for one click."""

from datetime import date

import pytest

from minkops_platform.accounts import settlement


def bill(name, rupees, day=1, advance=False):
    """An open bill as the mirror balances it: credit positive, so a supplier's unpaid bill is positive."""
    return {"ledger": "Steel Mart", "name": name, "date": date(2026, 9, day), "balance_cents": rupees * 100,
            "advance": advance}


def against(name, rupees):
    return {"type": "Agst Ref", "name": name, "amount_cents": rupees * 100}


def on_account(rupees):
    return {"type": "On Account", "amount_cents": rupees * 100}


OPEN = [bill("SM/101", 1180, 1), bill("SM/102", 5000, 2), bill("SM/103", 5000, 3)]


def allocate(bills, rupees, text="NEFT STEEL MART", proposed=None, payment=True):
    return settlement.allocate(bills, amount_cents=rupees * 100, payment=payment, text=text, proposed=proposed)


@pytest.mark.parametrize(("case", "bills", "rupees", "text", "proposed", "settled"), [
    ("the narration names the bill it pays in part", OPEN, 600, "NEFT SM/102 PART", [against("SM/102", 600)],
     [against("SM/102", 600)]),
    ("a narration's spacing and separators do not matter", OPEN, 5000, "NEFT SM 102", None, [against("SM/102", 5000)]),
    ("the only open bills that add up to the amount", OPEN, 10000, "NEFT STEEL MART", None,
     [against("SM/102", 5000), against("SM/103", 5000)]),
    ("the session may propose that same allocation", OPEN, 1180, "NEFT STEEL MART", [against("SM/101", 1180)],
     [against("SM/101", 1180)]),
    ("nothing is open, so the payment goes on account", [], 900, "NEFT STEEL MART", None, [on_account(900)]),
    ("paid ahead of its bill as a named Advance", [], 900, "NEFT STEEL MART",
     [{"type": "Advance", "name": "UTR77", "amount_cents": 90000}], [{"type": "Advance", "name": "UTR77",
                                                                       "amount_cents": 90000}]),
    ("a debit balance is no bill a payment settles", [bill("ADV-1", -300, advance=True)], 900, "NEFT", None,
     [on_account(900)]),
    ("the named bill is settled and nothing else is open for the rest", OPEN[:1], 1500, "NEFT SM/101", None,
     [against("SM/101", 1180), on_account(320)]),
    ("a receipt settles a debit balance it names", [bill("SM/R1", -400)], 400, "REFUND SM/R1", None,
     [against("SM/R1", 400)]),
])
def test_an_evident_allocation_is_accepted(case, bills, rupees, text, proposed, settled):
    assert allocate(bills, rupees, text, proposed, payment="REFUND" not in text) == settled


@pytest.mark.parametrize(("case", "rupees", "text", "proposed", "why", "choices"), [
    ("two open bills of the amount and a silent narration", 5000, "NEFT STEEL MART", None,
     "Several sets of open bills add up to this amount, and the narration names none of them.",
     [[against("SM/102", 5000)], [against("SM/103", 5000)], [against("SM/101", 1180), against("SM/102", 3820)],
      [on_account(5000)]]),
    ("part of an unnamed bill", 1000, "NEFT STEEL MART", None,
     "No set of open bills adds up to this amount, and the narration names none of them.",
     [[against("SM/101", 1000)], [on_account(1000)]]),
    ("on account while bills are open", 1180, "NEFT STEEL MART", [on_account(1180)],
     "Only SM/101 adds up to this amount, but the proposal settles it otherwise.",
     [[on_account(1180)], [against("SM/101", 1180)]]),
    ("the narration names one bill and the amount fits another", 1180, "NEFT SM/102", None,
     "The narration names SM/102, but other open bills add up to this amount.",
     [[against("SM/102", 1180)], [against("SM/101", 1180)], [on_account(1180)]]),
    ("more than the open bills add up to", 12000, "NEFT STEEL MART", None,
     "No set of open bills adds up to this amount, and the narration names none of them.",
     [[against("SM/101", 1180), against("SM/102", 5000), against("SM/103", 5000), on_account(820)],
      [on_account(12000)]]),
])
def test_an_allocation_the_books_do_not_settle_waits_with_its_choices(case, rupees, text, proposed, why, choices):
    with pytest.raises(settlement.Unresolved) as held:
        allocate(OPEN, rupees, text, proposed)
    assert held.value.reason == why
    # The session's own allocation comes first, then the books' candidates; each is offered once.
    assert [choice["bills"] for choice in held.value.choices] == choices


def test_choices_are_labelled_as_a_person_reads_them():
    with pytest.raises(settlement.Unresolved) as held:
        allocate(OPEN, 12000)
    assert [choice["label"] for choice in held.value.choices] == [
        "Settle SM/101, SM/102 and SM/103 in full, and 820.00 on account", "On account, settling no bill"]
    with pytest.raises(settlement.Unresolved) as held:
        allocate(OPEN, 1000)
    assert held.value.choices[0]["label"] == "Settle 1000.00 of SM/101 (1180.00 open)"


@pytest.mark.parametrize(("case", "proposed", "message"), [
    ("a bill that is not open", [against("SM/999", 1180)], "SM/999 is not an open bill this payment can settle"),
    ("more than a bill has open", [against("SM/101", 2000)], "SM/101 has 1180.00 open, less than 2000.00"),
    ("a debit balance against a payment", [against("ADV-1", 300)], "ADV-1 is not an open bill this payment can settle"),
    ("references that do not add up", [against("SM/101", 1180), on_account(100)],
     "The bills must add up to the counter line's 2000.00"),
    ("a new bill from a bank row", [{"type": "New Ref", "name": "X1", "amount_cents": 200000}],
     "A bank row settles bills"),
    ("an Advance that reuses an open bill's name", [{"type": "Advance", "name": "SM/101", "amount_cents": 200000}],
     "An Advance names a new bill"),
    ("one bill named twice", [against("SM/102", 1000), against("SM/102", 1000)], "SM/102 is named twice"),
    ("an On Account amount with a name", [{"type": "On Account", "name": "X", "amount_cents": 200000}],
     "On Account names no bill"),
])
def test_an_allocation_that_cannot_be_written_is_refused_with_its_reason(case, proposed, message):
    bills = [*OPEN, bill("ADV-1", -300, advance=True)]
    with pytest.raises(ValueError, match=message.replace("(", r"\(").replace(")", r"\)")):
        allocate(bills, 2000, proposed=proposed)
