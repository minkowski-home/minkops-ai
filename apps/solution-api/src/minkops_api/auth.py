"""Transport for people's accounts: server sessions in a cookie, CSRF, and the links sent by email.

The accounts themselves, and who belongs to which workspace, live in the platform (`identity`, `members`). There is
no public sign-up: a person joins through an invitation's link (docs/workspace-access.md).
"""

import atexit
import os
import secrets
import smtplib
from email.message import EmailMessage
from threading import Lock
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, EmailStr, Field

from minkops_connectors.email import send_email
from minkops_platform import identity, members

from .service import call as _call

router = APIRouter(prefix="/api")
digest = identity.digest
# Firebase Hosting forwards only this cookie to Cloud Run. Its value remains
# our opaque PostgreSQL session token; Google does not own user authentication.
SESSION_COOKIE = "__session"
LEGACY_SESSION_COOKIE = "minkops_session"
_pool = None
_pool_url = None
_pool_lock = Lock()


def database_pool():
    """Bound request connections to the pilot DB budget and reuse warm sockets."""
    global _pool, _pool_url
    url = os.getenv("DATABASE_URL")
    if not url:
        raise HTTPException(503, "Database is not configured.")
    with _pool_lock:
        if _pool is None or _pool_url != url or _pool.closed:
            if _pool is not None:
                _pool.close()
            _pool = ConnectionPool(url, min_size=0, max_size=3, max_waiting=16,
                                   timeout=10, max_idle=30, num_workers=1, open=True,
                                   kwargs={"row_factory": dict_row, "connect_timeout": 5})
            _pool_url = url
        return _pool


@atexit.register
def close_database_pool():
    if _pool is not None:
        _pool.close()


def session_token(request: Request) -> str:
    return request.cookies.get(SESSION_COOKIE) or request.cookies.get(LEGACY_SESSION_COOKIE, "")


def database():
    with database_pool().connection() as connection:
        # Commit the deadline fence before request work: an unauthorized or
        # failed request cannot roll it back. Reuse this request's connection.
        from minkops_platform.run_limits import expire
        connection.execute("SET LOCAL lock_timeout='1s'")
        expire(connection)
        connection.commit()
        yield connection


# Commit before a response-triggered wake-up reads the durable notification.
Db = Annotated[psycopg.Connection, Depends(database, scope="function")]


def session_user(request: Request, connection: Db) -> dict:
    if not session_token(request):
        raise HTTPException(401, "Sign in required.")
    row = identity.session_user(connection, session_token(request))
    if not row:
        raise HTTPException(401, "Session expired. Sign in again.")
    return row


User = Annotated[dict, Depends(session_user)]


def require_csrf(request: Request) -> None:
    token = session_token(request)
    sent = request.headers.get("x-csrf-token", "")
    expected = digest(f"{token}:csrf")
    if not token or not sent or not secrets.compare_digest(sent, expected):
        raise HTTPException(403, "Invalid request token.")


def tenant_access(slug: str, user: dict, connection: psycopg.Connection, *, edit=False):
    tenant = connection.execute("SELECT id, slug, name FROM tenants WHERE slug = %s", (slug,)).fetchone()
    if not tenant:
        raise HTTPException(404, "Workspace not found.")
    member = connection.execute(
        "SELECT role FROM memberships WHERE tenant_id = %s AND user_id = %s",
        (tenant["id"], user["id"]),
    ).fetchone()
    if not member and not user["is_platform_admin"]:
        raise HTTPException(403, "Workspace access required.")
    if edit and not user["is_platform_admin"] and member["role"] != "admin":
        raise HTTPException(403, "Workspace admin access required.")
    return tenant, member


# --- email ----------------------------------------------------------------------------------------------------------

def link(path: str) -> str:
    return f"{os.getenv('PUBLIC_APP_URL', 'http://localhost:3000').rstrip('/')}{path}"


def send_mail(email: str, subject: str, message_text: str) -> None:
    if os.getenv("AUTH_DEV_MODE") == "1":
        return
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM")
    if not host or not sender:
        raise HTTPException(503, "Email delivery is not configured.")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = email
    message.set_content(message_text)
    try:
        send_email(message)
    except (OSError, smtplib.SMTPException) as error:
        raise HTTPException(503, "Email could not be sent.") from error


def dev_link(name: str, url: str) -> dict:
    """On the local stack, which sends no email, the link travels in the answer instead."""
    return {name: url} if os.getenv("AUTH_DEV_MODE") == "1" else {}


# --- signing in -----------------------------------------------------------------------------------------------------

class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(max_length=1024)


def start_session(connection, response: Response, request: Request, user_id) -> None:
    token = identity.start_session(connection, user_id, request.headers.get("user-agent"))
    secure = os.getenv("COOKIE_SECURE") == "1" or request.url.scheme == "https"
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=secure,
                        samesite="lax", path="/", max_age=identity.SESSION_DAYS * 86400)


