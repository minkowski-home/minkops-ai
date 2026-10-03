"""FastAPI endpoints for the Minkops corporate website."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import os
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Literal

import aiosmtplib

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import JSONResponse

RECIPIENT = "info@minkops.com"
PUBLIC_SENDER = "info@minkops.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_TIMEOUT_SECONDS = 8
DELIVERY_DEDUPE_TTL_SECONDS = 24 * 60 * 60
DELIVERY_DEDUPE_MAX_ENTRIES = 20_000
EMAIL_PATTERN = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
INTEREST_VALUES = {
    "unsure",
    "email",
    "support",
    "sales",
    "marketing",
    "operations",
    "custom",
}


class InterestSubmission(BaseModel):
    """Validated visitor data. The honeypot is intentionally never emailed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    company: str = Field(default="", max_length=160)
    interest: str = Field(default="unsure", max_length=40)
    message: str = Field(default="", max_length=3000)
    website: str = Field(default="", max_length=200)
    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("interest")
    @classmethod
    def validate_interest(cls, value: str) -> str:
        if value not in INTEREST_VALUES:
            raise ValueError("Choose a listed workflow area")
        return value


class DeliveryError(Exception):
    """SMTP delivery could not be confirmed, with a conservative send outcome."""

    def __init__(self, message: str, *, ambiguous: bool = False) -> None:
        super().__init__(message)
        self.ambiguous = ambiguous


@dataclass(frozen=True)
class DeliveryRecord:
    state: Literal["accepted", "uncertain"]
    message_id: str
    created_at: float


class DeliveryGuard:
    """Suppress same-process retries when SMTP cannot supply idempotency keys.

    Accepted and uncertain attempts are retained for one day. This is a
    best-effort guard for a single process, not a cross-instance or durable
    exactly-once guarantee; Gmail SMTP does not provide one.
    """

    def __init__(self) -> None:
        self._records: dict[str, DeliveryRecord] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock_users: dict[str, int] = defaultdict(int)

    async def send(self, payload: InterestSubmission, key: str) -> str:
        lock = self._locks[key]
        self._lock_users[key] += 1
        try:
            async with lock:
                now = time.monotonic()
                record = self._records.get(key)
                if record and now - record.created_at < DELIVERY_DEDUPE_TTL_SECONDS:
                    if record.state == "accepted":
                        return record.message_id
                    raise DeliveryError(
                        "Email acceptance is uncertain; do not retry automatically.",
                        ambiguous=True,
                    )
                if record:
                    self._records.pop(key, None)

                self._prune(now)
                if len(self._records) >= DELIVERY_DEDUPE_MAX_ENTRIES:
                    raise DeliveryError("Email delivery is temporarily unavailable.")

                try:
                    message_id = await _send_with_workspace_smtp(payload)
                except asyncio.CancelledError:
                    self._records[key] = DeliveryRecord("uncertain", "", now)
                    raise
                except DeliveryError as exc:
                    if exc.ambiguous:
                        self._records[key] = DeliveryRecord("uncertain", "", now)
                    raise
                self._records[key] = DeliveryRecord("accepted", message_id, now)
                return message_id
        finally:
            self._lock_users[key] -= 1
            if self._lock_users[key] == 0:
                self._lock_users.pop(key, None)
                self._locks.pop(key, None)

    def _prune(self, now: float) -> None:
        expired = [
            key
            for key, record in self._records.items()
            if now - record.created_at >= DELIVERY_DEDUPE_TTL_SECONDS
        ]
        for key in expired:
            self._records.pop(key, None)
            if self._lock_users.get(key, 0) == 0:
                self._locks.pop(key, None)


@dataclass
class SlidingWindowLimiter:
    """Small per-process abuse guard; an edge/WAF limit is still needed at scale."""

    limit: int = 5
    window_seconds: int = 600
    max_clients: int = 10_000

    def __post_init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        if key not in self._attempts and len(self._attempts) >= self.max_clients:
            key = "__overflow__"
        attempts = self._attempts[key]
        while attempts and current - attempts[0] >= self.window_seconds:
            attempts.popleft()
        if len(attempts) >= self.limit:
            return False
        attempts.append(current)
        if len(self._attempts) > self.max_clients:
            stale_before = current - self.window_seconds
            for client, values in list(self._attempts.items()):
                while values and values[0] < stale_before:
                    values.popleft()
                if not values:
                    self._attempts.pop(client, None)
                if len(self._attempts) <= self.max_clients:
                    break
        return True


