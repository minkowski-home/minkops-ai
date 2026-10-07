"""Server-owned desktop dispatch. No shell, raw XML or arbitrary URL authority.

The companion keeps execution local; the existing tasks/event/outbox contract
keeps observations visible to every client. Only reads are automatically
reclaimable. Workbook saves reuse Accounts approval and byte verification;
an interrupted save requires an explicit request and native hash recovery.
"""

import base64
import binascii
import hashlib
import json
import secrets
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .accounts import service as accounts
from .errors import ServiceError
from .run_controls import observe_task, resolve_request


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def public_device(row):
    return {
        key: row[key]
        for key in (
            "id",
            "name",
            "installation_id",
            "owner_id",
            "last_seen_at",
            "expires_at",
            "revoked_at",
        )
    }


def register(connection, tenant, user, name, installation_id):
    credential = secrets.token_urlsafe(48)
    row = connection.execute(
        """INSERT INTO desktop_devices(tenant_id,owner_id,name,installation_id,token_hash)
           VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,owner_id,installation_id)
           DO UPDATE SET name=EXCLUDED.name,token_hash=EXCLUDED.token_hash,
             expires_at=now()+interval '90 days',revoked_at=NULL RETURNING *""",
        (tenant["id"], user["id"], name.strip(), installation_id, _hash(credential)),
    ).fetchone()
    return {**public_device(row), "credential": credential}


def authenticate(connection, credential):
    row = connection.execute(
        """SELECT d.*, t.slug, u.is_platform_admin FROM desktop_devices d
           JOIN tenants t ON t.id=d.tenant_id JOIN users u ON u.id=d.owner_id
           WHERE d.token_hash=%s AND d.revoked_at IS NULL AND d.expires_at>now()
           AND u.email_verified_at IS NOT NULL AND (u.is_platform_admin OR EXISTS
             (SELECT 1 FROM memberships m WHERE m.tenant_id=d.tenant_id AND m.user_id=d.owner_id))
           FOR UPDATE OF d""",
        (_hash(credential),),
    ).fetchone()
    if not row:
        raise ServiceError("unauthorized", "Reconnect this PC from Minkops.")
    return row


def devices(connection, tenant):
    return [
        public_device(row)
        for row in connection.execute(
            "SELECT * FROM desktop_devices WHERE tenant_id=%s ORDER BY created_at", (tenant["id"],)
        ).fetchall()
    ]


def owned_device(connection, tenant_id, user_id, device_id, *, active=True):
    row = connection.execute(
        "SELECT * FROM desktop_devices WHERE tenant_id=%s AND owner_id=%s AND id=%s FOR UPDATE",
        (tenant_id, user_id, device_id),
    ).fetchone()
    if not row:
        raise ServiceError("not_found", "PC not found for this account.")
    if active and (
        row["revoked_at"]
        or row["expires_at"] <= connection.execute("SELECT now() AS time").fetchone()["time"]
    ):
        raise ServiceError("conflict", "Reconnect this PC before starting work.")
    return row


def revoke(connection, tenant, user, device_id):
    owned_device(connection, tenant["id"], user["id"], device_id, active=False)
    connection.execute("UPDATE desktop_devices SET revoked_at=now() WHERE id=%s", (device_id,))
    pending = connection.execute(
        """UPDATE desktop_jobs SET state='failed',error='This PC was disconnected.',updated_at=now()
           WHERE device_id=%s AND state IN ('queued','executing') RETURNING *""",
        (device_id,),
    ).fetchall()
    for job in pending:
        _observe(
            connection,
            job,
            "failed",
            "This PC was disconnected. Reconnect it to start a new task.",
            0,
        )
    return {"message": "PC disconnected."}


def public_job(row):
    return {
        key: row[key]
        for key in (
            "id",
            "device_id",
            "task_id",
            "operation",
            "state",
            "result",
            "error",
            "created_at",
            "updated_at",
        )
    }


