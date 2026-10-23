"""People's accounts: passwords, sessions, password resets and profile."""

import os

import pytest

from minkops_platform import identity
from minkops_platform.errors import ServiceError

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")
PASSWORD = "a long enough password"


@pytest.fixture
def db():
    from factory import connect
    with connect() as connection:
        yield connection
        connection.rollback()


def account(db, password=PASSWORD):
    import factory
    return identity.create_account(db, email=f"{factory.suffix()}@Example.com", name="Asha Rao", password=password)


def test_an_account_is_verified_and_signs_in_by_its_password_only(db):
    created = account(db)
    assert created["email"] == created["email"].lower()
    assert identity.authenticate(db, created["email"].upper(), PASSWORD)["id"] == created["id"]
    assert identity.authenticate(db, created["email"], "not the password at all") is None
    assert identity.authenticate(db, "nobody@example.com", PASSWORD) is None
    for name, password in (("A", PASSWORD), ("Asha Rao", "too short")):
        with pytest.raises(ServiceError) as refused:
            identity.create_account(db, email="x@example.com", name=name, password=password)
        assert refused.value.kind == "invalid"
    with pytest.raises(ServiceError) as taken:
        identity.create_account(db, email=created["email"], name="Someone", password=PASSWORD)
    assert taken.value.kind == "conflict"


def test_a_person_sees_their_sessions_and_ends_them(db):
    person = account(db)
    here = identity.start_session(db, person["id"], "Firefox on Windows")
    there = identity.start_session(db, person["id"], "Chrome on Android " + "x" * 400)
    assert identity.session_user(db, here)["id"] == person["id"]
    listed = identity.sessions(db, person["id"], here)
    # This browser first; a browser's description is kept to 300 characters.
    assert [(s["current"], len(s["user_agent"])) for s in listed] == [(True, 18), (False, 300)]
    # Ending the others leaves this one; ending one by its id signs that browser out.
    assert identity.end_other_sessions(db, person["id"], here) == 1
    assert identity.session_user(db, there) is None
    identity.end_session(db, person["id"], listed[0]["id"])
    assert identity.session_user(db, here) is None
    with pytest.raises(ServiceError):
        identity.end_session(db, person["id"], listed[0]["id"])


def test_changing_a_password_needs_the_current_one_and_ends_the_other_sessions(db):
    person = account(db)
    here, there = (identity.start_session(db, person["id"], None) for _ in range(2))
    with pytest.raises(ServiceError) as wrong:
        identity.change_password(db, person["id"], here, current="not my password", new="a new long password")
    assert wrong.value.kind == "invalid"
    identity.change_password(db, person["id"], here, current=PASSWORD, new="a new long password")
    assert identity.session_user(db, here)["id"] == person["id"]
    assert identity.session_user(db, there) is None
    assert identity.authenticate(db, person["email"], "a new long password")
    identity.rename(db, person["id"], "  Asha R.  ")
    assert identity.session_user(db, here)["name"] == "Asha R."


def test_a_reset_link_works_once_within_the_hour_and_says_nothing_about_unknown_addresses(db):
    person = account(db)
    session = identity.start_session(db, person["id"], None)
    assert identity.request_reset(db, "nobody@example.com") is None
    first, second = (identity.request_reset(db, person["email"].upper()) for _ in range(2))
    identity.reset_password(db, second["token"], "a brand new password")
    assert identity.authenticate(db, person["email"], "a brand new password")
    # Every session ends, and every other outstanding link dies with the used one.
    assert identity.session_user(db, session) is None
    for token in (first["token"], second["token"]):
        with pytest.raises(ServiceError) as used:
            identity.reset_password(db, token, "yet another password")
        assert used.value.kind == "not_found"
    db.execute("UPDATE password_resets SET expires_at=now() - interval '1 second' WHERE user_id=%s", (person["id"],))
    late = identity.request_reset(db, person["email"])
    db.execute("UPDATE password_resets SET expires_at=now() - interval '1 second' WHERE user_id=%s", (person["id"],))
    with pytest.raises(ServiceError):
        identity.reset_password(db, late["token"], "yet another password")
    # Three links an hour: a fourth request sends nothing.
    assert identity.request_reset(db, person["email"]) is None


def test_an_unverified_account_from_before_invitations_is_verified_by_a_reset(db):
    import factory
    row = db.execute("""INSERT INTO users(email,name,password_hash) VALUES (%s,'Old',%s) RETURNING id,email""",
                     (f"{factory.suffix()}@example.com", identity.passwords.hash(PASSWORD))).fetchone()
    with pytest.raises(ServiceError) as unverified:
        identity.authenticate(db, row["email"], PASSWORD)
    assert unverified.value.kind == "forbidden"
    identity.reset_password(db, identity.request_reset(db, row["email"])["token"], "a verified password")
    assert identity.authenticate(db, row["email"], "a verified password")["id"] == row["id"]
