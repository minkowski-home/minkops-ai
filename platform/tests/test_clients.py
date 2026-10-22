"""Tenant -> client business -> company, with per-client access for practices."""

import os
import unittest

import pytest

from minkops_platform import clients
from minkops_platform.errors import ServiceError

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")


@pytest.fixture
def db():
    from factory import connect
    with connect() as connection:
        yield connection
        connection.rollback()


def test_a_single_business_lets_every_member_reach_every_client(db):
    import factory
    tenant = factory.tenant(db)
    member = factory.user(db, tenant)
    first, second = factory.client(db, tenant), factory.client(db, tenant)
    found = clients.listing(db, tenant, member, factory.member(db, tenant, member))
    assert {c["slug"] for c in found} == {first["slug"], second["slug"]}
    assert all(not c["can_edit"] for c in found)
    assert clients.require(db, tenant, member, factory.member(db, tenant, member), first["slug"])["id"] == first["id"]
    assert clients.visible_ids(db, tenant, member, factory.member(db, tenant, member)) is None


def test_a_practice_scopes_members_to_their_granted_clients(db):
    import factory
    tenant = factory.tenant(db, scoping=True)
    admin, member = factory.user(db, tenant, role="admin"), factory.user(db, tenant)
    granted, other = factory.client(db, tenant), factory.client(db, tenant)
    admin_member, plain = factory.member(db, tenant, admin), factory.member(db, tenant, member)
    clients.grant(db, tenant, admin, admin_member, granted["slug"], member["id"])
    assert [c["slug"] for c in clients.listing(db, tenant, member, plain)] == [granted["slug"]]
    assert clients.visible_ids(db, tenant, member, plain) == {granted["id"]}
    with pytest.raises(ServiceError) as denied:
        clients.require(db, tenant, member, plain, other["slug"])
    assert denied.value.kind == "forbidden"
    # Admins reach every client, and only they change access.
    assert {c["slug"] for c in clients.listing(db, tenant, admin, admin_member)} == {granted["slug"], other["slug"]}
    with pytest.raises(ServiceError) as refused:
        clients.grant(db, tenant, member, plain, other["slug"], member["id"])
    assert refused.value.kind == "forbidden"
    clients.revoke(db, tenant, admin, admin_member, granted["slug"], member["id"])
    assert clients.listing(db, tenant, member, plain) == []


def test_platform_admins_reach_every_client_without_membership(db):
    import factory
    tenant = factory.tenant(db, scoping=True)
    operator = factory.user(db, platform_admin=True)
    client = factory.client(db, tenant)
    assert clients.require(db, tenant, operator, None, client["slug"], edit=True)["id"] == client["id"]


def test_access_grants_only_reach_members_of_the_same_tenant(db):
    import factory
    tenant, elsewhere = factory.tenant(db, scoping=True), factory.tenant(db, scoping=True)
    admin, outsider = factory.user(db, tenant, role="admin"), factory.user(db, elsewhere)
    client = factory.client(db, tenant)
    with pytest.raises(ServiceError) as refused:
        clients.grant(db, tenant, admin, factory.member(db, tenant, admin), client["slug"], outsider["id"])
    assert refused.value.kind == "invalid"


def test_client_slugs_and_names_are_validated(db):
    import factory
    tenant = factory.tenant(db)
    admin = factory.user(db, tenant, role="admin")
    created = clients.create(db, tenant, admin, factory.member(db, tenant, admin), "acme-builders", "Acme Builders")
    assert created["slug"] == "acme-builders"
    for slug, name in (("Bad Slug", "Name"), ("ok", ""), ("acme-builders", "Duplicate")):
        with pytest.raises(ServiceError), db.transaction():
            clients.create(db, tenant, admin, factory.member(db, tenant, admin), slug, name)