def enqueue_approved(connection, run, device_id, operation, write_id):
    """Persist approved work before returning to the UI, so tray work survives
    closing either client. Only the domain calls this with an immutable intent."""
    owned_device(connection, run["tenant_id"], run["actor_id"], device_id)
    payload = {"run_id": str(run["id"]), "write_id": str(write_id)}
    connection.execute(
        """INSERT INTO desktop_jobs
        (tenant_id,device_id,actor_id,task_id,operation,input,request_key,request_hash)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            run["tenant_id"],
            device_id,
            run["actor_id"],
            run["task_id"],
            operation,
            Jsonb(payload),
            uuid4(),
            _hash(json.dumps(payload, sort_keys=True)),
        ),
    )


def _observe(connection, job, state, summary, progress):
    if job["operation"] == "tally.references":
        from .runtime.store import WorkflowRunStore, run_for

        run = run_for(connection, job["tenant_id"], job["input"]["run_id"])
        if run["state"] != "queued":
            return
        store = WorkflowRunStore()
        if state == "failed":
            store.fail(connection, run, summary)
        else:
            store.observe(
                connection,
                run,
                "queued",
                "Preparing current Tally references on the connected PC."
                if state == "executing"
                else summary,
                15,
            )
        return
    if job["operation"] == "sources.discover":
        # Discovery owns collection -> hosted mapping -> confirmation lifecycle.
        if state in ("queued", "executing"):
            from . import discovery

            row = discovery.get_run(connection, job["tenant_id"], job["input"]["discovery_run_id"])
            discovery._observe(
                connection,
                row,
                state,
                "Waiting for your PC."
                if state == "queued"
                else "Reading your selected business sources…",
                progress,
            )
        elif state == "failed":
            from . import discovery

            row = discovery.get_run(connection, job["tenant_id"], job["input"]["discovery_run_id"])
            if row["state"] != "failed":
                discovery.fail(connection, {"tenant_id": job["tenant_id"]}, job, summary)
        return
    # Accounts owns its run's lifecycle. A single workbook receipt must not
    # complete a multi-workbook run or turn a cancellation back into success.
    if job["operation"] in ("accounts.save", "tally.save"):
        run = connection.execute(
            "SELECT state FROM account_runs WHERE tenant_id=%s AND id=%s FOR UPDATE",
            (job["tenant_id"], job["input"]["run_id"]),
        ).fetchone()
        if run["state"] != "writing":
            return
        event = {
            "queued": "local_waiting",
            "executing": "local_saving",
            "completed": "local_verified",
            "failed": "local_failed",
        }[state]
        table = "account_tally_writes" if job["operation"] == "tally.save" else "account_writes"
        count = connection.execute(
            f"SELECT count(*) AS total,count(verified_at) AS saved FROM {table} WHERE tenant_id=%s AND run_id=%s",
            (job["tenant_id"], job["input"]["run_id"]),
        ).fetchone()
        summary = {
            "queued": summary,
            "executing": "Saving and checking approved bill entries…",
            "completed": f"{count['saved']} of {count['total']} destination writes checked.",
            "failed": summary,
        }[state]
        connection.execute(
            "UPDATE tasks SET summary=%s,updated_at=now() WHERE tenant_id=%s AND id=%s",
            (summary, job["tenant_id"], job["task_id"]),
        )
        connection.execute(
            "INSERT INTO task_events(tenant_id,task_id,event_type,summary,progress) VALUES (%s,%s,%s,%s,85)",
            (job["tenant_id"], job["task_id"], event, summary),
        )
        connection.execute(
            "INSERT INTO event_outbox(tenant_id,event_type,aggregate_id,payload) VALUES (%s,%s,%s,%s)",
            (
                job["tenant_id"],
                "desktop." + event,
                job["id"],
                Jsonb({"task_id": str(job["task_id"]), "summary": summary}),
            ),
        )
        return
    observe_task(
        connection,
        tenant_id=job["tenant_id"],
        task_id=job["task_id"],
        run_id=job["id"],
        state=state,
        summary=summary,
        progress=progress,
        event_prefix="desktop",
    )


def bindings(connection, tenant, user):
    return connection.execute(
        """SELECT b.source_id,b.device_id,d.name,d.last_seen_at FROM desktop_source_bindings b
        JOIN desktop_devices d ON d.tenant_id=b.tenant_id AND d.id=b.device_id
        WHERE b.tenant_id=%s AND d.owner_id=%s AND d.revoked_at IS NULL AND d.expires_at>now()""",
        (tenant["id"], user["id"]),
    ).fetchall()


def bind_source(connection, tenant, user, device_id, source_id):
    owned_device(connection, tenant["id"], user["id"], device_id)
    source = connection.execute(
        "SELECT * FROM account_sources WHERE tenant_id=%s AND id=%s FOR UPDATE",
        (tenant["id"], source_id),
    ).fetchone()
    if not source or source["actor_id"] != user["id"] or not source["writable"]:
        raise ServiceError("not_found", "Your writable source was not found.")
    connection.execute(
        """INSERT INTO desktop_source_bindings(tenant_id,device_id,source_id) VALUES (%s,%s,%s)
        ON CONFLICT (tenant_id,source_id) DO UPDATE SET device_id=EXCLUDED.device_id""",
        (tenant["id"], device_id, source_id),
    )
    return {"source_id": source_id, "device_id": device_id}


def _bound_source(connection, device, source_id):
    source = connection.execute(
        """SELECT s.* FROM account_sources s JOIN desktop_source_bindings b
        ON b.tenant_id=s.tenant_id AND b.source_id=s.id WHERE b.tenant_id=%s
        AND b.device_id=%s AND b.source_id=%s AND s.actor_id=%s AND s.writable""",
        (device["tenant_id"], device["id"], source_id, device["owner_id"]),
    ).fetchone()
    if not source:
        raise ServiceError("not_found", "Reconnect the original folder in the desktop app.")
    return source


def _save_spec(connection, device, payload, *, pending=True):
    run = connection.execute(
        "SELECT * FROM account_runs WHERE tenant_id=%s AND id=%s FOR UPDATE",
        (device["tenant_id"], payload["run_id"]),
    ).fetchone()
    if not run or run["actor_id"] != device["owner_id"]:
        raise ServiceError("not_found", "Approved run not found for this account.")
    spec = connection.execute(
        "SELECT * FROM account_writes WHERE tenant_id=%s AND run_id=%s AND id=%s FOR UPDATE",
        (device["tenant_id"], payload["run_id"], payload["write_id"]),
    ).fetchone()
    if not spec:
        raise ServiceError("not_found", "Approved save not found.")
    _bound_source(connection, device, spec["source_id"])
    if pending and (run["state"] != "writing" or spec["cancelled_at"] or spec["verified_at"]):
        raise ServiceError("conflict", "This save is no longer pending approval.")
    return run, spec


def _validate_input(operation, payload):
    keys = {
        "tally.probe": set(),
        "files.refresh": {"source_id"},
        "accounts.save": {"run_id", "write_id"},
        "tally.save": {"run_id", "write_id"},
    }
    if operation not in keys or set(payload) != keys[operation]:
        raise ServiceError("invalid", "This local operation is not supported.")
    try:
        for value in payload.values():
            UUID(value)
    except (TypeError, ValueError, AttributeError) as error:
        raise ServiceError("invalid", "Invalid local resource.") from error


def launch(connection, tenant, user, body):
    operation, payload = body["operation"], body["input"]
    _validate_input(operation, payload)
    device = owned_device(connection, tenant["id"], user["id"], body["device_id"])
    fingerprint, previous = resolve_request(
        connection,
        tenant["id"],
        body["request_key"],
        body,
        _request_job,
    )
    if previous:
        return public_job(previous)
    run = None
    if operation == "files.refresh":
        _bound_source(connection, device, payload["source_id"])
    elif operation == "accounts.save":
        run, _ = _save_spec(connection, device, payload)
    elif operation == "tally.save":
        from .accounts.tally_writes import spec

        run, _ = spec(connection, device, payload)
    if operation != "tally.probe":
        existing = connection.execute(
            """SELECT * FROM desktop_jobs WHERE device_id=%s AND operation=%s AND input=%s
            AND state IN ('queued','executing') ORDER BY created_at DESC LIMIT 1 FOR UPDATE""",
            (device["id"], operation, Jsonb(payload)),
        ).fetchone()
        if existing:
            if (
                operation not in ("accounts.save", "tally.save")
                or existing["state"] == "queued"
                or existing["lease_until"] > connection.execute("SELECT now() AS t").fetchone()["t"]
            ):
                _remember_request(
                    connection, tenant["id"], body["request_key"], fingerprint, existing["id"]
                )
                return public_job(existing)
            # An explicit new save request can recover an interrupted attempt.
            # Native hash checks recognize already saved bytes; claim never
            # automatically repeats a consequential write on lease expiry.
            connection.execute(
                "UPDATE desktop_jobs SET state='failed',error='Save interrupted; retry requested.' WHERE id=%s",
                (existing["id"],),
            )
    queued = connection.execute(
        "SELECT count(*) AS n FROM desktop_jobs WHERE device_id=%s AND state IN ('queued','executing')",
        (device["id"],),
    ).fetchone()["n"]
    if queued >= 10:
        raise ServiceError("conflict", "This PC already has queued work. Wait for it to finish.")
    task = (
        {"id": run["task_id"]}
        if run
        else connection.execute(
            "INSERT INTO tasks(tenant_id,title) VALUES (%s,%s) RETURNING id",
            (
                tenant["id"],
                "Check Tally connection" if operation == "tally.probe" else "Refresh local folder",
            ),
        ).fetchone()
    )
    job = connection.execute(
        """INSERT INTO desktop_jobs(tenant_id,device_id,actor_id,task_id,operation,input,request_key,request_hash)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            tenant["id"],
            device["id"],
            user["id"],
            task["id"],
            body["operation"],
            Jsonb(body["input"]),
            body["request_key"],
            fingerprint,
        ),
    ).fetchone()
    _remember_request(connection, tenant["id"], body["request_key"], fingerprint, job["id"])
    _observe(connection, job, "queued", f"Waiting for {device['name']}.", 0)
    return public_job(job)


