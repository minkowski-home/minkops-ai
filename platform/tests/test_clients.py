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


def test_a_disconnected_pcs_companies_leave_the_client_and_come_back_from_the_pc_that_replaces_it(db):
    import factory

    from minkops_platform import desktop
    from minkops_platform.accounts import desk_tools
    tenant = factory.tenant(db)
    admin = factory.user(db, tenant, role="admin")
    member = factory.member(db, tenant, admin)
    client = factory.client(db, tenant)
    old = factory.device(db, tenant, admin)
    factory.company(db, tenant, old, client, guid="g-books")
    # Disconnected, a PC's companies no longer hold the client's runs waiting on a PC that will never answer.
    desktop.revoke(db, tenant, admin, old["id"])
    assert clients.companies(db, tenant, client) == []
    with pytest.raises(ServiceError, match="Authorise this client's Tally companies"):
        desk_tools.prepare(db, tenant, admin, client)
    # The PC that replaces it finds the same books as new; once authorised, they are the client's again.
    new = factory.device(db, tenant, admin)
    found = factory.company(db, tenant, new, guid="g-books", status="pending")
    clients.authorise_company(db, tenant, admin, member, found["id"], client["slug"])
    assert [c["id"] for c in clients.companies(db, tenant, client)] == [found["id"]]
    assert [c["id"] for c in desk_tools.prepare(db, tenant, admin, client)[0]] == [found["id"]]


class CompanyIdentityTest(unittest.TestCase):
    """The pure part of company identity: which observed changes are the same company."""

    def test_same_pc_guid_and_books_from_with_a_new_name_is_a_rename(self):
        known = {"guid": "g", "books_from": "2026-04-01", "name": "Old", "company_number": "100000"}
        self.assertEqual(clients.identity_change(known, {**known, "name": "New"}), "renamed")
        self.assertEqual(clients.identity_change(known, {**known, "company_number": "100001"}), "renamed")
        self.assertEqual(clients.identity_change(known, dict(known)), "same")
        self.assertIsNone(clients.identity_change(known, {**known, "books_from": "2027-04-01"}))
