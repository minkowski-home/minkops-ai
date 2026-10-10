"""Approved Tally intents, native receipts and per-bill handoffs."""

import json
from uuid import NAMESPACE_URL, uuid5

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from minkops_platform.errors import ServiceError

from .bills import validate_tally
from .repository import observe, run_for


def prepare(connection, run, result, *, approved=False):
    from minkops_platform.workflow_policies import enforce_policies

    if enforce_policies(run["config"], result).get("requires_review") and not approved:
        raise ValueError("Client policy requires explicit review before destination writes.")
    scope = run["config"]["tally_target"]
    from .client_context import select_target

    seen = {}
    ordered = sorted(
        enumerate(result["records"]), key=lambda pair: pair[1].get("company_guid") or ""
    )
    for index, record in ordered:
        if (
            record.get("status") in ("saved", "duplicate", "rejected", "writing")
            or record.get("decision") == "hold"
        ):
            continue
        if record.get("decision") == "reject":
            record["status"] = "rejected"
            continue
        try:
            target = select_target(record, scope)
            identity = validate_tally(record["data"], target)
            key = (target["destination_key"], identity)
            if key in seen:
                first = result["records"][seen[key]]
                if first["data"] == record["data"]:
                    record["duplicate_of"] = seen[key]
                    record["status"] = "writing"
                    continue
                raise ValueError(
                    "This batch contains conflicting versions of the same bill. Review the correction separately."
                )
            if record["operation"] == "update" and not record.get("current"):
                raise ValueError(
                    "First reconcile the existing voucher before approving a correction."
                )
            token = str(
                uuid5(
                    NAMESPACE_URL,
                    f"minkops:{run['tenant_id']}:{target['destination_key']}:{identity}",
                )
            )
            plan = {
                "company": target["company"],
                "port": target["port"],
                "data": record["data"],
                "remote_id": token,
                "operation": record["operation"],
                "expected": record.get("current") if record["operation"] == "update" else None,
                "discovery_id": target["discovery_id"],
                "references": target.get("references"),
            }
            with connection.transaction():
                write = connection.execute(
                    """INSERT INTO account_tally_writes
                    (tenant_id,run_id,device_id,company,identity,record_index,plan,destination_key)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (
                        run["tenant_id"],
                        run["id"],
                        target["device_id"],
                        target["company"],
                        identity,
                        index,
                        Jsonb(plan),
                        target["destination_key"],
                    ),
                ).fetchone()
                from minkops_platform.desktop import enqueue_approved

                enqueue_approved(connection, run, target["device_id"], "tally.save", write["id"])
            record["status"] = "writing"
            seen[key] = index
        except ValueError as error:
            record["status"] = "held"
            record["findings"] = list(dict.fromkeys([*record["findings"], str(error)]))
            from .attention import flag
            flag(connection, run, record)
        except UniqueViolation:
            record["status"] = "held"
            record["findings"].append(
                "Another approved run is reconciling this bill. Finish it, then resume this review."
            )
    return result


def complete_run(connection, run, result):
    from .attention import flag
    for record in result["records"]:
        if record.get("status") == "held":
            flag(connection, run, record)
    pending_excel = connection.execute(
        "SELECT count(*) AS n FROM account_writes WHERE tenant_id=%s AND run_id=%s AND verified_at IS NULL AND cancelled_at IS NULL",
        (run["tenant_id"], run["id"]),
    ).fetchone()["n"]
    pending_tally = connection.execute(
        "SELECT count(*) AS n FROM account_tally_writes WHERE tenant_id=%s AND run_id=%s AND finished_at IS NULL AND cancelled_at IS NULL",
        (run["tenant_id"], run["id"]),
    ).fetchone()["n"]
    held = bool(result.get("unresolved")) or any(
        r.get("status") in (None, "held") for r in result["records"]
    )
    state = "writing" if pending_excel or pending_tally else "review" if held else "completed"
    connection.execute(
        "UPDATE account_runs SET result=%s WHERE tenant_id=%s AND id=%s",
        (Jsonb(result), run["tenant_id"], run["id"]),
    )
    summary = {
        "writing": "Approved entries are waiting for verified destination writes.",
        "review": "Successful entries are preserved. Review only the bills needing attention.",
        "completed": "Bill entries verified. Exact duplicates were skipped without adding records.",
    }[state]
    observe(
        connection,
        run,
        state,
        summary,
        100 if state == "completed" else 85 if state == "writing" else 70,
    )


def spec(connection, device, payload, *, pending=True):
    run = run_for(connection, device["tenant_id"], payload["run_id"], True)
    if run["actor_id"] != device["owner_id"]:
        raise ServiceError("not_found", "Approved run not found for this account.")
    row = connection.execute(
        "SELECT * FROM account_tally_writes WHERE tenant_id=%s AND run_id=%s AND id=%s AND device_id=%s FOR UPDATE",
        (device["tenant_id"], run["id"], payload["write_id"], device["id"]),
    ).fetchone()
    if not row:
        raise ServiceError("not_found", "Approved Tally write not found for this PC.")
    if pending and (run["state"] != "writing" or row["finished_at"] or row["cancelled_at"]):
        raise ServiceError("conflict", "This Tally write is no longer pending.")
    return run, row


def accept(connection, device, payload, receipt):
    run, write = spec(connection, device, payload, pending=False)
    if not isinstance(receipt, dict) or receipt.get("outcome") not in (
        "saved",
        "duplicate",
        "correction",
        "attention",
    ):
        raise ServiceError("invalid", "Invalid Tally write receipt.")
    outcome = receipt["outcome"]
    current = receipt.get("current")
    if outcome in ("saved", "duplicate", "correction"):
        if not isinstance(current, dict) or set(current) != {
            "master_id",
            "guid",
            "date",
            "invoice_number",
            "vendor",
            "entries",
            "fingerprint",
        }:
            raise ServiceError("invalid", "Tally receipt must contain an observed voucher.")
        if (
            any(
                not isinstance(current[k], str) or not 1 <= len(current[k]) <= 200
                for k in ("master_id", "guid", "date", "invoice_number", "vendor", "fingerprint")
            )
            or not isinstance(current["entries"], list)
            or not 1 <= len(current["entries"]) <= 100
        ):
            raise ServiceError("invalid", "Invalid observed voucher.")
        if any(
            not isinstance(e, dict)
            or set(e) != {"ledger", "amount"}
            or not isinstance(e["ledger"], str)
            or type(e["amount"]) is not int
            for e in current["entries"]
        ):
            raise ServiceError("invalid", "Invalid ledger readback.")
        from .bills import business_identity

        actual = {
            "vendor": current["vendor"],
            "invoice_number": current["invoice_number"],
            "date": f"{current['date'][:4]}-{current['date'][4:6]}-{current['date'][6:]}",
        }
        try:
            if business_identity(actual) != write["identity"]:
                raise ValueError()
        except ValueError as error:
            raise ServiceError("invalid", "Readback belongs to a different bill.") from error
        if outcome in ("saved", "duplicate"):
            from decimal import Decimal

            data = write["plan"]["data"]

            def money(v):
                return int(Decimal(str(v)) * 100)

            expected = [
                {"ledger": data["vendor"], "amount": money(data["total"])},
                {"ledger": data["purchase_ledger"], "amount": -money(data["subtotal"])},
            ]
            if data["tax"]:
                expected.append({"ledger": data["tax_ledger"], "amount": -money(data["tax"])})

            def key(e):
                return e["ledger"], e["amount"]

            if current["date"] != data["date"].replace("-", "") or sorted(
                current["entries"], key=key
            ) != sorted(expected, key=key):
                raise ServiceError(
                    "conflict", "Tally readback differs from the approved amounts or ledgers."
                )
            if (
                outcome == "saved"
                and write["plan"].get("expected")
                and current["guid"] != write["plan"]["expected"]["guid"]
            ):
                raise ServiceError("conflict", "Tally returned a different voucher identifier.")
    result = json.loads(json.dumps(run["result"]))
    record = result["records"][write["record_index"]]
    record["status"] = outcome if outcome in ("saved", "duplicate") else "held"
    for sibling in result["records"]:
        if sibling.get("duplicate_of") == write["record_index"]:
            sibling["status"] = "duplicate" if outcome in ("saved", "duplicate") else "held"
            sibling["findings"].append(
                "Repeated bill in this batch was skipped."
                if outcome in ("saved", "duplicate")
                else "The original bill needs attention; this repeated input was not written."
            )
    if current:
        record["current"] = current
    from .attention import flag
    if outcome in ("correction", "attention"):
        item = flag(connection, run, record, title="Review in Tally")
        from ..attention import audit
        audit(connection,item,run['actor_id'],outcome,receipt.get('message','Existing voucher needs review.'))
    # Best-guess review starts after verified write, using exact native identity.
    if current and outcome in ("saved", "duplicate"):
        from .attention import written
        written(connection, run, record)
        connection.execute("UPDATE attention_items SET target=jsonb_set(target,'{baseline}',%s),updated_at=now() WHERE tenant_id=%s AND event_key=%s AND status='pending'",
            (Jsonb(current), run["tenant_id"], f"bill:{run['id']}:{record['source_file_id']}:review"))
    if outcome == "duplicate":
        record["findings"].append(
            "Exact duplicate already exists; no additional voucher was created."
        )
    elif outcome in ("correction", "attention"):
        record["findings"].append(
            "Review in Tally."
            if outcome == "correction"
            else str(receipt.get("message", "Tally write needs attention."))[:300]
        )
    connection.execute(
        "UPDATE account_tally_writes SET outcome=%s,receipt=%s,finished_at=now(),verified_at=CASE WHEN %s THEN now() ELSE NULL END WHERE id=%s",
        (outcome, Jsonb(receipt), outcome in ("saved", "duplicate"), write["id"]),
    )
    if run["state"] == "writing":
        complete_run(connection, run, result)
    else:
        connection.execute(
            "UPDATE account_runs SET result=%s WHERE id=%s", (Jsonb(result), run["id"])
        )
    return {"verified": outcome in ("saved", "duplicate"), "outcome": outcome}
