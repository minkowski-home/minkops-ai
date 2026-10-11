"""Internal, tenant-scoped evidence without raw provider or document payloads.

Use a separate short transaction: diagnostic writes must neither commit business
work early nor disappear when validation rolls it back. A diagnostics outage
cannot turn an already applied business operation into a reported failure.
"""

import logging
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

import psycopg
from jsonschema import ValidationError
from psycopg.types.json import Jsonb

log = logging.getLogger(__name__)


def record(connection, run, kind, summary, *, level="info", details=None):
    try:
        with psycopg.connect(
            connection.info.dsn, password=connection.info.password, connect_timeout=5
        ) as audit:
            audit.execute("SET LOCAL statement_timeout = '5s'")
            audit.execute("SET LOCAL lock_timeout = '1s'")
            audit.execute(
                """INSERT INTO workflow_run_diagnostics
                   (tenant_id,run_id,event_type,level,summary,details)
                   VALUES(%s,%s,%s,%s,%s,%s)""",
                (run["tenant_id"], run["id"], kind, level, summary, Jsonb(details or {})),
            )
    except psycopg.Error as error:
        log.error(
            "Internal diagnostic unavailable for run %s (%s)", run["id"], type(error).__name__
        )


def error_details(error):
    details = {"error_type": type(error).__name__}
    if isinstance(error, ValidationError):
        # str(ValidationError) embeds the entire instance and schema. The rule
        # and exact path explain the rejection without leaking those payloads.
        details.update(path=list(error.absolute_path), validator=error.validator)
        details["explanation"] = f"Output violates schema rule {error.validator} at " + ".".join(
            map(str, error.absolute_path)
        )
    if getattr(error, "status_code", None) is not None:
        details["http_status"] = error.status_code
    if getattr(error, "sqlstate", None):
        details["sqlstate"] = error.sqlstate
    details["frames"] = [
        {"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
        for frame in traceback.extract_tb(error.__traceback__)[-12:]
    ]
    return details


@contextmanager
def stage(connection, run, name, summary, *, details=None):
    started = time.monotonic()
    record(connection, run, name + ".started", summary, details=details)
    try:
        yield
    except Exception as error:
        record(
            connection,
            run,
            name + ".failed",
            f"{summary} failed ({type(error).__name__}).",
            level="error",
            details={
                **error_details(error),
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            },
        )
        raise
    else:
        record(
            connection,
            run,
            name + ".completed",
            summary + " completed.",
            details={"elapsed_ms": round((time.monotonic() - started) * 1000)},
        )