def test_a_company_is_authorised_for_one_client_by_an_admin(db):
    import factory
    tenant = factory.tenant(db)
    admin, member = factory.user(db, tenant, role="admin"), factory.user(db, tenant)
    client = factory.client(db, tenant)
    company = factory.company(db, tenant, factory.device(db, tenant, admin), status="pending")
    with pytest.raises(ServiceError):
        clients.authorise_company(db, tenant, member, factory.member(db, tenant, member), company["id"], client["slug"])
    done = clients.authorise_company(db, tenant, admin, factory.member(db, tenant, admin), company["id"], client["slug"])
    assert (done["status"], done["client_id"], done["decided_by"]) == ("authorised", client["id"], admin["id"])
    assert [c["id"] for c in clients.companies(db, tenant, client)] == [company["id"]]
    # Re-authorising for another client is refused; decline is final for that identity.
    other = factory.client(db, tenant)
    with pytest.raises(ServiceError) as moved:
        clients.authorise_company(db, tenant, admin, factory.member(db, tenant, admin), company["id"], other["slug"])
    assert moved.value.kind == "conflict"


def test_a_disconnected_pcs_companies_leave_the_client_and_the_pc_that_replaces_it_continues_them(db):
    import factory

    from minkops_platform import desktop
    from minkops_platform.accounts import desk_tools
    tenant = factory.tenant(db)
    admin = factory.user(db, tenant, role="admin")
    member = factory.member(db, tenant, admin)
    client, other = factory.client(db, tenant), factory.client(db, tenant)
    old, new = factory.device(db, tenant, admin), factory.device(db, tenant, admin)
    books = factory.company(db, tenant, old, client, guid="g-books")
    found = factory.company(db, tenant, new, guid="g-books", status="pending")
    # While the old PC is connected, its copy is the client's: a second copy would split the client's entries.
    for slug in (client["slug"], other["slug"]):
        with pytest.raises(ServiceError, match=f"already {client['name']}'s on {old['name']}"), db.transaction():
            clients.authorise_company(db, tenant, admin, member, found["id"], slug)
    assert clients.predecessor(db, found) is None
    # Disconnected, a PC's companies no longer hold the client's runs waiting on a PC that will never answer.
    desktop.revoke(db, tenant, admin, old["id"])
    assert clients.companies(db, tenant, client) == []
    with pytest.raises(ServiceError, match="Authorise this client's Tally companies"):
        desk_tools.prepare(db, tenant, admin, client)
    # The books the new PC found are the client's company continued: the same row, now on the new PC.
    assert clients.predecessor(db, found)["id"] == books["id"]
    continued = clients.authorise_company(db, tenant, admin, member, found["id"], client["slug"])
    assert (continued["id"], continued["device_id"], continued["continued_from"]) == (books["id"], new["id"], old["id"])
    assert db.execute("SELECT 1 FROM companies WHERE id=%s", (found["id"],)).fetchone() is None
    assert [c["id"] for c in clients.companies(db, tenant, client)] == [books["id"]]
    assert [c["id"] for c in desk_tools.prepare(db, tenant, admin, client)[0]] == [books["id"]]
    # The same decision again finds the company it continued; another client's is refused.
    assert clients.authorise_company(db, tenant, admin, member, found["id"], client["slug"])["id"] == books["id"]
    with pytest.raises(ServiceError, match="already decided"), db.transaction():
        clients.authorise_company(db, tenant, admin, member, found["id"], other["slug"])