def _request_job(connection, tenant_id, key):
    row = connection.execute(
        """SELECT j.*,r.request_hash AS replay_hash FROM desktop_job_requests r JOIN desktop_jobs j
        ON j.tenant_id=r.tenant_id AND j.id=r.job_id WHERE r.tenant_id=%s AND r.request_key=%s""",
        (tenant_id, key),
    ).fetchone()
    if row:
        row["request_hash"] = row.pop("replay_hash")
    return row


def _remember_request(connection, tenant_id, key, fingerprint, job_id):
    connection.execute(
        "INSERT INTO desktop_job_requests(tenant_id,request_key,request_hash,job_id) VALUES (%s,%s,%s,%s)",
        (tenant_id, key, fingerprint, job_id),
    )


def job_detail(connection, tenant, user, job_id):
    row = connection.execute(
        "SELECT * FROM desktop_jobs WHERE tenant_id=%s AND actor_id=%s AND id=%s",
        (tenant["id"], user["id"], job_id),
    ).fetchone()
    if not row:
        raise ServiceError("not_found", "Local task not found.")
    return public_job(row)


def claim(connection, device):
    connection.execute("UPDATE desktop_devices SET last_seen_at=now() WHERE id=%s", (device["id"],))
    row = connection.execute(
        """SELECT * FROM desktop_jobs WHERE device_id=%s AND (state='queued' OR
           (state='executing' AND operation NOT IN ('accounts.save','tally.save') AND lease_until<now()))
           ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1""",
        (device["id"],),
    ).fetchone()
    if not row:
        return None
    row = connection.execute(
        """UPDATE desktop_jobs SET state='executing',claim_token=%s,lease_until=now()+interval '2 minutes',
           attempts=attempts+1,updated_at=now() WHERE id=%s RETURNING *""",
        (uuid4(), row["id"]),
    ).fetchone()
    _observe(
        connection,
        row,
        "executing",
        "Checking Tally on your PC…"
        if row["operation"] == "tally.probe"
        else "Reading your connected folder…",
        30,
    )
    return {
        "id": row["id"],
        "operation": row["operation"],
        "input": row["input"],
        "claim_token": row["claim_token"],
    }


