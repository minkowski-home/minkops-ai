"""Best-effort duplicate control and delivery orchestration for website inquiries."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Literal

from minkops_connectors.workspace_smtp import (
    SmtpRejected,
    SmtpSetupFailure,
    SmtpConfigurationError,
    SmtpOutcomeUncertain,
    send_discovery_notification,
)

DELIVERY_DEDUPE_TTL_SECONDS = 24 * 60 * 60
DELIVERY_DEDUPE_MAX_ENTRIES = 20_000


@dataclass(frozen=True)
class InterestSubmission:
    name: str
    email: str
    company: str
    interest: str
    message: str


class DeliveryError(Exception):
    """Delivery could not be confirmed, with a conservative send outcome."""

    def __init__(self, message: str, *, ambiguous: bool = False) -> None:
        super().__init__(message)
        self.ambiguous = ambiguous


@dataclass(frozen=True)
class DeliveryRecord:
    state: Literal["accepted", "uncertain"]
    message_id: str
    created_at: float


class DeliveryGuard:
    """Suppress retries within one process; no durable idempotency is implied."""

    def __init__(self) -> None:
        self._records: dict[str, DeliveryRecord] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock_users: dict[str, int] = defaultdict(int)

    async def send(self, submission: InterestSubmission, key: str) -> None:
        lock = self._locks[key]
        self._lock_users[key] += 1
        try:
            async with lock:
                now = time.monotonic()
                record = self._records.get(key)
                if record and now - record.created_at < DELIVERY_DEDUPE_TTL_SECONDS:
                    if record.state == "accepted":
                        return
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
                    message_id = await send_discovery_notification(**asdict(submission))
                except SmtpConfigurationError:
                    raise DeliveryError("Email delivery is not configured") from None
                except (SmtpSetupFailure, SmtpRejected):
                    raise DeliveryError("Email delivery was rejected before acceptance") from None
                except SmtpOutcomeUncertain:
                    self._records[key] = DeliveryRecord("uncertain", "", now)
                    raise DeliveryError(
                        "Email acceptance could not be confirmed.", ambiguous=True
                    ) from None
                except asyncio.CancelledError:
                    self._records[key] = DeliveryRecord("uncertain", "", now)
                    raise

                self._records[key] = DeliveryRecord("accepted", message_id, now)
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


_delivery_guard = DeliveryGuard()


async def deliver_interest(submission: InterestSubmission) -> None:
    """Validate-free app operation: dedupe and delegate the notification."""

    canonical = json.dumps(asdict(submission), sort_keys=True, separators=(",", ":"))
    key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    await _delivery_guard.send(submission, key)
