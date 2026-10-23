"""People's accounts: passwords, sessions, password resets and profile (docs/workspace-access.md).

An account is created only when its invitation is accepted (`members.accept`). The link reached the address, so
every account's email is verified. A session is an opaque token whose hash alone is stored; the entry point carries
the token in a cookie. Ending sessions never stops a PC: companions authenticate with their own device tokens.
"""

import hashlib
import re
import secrets

from pwdlib import PasswordHash

from .errors import ServiceError

passwords = PasswordHash.recommended()
SESSION_DAYS = 7
# A reset link lives an hour; an account is sent at most three an hour, so a stranger cannot flood its inbox.
RESET_MINUTES, RESETS_PER_HOUR = 60, 3
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# Verified against when no account matches, so an unknown address takes as long as a wrong password.
_NOBODY = passwords.hash(secrets.token_urlsafe(16))


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _name(value):
    name = " ".join(str(value or "").split())
    if not 2 <= len(name) <= 120 or CONTROL.search(name):
        raise ServiceError("invalid", "A name is 2 to 120 characters.")
    return name


def _password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 1024:
        raise ServiceError("invalid", "A password is 12 to 1,024 characters.")
    return passwords.hash(value)


def create_account(connection, *, email, name, password):
    """A verified account: only an invitation accepted from its own inbox creates one."""
    email = str(email).strip().lower()
    row = connection.execute(
        """INSERT INTO users(email,name,password_hash,email_verified_at)
           SELECT %s,%s,%s,now() WHERE NOT EXISTS (SELECT 1 FROM users WHERE lower(email)=%s)
           RETURNING id,name,email,is_platform_admin""",
        (email, _name(name), _password(password), email)).fetchone()
    if row is None:
        raise ServiceError("conflict", f"{email} already has an account.")
    return row


def authenticate(connection, email, password):
    """The account this email and password open, or None. An account not yet verified is refused only once its
    password is right, so the refusal reveals nothing to someone without it."""
    row = connection.execute(
        """SELECT id,name,email,is_platform_admin,password_hash,email_verified_at FROM users
           WHERE lower(email)=lower(%s)""", (str(email).strip(),)).fetchone()
    if not passwords.verify(password, row["password_hash"] if row else _NOBODY) or row is None:
        return None
    if not row["email_verified_at"]:
        raise ServiceError("forbidden", "This email is not verified yet. Reset your password to verify it.")
    return {key: row[key] for key in ("id", "name", "email", "is_platform_admin")}


def start_session(connection, user_id, user_agent):
    token = secrets.token_urlsafe(32)
    connection.execute(
        """INSERT INTO sessions(user_id,token_hash,expires_at,user_agent,last_seen_at)
           VALUES (%s,%s,now() + make_interval(days => %s),%s,now())""",
        (user_id, digest(token), SESSION_DAYS, (CONTROL.sub("", user_agent or "")[:300] or None)))
    return token


def session_user(connection, token):
    """The verified account a live session belongs to, or None. Its last use is noted at most every five minutes,
    never waiting on another request of the same session."""
    if not token:
        return None
    row = connection.execute(
        """SELECT s.id AS session_id, u.id, u.name, u.email, u.is_platform_admin
           FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token_hash=%s AND s.expires_at > now() AND s.revoked_at IS NULL
             AND u.email_verified_at IS NOT NULL""", (digest(token),)).fetchone()
    if row:
        connection.execute(
            """UPDATE sessions SET last_seen_at=now() WHERE id = (
                   SELECT id FROM sessions WHERE id=%s AND (last_seen_at IS NULL OR last_seen_at < now() - interval '5 minutes')
                   FOR UPDATE SKIP LOCKED)""", (row["session_id"],))
    return row


def sessions(connection, user_id, current_token):
    """A person's live sessions: this browser first, then the most recently used."""
    return connection.execute(
        """SELECT id, user_agent, created_at, coalesce(last_seen_at, created_at) AS last_seen_at,
                  token_hash = %s AS current
           FROM sessions WHERE user_id=%s AND revoked_at IS NULL AND expires_at > now()
           ORDER BY token_hash = %s DESC, coalesce(last_seen_at, created_at) DESC, created_at DESC, id""",
        (digest(current_token or ""), user_id, digest(current_token or ""))).fetchall()


def end_session(connection, user_id, session_id):
    if connection.execute("""UPDATE sessions SET revoked_at=now()
                             WHERE id=%s AND user_id=%s AND revoked_at IS NULL RETURNING id""",
                          (session_id, user_id)).fetchone() is None:
        raise ServiceError("not_found", "That session has already ended.")


def end_other_sessions(connection, user_id, current_token):
    return connection.execute("""UPDATE sessions SET revoked_at=now()
                                 WHERE user_id=%s AND revoked_at IS NULL AND token_hash <> %s""",
                              (user_id, digest(current_token or ""))).rowcount


def end_sessions(connection, user_id):
    return connection.execute("UPDATE sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL",
                              (user_id,)).rowcount


def rename(connection, user_id, name):
    return connection.execute("UPDATE users SET name=%s WHERE id=%s RETURNING id,name,email",
                              (_name(name), user_id)).fetchone()


def change_password(connection, user_id, current_token, *, current, new):
    """A new password, given the current one; every other session ends, this one stays."""
    row = connection.execute("SELECT password_hash FROM users WHERE id=%s FOR UPDATE", (user_id,)).fetchone()
    if not passwords.verify(current, row["password_hash"]):
        raise ServiceError("invalid", "The current password is not right.")
    connection.execute("UPDATE users SET password_hash=%s WHERE id=%s", (_password(new), user_id))
    end_other_sessions(connection, user_id, current_token)


def request_reset(connection, email):
    """A reset link's token for the account with this email, or None: for an unknown address, or one sent its
    three links this hour. The caller answers the same either way."""
    row = connection.execute("SELECT id,name,email FROM users WHERE lower(email)=lower(%s) FOR UPDATE",
                             (str(email).strip(),)).fetchone()
    if row is None or connection.execute(
            "SELECT count(*) AS n FROM password_resets WHERE user_id=%s AND created_at > now() - interval '1 hour'",
            (row["id"],)).fetchone()["n"] >= RESETS_PER_HOUR:
        return None
    token = secrets.token_urlsafe(32)
    connection.execute("""INSERT INTO password_resets(user_id,token_hash,expires_at)
                          VALUES (%s,%s,now() + make_interval(mins => %s))""", (row["id"], digest(token), RESET_MINUTES))
    return {"user": row, "token": token}


def reset_password(connection, token, password):
    """Set a new password from a reset link. The link reached the inbox, so the email is verified; every session
    ends, and so does every other link sent before."""
    row = connection.execute(
        """SELECT user_id FROM password_resets WHERE token_hash=%s AND used_at IS NULL AND expires_at > now()
           FOR UPDATE""", (digest(token or ""),)).fetchone()
    if row is None:
        raise ServiceError("not_found", "This reset link is invalid, used or expired. Ask for a new one.")
    connection.execute("UPDATE users SET password_hash=%s, email_verified_at=coalesce(email_verified_at, now()) "
                       "WHERE id=%s", (_password(password), row["user_id"]))
    connection.execute("UPDATE password_resets SET used_at=now() WHERE user_id=%s AND used_at IS NULL",
                       (row["user_id"],))
    end_sessions(connection, row["user_id"])
    return row["user_id"]