def test_only_the_same_books_of_the_same_client_continue_and_an_unclear_owner_is_never_offered(db):
    import factory

    from minkops_platform import desktop
    tenant = factory.tenant(db)
    admin = factory.user(db, tenant, role="admin")
    member = factory.member(db, tenant, admin)
    client, other = factory.client(db, tenant), factory.client(db, tenant)
    old, older, new = (factory.device(db, tenant, admin) for _ in range(3))
    books = factory.company(db, tenant, old, client, guid="g-books")
    theirs = factory.company(db, tenant, old, client, guid="g-theirs")
    factory.company(db, tenant, old, client, guid="g-shared")
    factory.company(db, tenant, older, other, guid="g-shared")
    desktop.revoke(db, tenant, admin, old["id"])
    desktop.revoke(db, tenant, admin, older["id"])
    # A year split keeps the GUID but begins its books later: other books, authorised afresh.
    sibling = factory.company(db, tenant, new, guid="g-books", books_from="2027-04-01", status="pending")
    assert clients.predecessor(db, sibling) is None
    fresh = clients.authorise_company(db, tenant, admin, member, sibling["id"], client["slug"])
    assert (fresh["id"], fresh.get("continued_from")) == (sibling["id"], None)
    # Books authorised for another client start afresh: one client's memory never reaches another.
    found = factory.company(db, tenant, new, guid="g-theirs", status="pending")
    assert clients.predecessor(db, found)["client_id"] == client["id"]
    assert clients.authorise_company(db, tenant, admin, member, found["id"], other["slug"])["id"] == found["id"]
    assert db.execute("SELECT device_id FROM companies WHERE id=%s", (theirs["id"],)).fetchone()["device_id"] == old["id"]
    # Two clients held these books on disconnected PCs: no one-click offer, but naming the client continues its own.
    shared = factory.company(db, tenant, new, guid="g-shared", status="pending")
    assert clients.predecessor(db, shared) is None
    assert clients.authorise_company(db, tenant, admin, member, shared["id"], other["slug"])["continued_from"] == \
        older["id"]
    # A PC disconnected before anyone decided cannot take the books over.
    late = factory.device(db, tenant, admin)
    stranded = factory.company(db, tenant, late, guid="g-books", status="pending")
    desktop.revoke(db, tenant, admin, late["id"])
    with pytest.raises(ServiceError, match="was disconnected"), db.transaction():
        clients.authorise_company(db, tenant, admin, member, stranded["id"], client["slug"])
    assert db.execute("SELECT device_id FROM companies WHERE id=%s", (books["id"],)).fetchone()["device_id"] == old["id"]


def test_two_pcs_copies_of_the_same_books_are_never_both_authorised_even_at_once():
    import threading

    import factory
    with factory.connect() as setup:
        tenant = factory.tenant(setup)
        admin = factory.user(setup, tenant, role="admin")
        client = factory.client(setup, tenant)
        first, second = (factory.company(setup, tenant, factory.device(setup, tenant, admin), guid="g-books",
                                         status="pending") for _ in range(2))
        member = factory.member(setup, tenant, admin)
        setup.commit()
    with factory.connect() as one, factory.connect() as two:
        clients.authorise_company(one, tenant, admin, member, first["id"], client["slug"])
        outcome = {}

        def decide():
            try:
                clients.authorise_company(two, tenant, admin, member, second["id"], client["slug"])
                outcome["second"] = "authorised"
            except ServiceError as error:
                outcome["second"] = error.kind
                two.rollback()

        other = threading.Thread(target=decide)
        other.start()
        other.join(0.5)
        assert other.is_alive()  # The second decision waits for the first one on the same books.
        one.commit()
        other.join(10)
        assert outcome == {"second": "conflict"}


class CompanyIdentityTest(unittest.TestCase):
    """The pure part of company identity: which observed changes are the same company."""

    def test_same_pc_guid_and_books_from_with_a_new_name_is_a_rename(self):
        known = {"guid": "g", "books_from": "2026-04-01", "name": "Old", "company_number": "100000"}
        self.assertEqual(clients.identity_change(known, {**known, "name": "New"}), "renamed")
        self.assertEqual(clients.identity_change(known, {**known, "company_number": "100001"}), "renamed")
        self.assertEqual(clients.identity_change(known, dict(known)), "same")
        self.assertIsNone(clients.identity_change(known, {**known, "books_from": "2027-04-01"}))
