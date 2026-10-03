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
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import JSONResponse

RECIPIENT = "info@minkops.com"
RESEND_ENDPOINT = "https://api.resend.com/emails"
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
    """Provider not configured or unable to accept the submission."""


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


def _send_with_resend(
    payload: InterestSubmission,
    idempotency_key: str,
    *,
    opener: Callable[..., object] = urlopen,
) -> str:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("RESEND_FROM_EMAIL", "").strip()
    if not api_key or not sender:
        raise DeliveryError("Email delivery is not configured")
    if "\r" in sender or "\n" in sender:
        raise DeliveryError("Email delivery is not configured")

    text_body, html_body = _render_message(payload)
    request_body = json.dumps(
        {
            "from": sender,
            "to": [RECIPIENT],
            "reply_to": payload.email,
            "subject": "New Minkops discovery request",
            "text": text_body,
            "html": html_body,
        }
    ).encode("utf-8")
    request = UrlRequest(
        RESEND_ENDPOINT,
        data=request_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        },
        method="POST",
    )
    try:
        with opener(request, timeout=8) as response:  # type: ignore[attr-defined]
            status = getattr(response, "status", 200)
            response_data = json.loads(response.read().decode("utf-8"))  # type: ignore[attr-defined]
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise DeliveryError("Email delivery was not accepted") from exc

    if status < 200 or status >= 300 or not isinstance(response_data, dict):
        raise DeliveryError("Email delivery was not accepted")
    message_id = response_data.get("id")
    if not isinstance(message_id, str) or not message_id:
        raise DeliveryError("Email delivery was not accepted")
    return message_id


async def send_interest_email(payload: InterestSubmission, idempotency_key: str) -> str:
    """Send with provider idempotency so browser retries cannot fan out duplicates."""

    return await asyncio.to_thread(_send_with_resend, payload, idempotency_key)


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
        message_id = await send_interest_email(payload, idempotency_key)
    except DeliveryError as exc:
        raise HTTPException(
            status_code=503,
            detail="We couldn't send your note yet. Please try again or email info@minkops.com.",
        ) from exc
    return {"status": "accepted", "message_id": message_id}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("minkops_corporate_website_api.main:app", host=host, port=port, reload=True)
