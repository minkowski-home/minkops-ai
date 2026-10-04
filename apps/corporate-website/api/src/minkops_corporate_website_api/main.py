"""HTTP transport for the Minkops corporate website."""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from minkops_platform.interest_delivery import (
    DeliveryError,
    InterestSubmission,
    deliver_interest,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import JSONResponse

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


class InterestRequest(BaseModel):
    """Validated form data. The honeypot is intentionally not delivered."""

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
async def submit_interest(payload: InterestRequest) -> dict[str, str]:
    # A quiet success for a filled honeypot avoids teaching bots how to bypass it.
    if payload.website:
        return {"status": "accepted"}

    try:
        await deliver_interest(
            InterestSubmission(
                name=payload.name,
                email=payload.email,
                company=payload.company,
                interest=payload.interest,
                message=payload.message,
            )
        )
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
    uvicorn.run("minkops_corporate_website_api.main:app", host=host, port=port)
