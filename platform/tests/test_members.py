"""Who belongs to a workspace, in which role, and which workflows each member runs."""

import os

import pytest

from minkops_platform import identity, members, work
from minkops_platform.errors import ServiceError

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")
PASSWORD = "a long enough password"


@pytest.fixture
def db():
    from factory import connect
    with connect() as connection:
        yield connection
        connection.rollback()


@pytest.fixture
def workspace(db):
    import factory
    tenant = factory.tenant(db)
    admin = factory.user(db, tenant, role="admin")
    return {"tenant": tenant, "admin": admin, "bills": factory.workflow(db, tenant, "bill-entry"),
            "statements": factory.workflow(db, tenant, "statement-entry")}


def joined(db, workspace, role="member", email=None):
    """Someone invited by the workspace's admin who accepts with a new account."""
    import factory
    email = email or f"{factory.suffix()}@example.com"
    sent = members.invite(db, workspace["tenant"], workspace["admin"], email, role)
    return members.accept(db, sent["token"], name="New Person", password=PASSWORD)


def test_an_invitation_creates_a_verified_account_in_its_workspace_with_its_role_once(db, workspace):
    import factory
    email = f"{factory.suffix()}@Example.com"
    sent = members.invite(db, workspace["tenant"], workspace["admin"], email, "admin")
    shown = members.invitation(db, sent["token"])
    assert (shown["workspace"], shown["email"], shown["role"], shown["account"]) == (
        workspace["tenant"]["name"], email.lower(), "admin", False)
    person = members.accept(db, sent["token"], name="Ravi Kumar", password=PASSWORD)
    assert identity.authenticate(db, email, PASSWORD)["id"] == person["id"]
    assert [(m["email"], m["role"]) for m in members.members(db, workspace["tenant"])
            if m["id"] == person["id"]] == [(email.lower(), "admin")]
    for token in (sent["token"], "not a token"):
        with pytest.raises(ServiceError) as used:
            members.invitation(db, token)
        assert used.value.kind == "not_found"
    late = members.invite(db, workspace["tenant"], workspace["admin"], f"{factory.suffix()}@example.com", "member")
    db.execute("UPDATE invitations SET expires_at=now() - interval '1 second' WHERE token_hash=%s",
               (identity.digest(late["token"]),))
    with pytest.raises(ServiceError):
        members.accept(db, late["token"], name="Too Late", password=PASSWORD)


def test_a_person_belongs_to_one_workspace(db, workspace):
    import factory
    elsewhere = factory.tenant(db)
    other_admin = factory.user(db, elsewhere, role="admin")
    person = joined(db, workspace)
    for tenant, actor, why in ((workspace["tenant"], workspace["admin"], "already a member of this workspace"),
                               (elsewhere, other_admin, "already belongs to another workspace")):
        with pytest.raises(ServiceError, match=why):
            members.invite(db, tenant, actor, person["email"], "member")
    # Invited by two workspaces at once, the second link finds the person taken.
    email = f"{factory.suffix()}@example.com"
    here = members.invite(db, workspace["tenant"], workspace["admin"], email, "member")
    there = members.invite(db, elsewhere, other_admin, email, "member")
    members.accept(db, here["token"], name="Two Invites", password=PASSWORD)
    with pytest.raises(ServiceError, match="already belongs to a workspace"):
        members.accept(db, there["token"], user=identity.authenticate(db, email, PASSWORD))


def test_an_existing_account_signs_in_to_accept(db, workspace):
    import factory
    left = joined(db, workspace)
    members.remove(db, workspace["tenant"], workspace["admin"], left["id"])
    elsewhere = factory.tenant(db)
    sent = members.invite(db, elsewhere, factory.user(db, elsewhere, role="admin"), left["email"], "member")
    assert members.invitation(db, sent["token"])["account"] is True
    with pytest.raises(ServiceError) as sign_in:
        members.accept(db, sent["token"], name="Someone", password="any long password here")
    assert (sign_in.value.kind, sign_in.value.payload) == ("conflict", {"sign_in": True})
    stranger = factory.user(db)
    with pytest.raises(ServiceError, match="This invitation is for"):
        members.accept(db, sent["token"], user=stranger)
    assert members.accept(db, sent["token"], user=identity.authenticate(db, left["email"], PASSWORD))["id"] == left["id"]