def _claimed_job(connection, device, job_id, claim_token):
    job = connection.execute(
        "SELECT * FROM desktop_jobs WHERE device_id=%s AND id=%s FOR UPDATE", (device["id"], job_id)
    ).fetchone()
    if not job:
        raise ServiceError("not_found", "Local task not found.")
    if str(job["claim_token"]) != str(claim_token):
        raise ServiceError("conflict", "This task attempt has been replaced.")
    return job


def plan(connection, device, job_id, claim_token):
    job = _claimed_job(connection, device, job_id, claim_token)
    if job["state"] == "executing" and job["operation"] == "tally.references":
        from .accounts.bills import context_plan

        return context_plan(connection, device, job)
    if job["state"] == "executing" and job["operation"] == "sources.discover":
        from . import discovery

        return discovery.plan(connection, device, job)
    if job["state"] == "executing" and job["operation"] == "tally.save":
        from .accounts.bills import recheck_target
        from .accounts.tally_writes import spec

        run, write = spec(connection, device, job["input"])
        recheck_target(
            connection,
            {"id": device["tenant_id"]},
            {"id": device["owner_id"]},
            run["config"]["tally_target"],
        )
        return write["plan"]
    if job["state"] != "executing" or job["operation"] != "accounts.save":
        raise ServiceError("conflict", "This save is no longer running.")
    _, spec = _save_spec(connection, device, job["input"])
    return {
        "source_id": spec["source_id"],
        "path": spec["path"],
        "before_sha256": spec["before_sha256"],
        "after_sha256": spec["after_sha256"],
        "content": base64.b64encode(bytes(spec["content"])).decode(),
    }


def _bytes(value):
    try:
        if not isinstance(value, str) or len(value) > 6_666_668:
            raise ValueError()
        data = base64.b64decode(value, validate=True)
        if not 1 <= len(data) <= 5_000_000:
            raise ValueError()
        return data
    except (ValueError, binascii.Error) as error:
        raise ServiceError("invalid", "The saved file is invalid or too large.") from error


