"""Small first-party auth layer: verified email, server sessions, tenant membership."""

import hashlib
import os
import re
import secrets
import smtplib
from email.message import EmailMessage
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from psycopg.rows import dict_row
from pwdlib import PasswordHash
from minkops_connectors.email import send_email


router = APIRouter(prefix="/api")
passwords = PasswordHash.recommended()
# Firebase Hosting forwards only this cookie to Cloud Run. Its value remains
# our opaque PostgreSQL session token; Google does not own user authentication.
SESSION_COOKIE = "__session"
LEGACY_SESSION_COOKIE = "minkops_session"


def session_token(request: Request) -> str:
    return request.cookies.get(SESSION_COOKIE) or request.cookies.get(LEGACY_SESSION_COOKIE, "")


def database():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise HTTPException(503, "Database is not configured.")
    with psycopg.connect(url, row_factory=dict_row) as connection:
        yield connection


# Commit before a response-triggered wake-up reads the durable notification.
Db = Annotated[psycopg.Connection, Depends(database, scope="function")]


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_user(request: Request, connection: Db) -> dict:
    token = session_token(request)
    if not token:
        raise HTTPException(401, "Sign in required.")
    row = connection.execute(
        """SELECT users.id, users.name, users.email, users.is_platform_admin
           FROM sessions JOIN users ON users.id = sessions.user_id
           WHERE sessions.token_hash = %s AND sessions.expires_at > now()
             AND sessions.revoked_at IS NULL AND users.email_verified_at IS NOT NULL""",
        (digest(token),),
    ).fetchone()
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


class Signup(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)
    organization_name: str | None = Field(default=None, min_length=2, max_length=120)


class Credentials(BaseModel):
    email: EmailStr
    password: str


class TokenInput(BaseModel):
    token: str


def verification_link(token: str) -> str:
    base = os.getenv("PUBLIC_APP_URL", "http://localhost:3000").rstrip("/")
    return f"{base}/verify/{token}"


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


def send_verification(email: str, link: str) -> None:
    send_mail(email, "Verify your Minkops account",
              f"Open this link to verify your email: {link}")


@router.post("/auth/signup", status_code=201)
def signup(body: Signup, connection: Db):
    email = str(body.email).strip().lower()
    if connection.execute("SELECT 1 FROM users WHERE lower(email) = %s", (email,)).fetchone():
        raise HTTPException(409, "Account already exists.")
    domain = email.rsplit("@", 1)[1]
    suggestion = connection.execute(
        """SELECT tenants.slug, tenants.name FROM tenant_domains
           JOIN tenants ON tenants.id = tenant_domains.tenant_id
           WHERE tenant_domains.domain = %s AND verified_at IS NOT NULL""",
        (domain,),
    ).fetchone()
    token = secrets.token_urlsafe(32)
    link = verification_link(token)
    send_verification(email, link)
    user_id = connection.execute(
        "INSERT INTO users (email, name, password_hash) VALUES (%s, %s, %s) RETURNING id",
        (email, body.name.strip(), passwords.hash(body.password)),
    ).fetchone()["id"]
    connection.execute(
        "INSERT INTO email_verifications (user_id, token_hash, expires_at) VALUES (%s, %s, now() + interval '24 hours')",
        (user_id, digest(token)),
    )
    if body.organization_name:
        base = re.sub(r"[^a-z0-9]+", "-", body.organization_name.lower()).strip("-")[:36]
        slug = f"{base}-{secrets.token_hex(3)}"
        tenant_id = connection.execute(
            "INSERT INTO tenants (slug, name) VALUES (%s, %s) RETURNING id",
            (slug, body.organization_name.strip()),
        ).fetchone()["id"]
        connection.execute(
            "INSERT INTO memberships (tenant_id, user_id, role) VALUES (%s, %s, 'admin')",
            (tenant_id, user_id),
        )
    result = {"message": "Check your email to verify your account.", "suggested_tenant": suggestion}
    if os.getenv("AUTH_DEV_MODE") == "1":
        result["verification_link"] = link
    return result


@router.post("/auth/verify")
def verify(body: TokenInput, connection: Db):
    row = connection.execute(
        "SELECT user_id FROM email_verifications WHERE token_hash = %s AND expires_at > now()",
        (digest(body.token),),
    ).fetchone()
    if not row:
        raise HTTPException(400, "Verification link is invalid or expired.")
    connection.execute("UPDATE users SET email_verified_at = now() WHERE id = %s", (row["user_id"],))
    connection.execute("DELETE FROM email_verifications WHERE user_id = %s", (row["user_id"],))
    return {"message": "Email verified. You can sign in."}


