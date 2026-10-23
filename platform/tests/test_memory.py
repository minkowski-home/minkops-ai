"""Employee memory: what was learnt stays true to the books, and only people state or change its rules."""

import os

import pytest

from minkops_platform.accounts import memory
from minkops_platform.errors import ServiceError

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")

LEDGERS = {"g-sunrise": ("Sunrise Office Systems", "Sundry Creditors"), "g-cabins": ("Office Cabins", "Fixed Assets"),
           "g-cgst": ("Input CGST 9%", "Duties & Taxes"), "g-repairs": ("Repairs", "Indirect Expenses")}


def masters(*without):
    rows = [{"type": "LEDGER", "data": {"@_NAME": name, "GUID": guid, "PARENT": parent, "ALTERID": "1"}}
            for guid, (name, parent) in LEDGERS.items() if guid not in without]
    return rows + [{"type": "VOUCHERTYPE", "data": {"@_NAME": "Purchase", "@_RESERVEDNAME": "Purchase",
                                                    "GUID": "vt-purchase", "PARENT": "Purchase", "ALTERID": "1"}}]


def saved(expense="Office Cabins", alter="3"):
    """The voucher Minkops saved for Sunrise's bill, as Tally holds it now."""
    return {"GUID": "v-1", "MASTERID": "5", "ALTERID": alter, "DATE": "20260901", "VOUCHERTYPENAME": "Purchase",
            "REFERENCE": "SOS/26/0412", "PARTYLEDGERNAME": "Sunrise Office Systems",
            "ALLLEDGERENTRIES.LIST": [{"LEDGERNAME": "Sunrise Office Systems", "AMOUNT": "11800.00"},
                                      {"LEDGERNAME": expense, "AMOUNT": "-10000.00"},
                                      {"LEDGERNAME": "Input CGST 9%", "AMOUNT": "-1800.00"}]}


@pytest.fixture
def books():
    import factory
    with factory.connect() as db:
        tenant = factory.tenant(db)
        admin, clerk = factory.user(db, tenant, role="admin"), factory.user(db, tenant, role="member")
        client = factory.client(db, tenant)
        device = factory.device(db, tenant, admin)
        company = factory.company(db, tenant, device, client)
        factory.books(db, company, masters(), [saved()])
        yield {"db": db, "tenant": tenant, "client": client, "company": company,
               "admin": (admin, factory.member(db, tenant, admin)), "clerk": (clerk, factory.member(db, tenant, clerk))}
        db.rollback()


def booking(books):
    """What Minkops learnt when Sunrise's bill was approved and verified."""
    company = books["company"]
    return memory.record(books["db"], tenant_id=company["tenant_id"], client_id=company["client_id"],
                         company_id=company["id"], kind="booking", subject="g-sunrise:cabins",
                         value={"supplier": "Sunrise Office Systems", "voucher_type": "Purchase",
                                "ledgers": ["Office Cabins"]},
                         guids=["g-sunrise", "vt-purchase", "g-cabins"],
                         evidence={"kind": "outcome", "voucher": "v-1"}, status="confirmed",
                         actor_id=books["admin"][0]["id"])


def sync(books, records, vouchers):
    """A sync publishes the next version of the books, then revalidates what memory learnt from them."""
    import factory
    version = factory.books(books["db"], books["company"], records, vouchers)
    memory.revalidate(books["db"], books["company"], version)
    return memory.live(books["db"], books["company"]["tenant_id"], books["company"]["client_id"],
                       company_id=books["company"]["id"], kind="booking", subject="g-sunrise:cabins") or books["db"].execute(
        "SELECT * FROM memory_entries WHERE company_id=%s AND kind='booking'", (books["company"]["id"],)).fetchone()


def test_an_edit_made_in_tally_demotes_what_was_learnt_and_lost_masters_retire_it(books):
    entry = booking(books)
    # Unchanged books keep the entry confirmed.
    assert sync(books, masters(), [saved()])["status"] == "confirmed"
    # Someone rebooked the saved bill to repairs in Tally: the booking Minkops learnt is no longer trusted.
    demoted = sync(books, masters(), [saved("Repairs", alter="4")])
    assert (demoted["status"], demoted["version"]) == ("demoted", entry["version"])
    actions = [row["action"] for row in books["db"].execute(
        "SELECT action FROM memory_events WHERE entry_id=%s ORDER BY id", (entry["id"],))]
    assert actions == ["created", "demoted"]
    # A ledger it names missing from three syncs in a row retires it; one sync with it back resets the count.
    assert sync(books, masters("g-cabins"), [saved("Repairs", alter="4")])["misses"] == 1
    assert sync(books, masters(), [saved("Repairs", alter="4")])["misses"] == 0
    for _ in range(3):
        last = sync(books, masters("g-cabins"), [saved("Repairs", alter="4")])
    assert last["status"] == "retired"