def finish(connection, device, job_id, receipt):
    job = _claimed_job(connection, device, job_id, receipt["claim_token"])
    result, error = receipt.get("result"), receipt.get("error")
    if (result is None) == (error is None):
        raise ServiceError("invalid", "Return a result or an error.")
    if (
        result is not None
        and job["operation"] == "tally.probe"
        and (
            not isinstance(result, dict)
            or set(result) != {"available", "companies"}
            or type(result["available"]) is not bool
            or not isinstance(result["companies"], list)
            or len(result["companies"]) > 100
            or any(not isinstance(c, str) or not 1 <= len(c) <= 200 for c in result["companies"])
        )
    ):
        raise ServiceError("invalid", "Tally returned an invalid connection result.")
    fingerprint = _hash(json.dumps({"result": result, "error": error}, sort_keys=True))
    if job["receipt_hash"]:
        if job["receipt_hash"] != fingerprint:
            raise ServiceError("conflict", "This task already has a different result.")
        return public_job(job)
    if job["state"] != "executing" and not (
        job["operation"] in ("accounts.save", "tally.save")
        and job["error"] == "Save interrupted; retry requested."
    ):
        raise ServiceError("conflict", "This local task is no longer running.")
    summary = error
    if result is not None and job["operation"] == "files.refresh":
        if (
            set(result) != {"files"}
            or not isinstance(result["files"], list)
            or not 1 <= len(result["files"]) <= 100
        ):
            raise ServiceError("invalid", "Choose between 1 and 100 supported files.")
        if any(
            not isinstance(f, dict)
            or set(f) != {"path", "content"}
            or not isinstance(f["path"], str)
            for f in result["files"]
        ):
            raise ServiceError("invalid", "Invalid folder snapshot.")
        source = _bound_source(connection, device, job["input"]["source_id"])
        names, contents = [], []
        for file in result["files"]:
            names.append(file["path"])
            contents.append(_bytes(file["content"]))
            if sum(map(len, contents)) > 30_000_000:
                raise ServiceError("invalid", "A source refresh is limited to 30 MB.")
        accounts.upload_source(
            connection,
            {"id": device["tenant_id"]},
            {"id": device["owner_id"], "is_platform_admin": False},
            names,
            contents,
            source["label"],
            True,
            source["id"],
        )
        result = {"source_id": str(source["id"]), "file_count": len(contents)}
        summary = f"Folder refreshed. {len(contents)} files ready."
    elif result is not None and job["operation"] == "accounts.save":
        if set(result) != {"content"}:
            raise ServiceError("invalid", "Return the actual saved workbook.")
        _save_spec(connection, device, job["input"], pending=False)
        verified = accounts.verify_write(
            connection,
            {"id": device["tenant_id"]},
            job["input"]["run_id"],
            job["input"]["write_id"],
            _bytes(result["content"]),
        )
        result = {"verified": True, "run_state": verified["state"]}
        summary = "Workbook saved and checked."
    elif job["operation"] == "tally.save":
        from .accounts.tally_writes import accept

        result = accept(
            connection,
            device,
            job["input"],
            result if result is not None else {"outcome": "attention", "message": error},
        )
        summary = (
            "Tally bill reconciled."
            if result["verified"]
            else "This bill needs review; other bills continue."
        )
    elif job["operation"] == "tally.references":
        if not error:
            from .accounts.bills import accept_context

            try:
                result = accept_context(connection, device, job, result)
            except ServiceError as rejected:
                # A rejected read is terminal and observable. Returning a 409
                # would discard the PC receipt while leaving the job reclaimable.
                error, result = str(rejected), None
        summary = error or "Tally references prepared; bill extraction is queued."
    elif job["operation"] == "sources.discover":
        from . import discovery

        if error:
            discovery.fail(connection, device, job, error)
        else:
            result = discovery.collect(connection, device, job, result)
        summary = "Source collection finished."
    elif result and not result["available"]:
        error = "Tally is not available. Open Tally and try again."
    state = "failed" if error else "completed"
    updated = connection.execute(
        """UPDATE desktop_jobs SET state=%s,result=%s,error=%s,receipt_hash=%s,lease_until=NULL,
           updated_at=now() WHERE id=%s RETURNING *""",
        (state, Jsonb(result), error, fingerprint, job_id),
    ).fetchone()
    summary = (
        error
        or summary
        or (
            f"Tally is connected. {len(result['companies'])} compan{'y' if len(result['companies']) == 1 else 'ies'} available."
        )
    )
    _observe(
        connection,
        updated,
        "queued" if job["operation"] == "tally.references" and not error else state,
        summary,
        30 if error or job["operation"] == "tally.references" else 100,
    )
    return public_job(updated)