@router.post("/auth/login")
def login(body: Credentials, response: Response, request: Request, connection: Db):
    user = connection.execute(
        "SELECT id, password_hash, email_verified_at FROM users WHERE lower(email) = %s",
        (str(body.email).lower(),),
    ).fetchone()
    if not user or not passwords.verify(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password.")
    if not user["email_verified_at"]:
        raise HTTPException(403, "Verify your email before signing in.")
    token = secrets.token_urlsafe(32)
    connection.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (%s, %s, now() + interval '7 days')",
        (user["id"], digest(token)),
    )
    secure = os.getenv("COOKIE_SECURE") == "1" or request.url.scheme == "https"
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=secure,
                        samesite="lax", path="/", max_age=7 * 86400)
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


@router.post("/tenants/{slug}/join-requests", status_code=201)
def request_membership(slug: str, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant = connection.execute("SELECT id FROM tenants WHERE slug = %s", (slug,)).fetchone()
    if not tenant:
        raise HTTPException(404, "Workspace not found.")
    if connection.execute(
        "SELECT 1 FROM memberships WHERE tenant_id = %s AND user_id = %s",
        (tenant["id"], user["id"]),
    ).fetchone():
        raise HTTPException(409, "Already a member.")
    connection.execute(
        """INSERT INTO join_requests (tenant_id, user_id, status)
           VALUES (%s, %s, 'pending') ON CONFLICT (tenant_id, user_id)
           DO UPDATE SET status = 'pending', resolved_at = NULL""",
        (tenant["id"], user["id"]),
    )
    return {"message": "Request sent to workspace admins."}


@router.get("/tenants/{slug}/join-requests")
def list_join_requests(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection, edit=True)
    rows = connection.execute(
        """SELECT join_requests.id, users.name, users.email, join_requests.created_at
           FROM join_requests JOIN users ON users.id = join_requests.user_id
           WHERE join_requests.tenant_id = %s AND join_requests.status = 'pending'
           ORDER BY join_requests.created_at""",
        (tenant["id"],),
    ).fetchall()
    return rows


@router.post("/tenants/{slug}/join-requests/{request_id}/approve")
def approve_join_request(slug: str, request_id: str, request: Request,
                         user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection, edit=True)
    row = connection.execute(
        """UPDATE join_requests SET status = 'approved', resolved_at = now()
           WHERE id = %s AND tenant_id = %s AND status = 'pending'
           RETURNING user_id""",
        (request_id, tenant["id"]),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Pending request not found.")
    connection.execute(
        """INSERT INTO memberships (tenant_id, user_id, role) VALUES (%s, %s, 'member')
           ON CONFLICT (tenant_id, user_id) DO NOTHING""",
        (tenant["id"], row["user_id"]),
    )
    return {"message": "Membership approved."}


class InvitationInput(BaseModel):
    email: EmailStr
    role: str = "member"


@router.post("/tenants/{slug}/invitations", status_code=201)
def invite(slug: str, body: InvitationInput, request: Request,
           user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection, edit=True)
    if body.role not in ("admin", "member"):
        raise HTTPException(422, "Invalid role.")
    token = secrets.token_urlsafe(32)
    link = f"{os.getenv('PUBLIC_APP_URL', 'http://localhost:3000').rstrip('/')}/invite/{token}"
    send_mail(str(body.email), f"Join {tenant['name']} on Minkops",
              f"Open this link to join the workspace: {link}")
    connection.execute(
        """INSERT INTO invitations (tenant_id, email, role, token_hash, expires_at, invited_by)
           VALUES (%s, %s, %s, %s, now() + interval '7 days', %s)""",
        (tenant["id"], str(body.email).lower(), body.role, digest(token), user["id"]),
    )
    result = {"message": "Invitation sent."}
    if os.getenv("AUTH_DEV_MODE") == "1":
        result["invitation_link"] = link
    return result


@router.post("/auth/accept-invite")
def accept_invite(body: TokenInput, request: Request, user: User, connection: Db):
    require_csrf(request)
    row = connection.execute(
        """SELECT id, tenant_id, email, role FROM invitations
           WHERE token_hash = %s AND expires_at > now() AND accepted_at IS NULL
           FOR UPDATE""",
        (digest(body.token),),
    ).fetchone()
    if not row or row["email"] != user["email"].lower():
        raise HTTPException(400, "Invitation is invalid or belongs to another account.")
    connection.execute(
        """INSERT INTO memberships (tenant_id, user_id, role) VALUES (%s, %s, %s)
           ON CONFLICT (tenant_id, user_id) DO UPDATE SET role = EXCLUDED.role""",
        (row["tenant_id"], user["id"], row["role"]),
    )
    connection.execute("UPDATE invitations SET accepted_at = now() WHERE id = %s", (row["id"],))
    return {"message": "Workspace joined."}