def test_rules_are_versioned_and_scoped_and_a_seed_is_applied_once(books):
    db, tenant, slug = books["db"], books["tenant"], books["client"]["slug"]
    admin, clerk = books["admin"], books["clerk"]
    client_id, company_id = books["client"]["id"], books["company"]["id"]
    rule = memory.write_instruction(db, tenant, *admin, slug, text="Book NEFT returns as two entries.",
                                    workflow_key="statement-entry")
    edited = memory.write_instruction(db, tenant, *admin, slug, instruction_id=rule["id"],
                                      text="Book both legs of a NEFT return.", workflow_key="statement-entry")
    assert (rule["version"], edited["version"]) == (1, 2)
    # Proposals cite a rule by ID and version, so every version stays readable.
    assert [row["text"] for row in db.execute(
        "SELECT text FROM memory_instruction_versions WHERE instruction_id=%s ORDER BY version", (rule["id"],))] == [
        "Book NEFT returns as two entries.", "Book both legs of a NEFT return."]
    sites = memory.write_instruction(db, tenant, *admin, slug, text="A site note names the cost centre.",
                                     company_id=company_id)
    scoped = lambda workflow: [r["id"] for r in memory.instructions(  # noqa: E731
        db, tenant["id"], client_id, workflow_key=workflow, company_ids=[company_id])]
    assert scoped("bill-entry") == [sites["id"]]
    assert sorted(scoped("statement-entry")) == sorted([rule["id"], sites["id"]])
    # A disabled rule is never offered.
    memory.set_instruction(db, tenant, *admin, slug, sites["id"], status="disabled")
    assert scoped("bill-entry") == []
    # A seed the client agreed is written once, and never brought back after an admin deletes it.
    seeds = [{"key": "neft-returns", "workflow": "statement-entry", "text": "Book both legs of a NEFT return."}]
    memory.seed(db, tenant["id"], client_id, seeds)
    memory.seed(db, tenant["id"], client_id, seeds)
    seeded = [r for r in memory.instructions(db, tenant["id"], client_id, workflow_key="statement-entry",
                                             company_ids=[]) if r["id"] != rule["id"]]
    assert [r["text"] for r in seeded] == ["Book both legs of a NEFT return."]
    memory.delete_instruction(db, tenant, *admin, slug, seeded[0]["id"])
    memory.seed(db, tenant["id"], client_id, seeds)
    assert [r["id"] for r in memory.instructions(db, tenant["id"], client_id, workflow_key="statement-entry",
                                                 company_ids=[])] == [rule["id"]]
    with pytest.raises(ServiceError, match="Only workspace admins"):
        memory.write_instruction(db, tenant, *clerk, slug, text="Book everything to suspense.")
    # Sessions read every active rule at once, so a client keeps a bounded number of them.
    for n in range(memory.RULES - 1):
        memory.write_instruction(db, tenant, *admin, slug, text=f"Rule {n}.")
    for attempt in (lambda: memory.write_instruction(db, tenant, *admin, slug, text="One rule too many."),
                    lambda: memory.set_instruction(db, tenant, *admin, slug, sites["id"], status="active")):
        with pytest.raises(ServiceError, match=f"already has {memory.RULES} active rules"):
            attempt()


def test_the_memory_page_shows_what_was_learnt_and_only_admins_disable_or_delete_it(books):
    db, tenant, slug = books["db"], books["tenant"], books["client"]["slug"]
    entry = booking(books)
    # Every member who can reach the client reads its memory, with the evidence behind each entry.
    [shown] = memory.page(db, tenant, *books["clerk"], slug)["entries"]
    assert {key: shown[key] for key in ("id", "kind", "subject", "status", "uses", "company")} == {
        "id": str(entry["id"]), "kind": "booking", "subject": "Sunrise Office Systems", "status": "confirmed",
        "uses": 0, "company": books["company"]["name"]}
    assert shown["value"] == entry["value"] and shown["evidence"] == [{"kind": "outcome", "voucher": "v-1"}]
    with pytest.raises(ServiceError, match="Only workspace admins"):
        memory.set_entry(db, tenant, *books["clerk"], slug, entry["id"], "disabled")
    memory.set_entry(db, tenant, *books["admin"], slug, entry["id"], "disabled")
    assert memory.entries(db, tenant["id"], books["client"]["id"], company_ids=[books["company"]["id"]]) == []
    memory.set_entry(db, tenant, *books["admin"], slug, entry["id"], "retired")
    assert memory.page(db, tenant, *books["admin"], slug)["entries"] == []