def test_a_resend_replaces_the_link_and_a_withdrawn_invitation_opens_nothing(db, workspace):
    import factory
    sent = members.invite(db, workspace["tenant"], workspace["admin"], f"{factory.suffix()}@example.com", "member")
    again = members.resend(db, workspace["tenant"], workspace["admin"], sent["invitation"]["id"])
    with pytest.raises(ServiceError):
        members.invitation(db, sent["token"])
    assert members.invitation(db, again["token"])["role"] == "member"
    [listed] = [i for i in members.invitations(db, workspace["tenant"]) if i["id"] == sent["invitation"]["id"]]
    assert (listed["invited_by"], listed["expired"]) == (workspace["admin"]["name"], False)
    members.withdraw(db, workspace["tenant"], workspace["admin"], sent["invitation"]["id"])
    with pytest.raises(ServiceError):
        members.invitation(db, again["token"])


def test_a_member_runs_the_workflows_assigned_and_an_admin_runs_every_one(db, workspace):
    import factory
    tenant, admin = workspace["tenant"], workspace["admin"]
    person = joined(db, workspace)
    member = factory.member(db, tenant, person)
    assert members.assigned(db, tenant, admin, factory.member(db, tenant, admin)) is None
    assert members.assigned(db, tenant, person, member) == {}
    members.update(db, tenant, admin, person["id"], workflow_ids=[workspace["bills"]["id"]])
    assert members.assigned(db, tenant, person, member) == {workspace["bills"]["id"]: "bill-entry"}
    members.require_workflow(db, tenant, person, member, key="bill-entry")
    with pytest.raises(ServiceError) as hidden:
        members.require_workflow(db, tenant, person, member, workflow_id=workspace["statements"]["id"])
    assert hidden.value.kind == "not_found"
    # Another workspace's workflow cannot be assigned.
    foreign = factory.workflow(db, factory.tenant(db), "bill-entry")
    with pytest.raises(ServiceError) as refused:
        members.update(db, tenant, admin, person["id"], workflow_ids=[foreign["id"]])
    assert refused.value.kind == "invalid"


def test_a_workspace_always_keeps_an_admin(db, workspace):
    tenant, admin = workspace["tenant"], workspace["admin"]
    for change in (lambda: members.update(db, tenant, admin, admin["id"], role="member"),
                   lambda: members.remove(db, tenant, admin, admin["id"])):
        with pytest.raises(ServiceError, match="only admin"):
            change()
    second = joined(db, workspace, role="admin")
    members.update(db, tenant, second, admin["id"], role="member")
    assert {m["id"]: m["role"] for m in members.members(db, tenant)}[admin["id"]] == "member"


def test_removing_a_member_signs_them_out_and_disconnects_their_pcs_while_their_runs_go_on(db, workspace):
    import factory
    tenant, admin = workspace["tenant"], workspace["admin"]
    person = joined(db, workspace)
    members.update(db, tenant, admin, person["id"], workflow_ids=[workspace["bills"]["id"]])
    session = identity.start_session(db, person["id"], None)
    pc = factory.device(db, tenant, person)
    run = factory.run(db, tenant, factory.client(db, tenant), workspace["bills"], person,
                      [work.ItemSpec("bill", {"file_id": "f-1"})])
    removed = members.remove(db, tenant, admin, person["id"])
    assert removed == {"pcs": 1}
    assert person["id"] not in {m["id"] for m in members.members(db, tenant)}
    assert identity.session_user(db, session) is None
    assert db.execute("SELECT revoked_at FROM desktop_devices WHERE id=%s", (pc["id"],)).fetchone()["revoked_at"]
    assert db.execute("SELECT count(*) AS n FROM workflow_assignments WHERE user_id=%s",
                      (person["id"],)).fetchone()["n"] == 0
    # The work they started carries on, for others to review.
    assert work.get_run(db, tenant["id"], run["id"])["state"] == run["state"]