@router.post("/auth/login")
def login(body: Credentials, response: Response, request: Request, connection: Db):
    user = _call(identity.authenticate, connection, str(body.email), body.password)
    if not user:
        raise HTTPException(401, "Invalid email or password.")
    start_session(connection, response, request, user["id"])
    return {"message": "Signed in."}


def session_profile(request: Request, user: dict, connection: psycopg.Connection):
    memberships = connection.execute(
        """SELECT tenants.slug, tenants.name, memberships.role
           FROM memberships JOIN tenants ON tenants.id = memberships.tenant_id
           WHERE memberships.user_id = %s ORDER BY tenants.name""",
        (user["id"],),
    ).fetchall()
    return {
        "id": str(user["id"]), "name": user["name"], "email": user["email"],
        "is_platform_admin": user["is_platform_admin"],
        "memberships": memberships,
        "csrf_token": digest(f"{session_token(request)}:csrf"),
    }


@router.get("/auth/me")
def me(request: Request, user: User, connection: Db):
    return session_profile(request, user, connection)


@router.get("/auth/session")
def session(request: Request, connection: Db):
    try:
        user = session_user(request, connection)
    except HTTPException as error:
        if error.status_code == 401:
            return None
        raise
    return session_profile(request, user, connection)


@router.post("/auth/logout")
def logout(request: Request, response: Response, connection: Db):
    require_csrf(request)
    connection.execute(
        "UPDATE sessions SET revoked_at = now() WHERE token_hash = %s",
        (digest(session_token(request)),),
    )
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(LEGACY_SESSION_COOKIE, path="/")
    return {"message": "Signed out."}


# --- joining by invitation ------------------------------------------------------------------------------------------

@router.get("/auth/invitations/{token}")
def invitation(token: str, connection: Db):
    """What an invitation's link opens: the workspace, the address and role, and whether to sign in or sign up."""
    return _call(members.invitation, connection, token)


class Joining(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, max_length=1024)


@router.post("/auth/invitations/{token}/accept")
def accept(token: str, body: Joining, request: Request, response: Response, connection: Db):
    """Join the invitation's workspace: signed in, as the invited address; otherwise with a new account, which is
    signed in at once."""
    current = identity.session_user(connection, session_token(request))
    if current:
        require_csrf(request)
        joined = _call(members.accept, connection, token, user=current)
    else:
        joined = _call(members.accept, connection, token, name=body.name, password=body.password)
        start_session(connection, response, request, joined["id"])
    return {"message": "Workspace joined.", "workspace": joined["workspace"]}


# --- passwords ------------------------------------------------------------------------------------------------------

class ResetRequest(BaseModel):
    email: EmailStr


@router.post("/auth/password-reset", status_code=202)
def request_reset(body: ResetRequest, connection: Db):
    """Email a reset link to the account using this address. The answer is the same whether or not one does."""
    sent = identity.request_reset(connection, str(body.email))
    answer = {"message": "If an account uses this email, a link to reset its password is on its way."}
    if sent:
        url = link(f"/reset/{sent['token']}")
        send_mail(sent["user"]["email"], "Reset your Minkops password", (
            f"Someone asked to reset the password for {sent['user']['email']} on Minkops.\n\n"
            f"If it was you, open this link within the hour to choose a new password:\n{url}\n\n"
            "If it was not, ignore this email: your password stays as it is."))
        answer |= dev_link("reset_link", url)
    return answer


class Reset(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=1024)


@router.post("/auth/password-reset/confirm")
def reset(body: Reset, connection: Db):
    _call(identity.reset_password, connection, body.token, body.password)
    return {"message": "Password changed. Sign in with your new password."}


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)


@router.post("/auth/password")
def change_password(body: PasswordChange, request: Request, user: User, connection: Db):
    require_csrf(request)
    _call(identity.change_password, connection, user["id"], session_token(request),
          current=body.current_password, new=body.new_password)
    return {"message": "Password changed. Your other sessions are signed out."}


# --- profile and sessions -------------------------------------------------------------------------------------------

class Profile(BaseModel):
    name: str = Field(max_length=200)


@router.patch("/auth/me")
def rename(body: Profile, request: Request, user: User, connection: Db):
    require_csrf(request)
    _call(identity.rename, connection, user["id"], body.name)
    return session_profile(request, identity.session_user(connection, session_token(request)), connection)


@router.get("/auth/sessions")
def sessions(request: Request, user: User, connection: Db):
    return identity.sessions(connection, user["id"], session_token(request))


@router.delete("/auth/sessions/{session_id}")
def end_session(session_id: str, request: Request, user: User, connection: Db):
    require_csrf(request)
    _call(identity.end_session, connection, user["id"], session_id)
    return {"message": "Signed out there."}


@router.post("/auth/sessions/end-others")
def end_others(request: Request, user: User, connection: Db):
    require_csrf(request)
    ended = identity.end_other_sessions(connection, user["id"], session_token(request))
    return {"message": f"Signed out of {ended} other session{'s' if ended != 1 else ''}.", "ended": ended}