def _render_message(payload: InterestSubmission) -> tuple[str, str]:
    """Build equivalent plain-text and escaped HTML email bodies."""

    lines = [
        "A visitor submitted the Minkops discovery form.",
        "",
        f"Name: {payload.name}",
        f"Email: {payload.email}",
        f"Company: {payload.company or 'Not provided'}",
        f"Interested in: {payload.interest}",
        "",
        "Additional context:",
        payload.message or "Not provided",
    ]
    text_body = "\n".join(lines)
    html_body = "<br>\n".join(html.escape(line) for line in lines)
    return text_body, f"<div>{html_body}</div>"


async def _send_with_workspace_smtp(payload: InterestSubmission) -> str:
    """Send through the existing Google Workspace SMTP configuration."""

    host = os.getenv("SMTP_HOST", "").strip().lower()
    raw_port = os.getenv("SMTP_PORT", "").strip()
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip().lower()
    sender_name = os.getenv("SMTP_FROM_NAME", "").strip()
    if (
        host != SMTP_HOST
        or raw_port != str(SMTP_PORT)
        or not username
        or not password
        or sender != PUBLIC_SENDER
        or not sender_name
        or any(char in sender_name for char in "\r\n")
    ):
        raise DeliveryError("Email delivery is not configured")

    text_body, html_body = _render_message(payload)
    message_id = make_msgid(domain="minkops.com")
    message = EmailMessage()
    message["From"] = formataddr((sender_name, sender))
    message["To"] = RECIPIENT
    message["Reply-To"] = payload.email
    message["Subject"] = "New Minkops discovery request"
    message["Message-ID"] = message_id
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    try:
        await aiosmtplib.send(
            message,
            hostname=host,
            port=SMTP_PORT,
            start_tls=True,
            username=username,
            password=password,
            sender=sender,
            recipients=[RECIPIENT],
            timeout=SMTP_TIMEOUT_SECONDS,
        )
    except Exception:
        # Once transport begins, a disconnect may happen after SMTP accepted
        # DATA. Preserve an uncertain outcome rather than risking a blind retry.
        raise DeliveryError(
            "Email acceptance could not be confirmed.", ambiguous=True
        ) from None
    return message_id


async def send_interest_email(payload: InterestSubmission, idempotency_key: str) -> str:
    """Submit through the local duplicate guard and Workspace SMTP."""

    return await app.state.delivery_guard.send(payload, idempotency_key)


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://minkops.com",
        "https://www.minkops.com",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.state.interest_limiter = SlidingWindowLimiter()
app.state.delivery_guard = DeliveryGuard()


@app.middleware("http")
async def protect_interest_endpoint(request: Request, call_next):
    """Apply limits before body validation so invalid traffic cannot bypass them."""

    if request.url.path == "/api/interest" and request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > 16_384:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Submission is too large."},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid content length."},
                )
        client_key = request.client.host if request.client else "unknown"
        if not app.state.interest_limiter.allow(client_key):
            return JSONResponse(
                status_code=429,
                content={"detail": "Please wait a few minutes before trying again."},
            )
    return await call_next(request)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "corporate-website"}


@app.post("/api/interest", status_code=202)
async def submit_interest(payload: InterestSubmission) -> dict[str, str]:
    # A quiet success for a filled honeypot avoids teaching bots how to bypass it.
    if payload.website:
        return {"status": "accepted"}

    canonical = payload.model_dump(exclude={"website"}, mode="json")
    idempotency_key = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    try:
        await send_interest_email(payload, idempotency_key)
    except DeliveryError as exc:
        detail = (
            "We couldn't confirm whether your note was sent. Please don't submit it again; "
            "email info@minkops.com and we'll check."
            if exc.ambiguous
            else "We couldn't send your note yet. Please try again or email info@minkops.com."
        )
        raise HTTPException(status_code=503, detail=detail) from None
    return {"status": "accepted"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("minkops_corporate_website_api.main:app", host=host, port=port, reload=True)
