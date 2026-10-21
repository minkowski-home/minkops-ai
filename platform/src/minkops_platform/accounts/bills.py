"""Bill holds and notes, and the Tally destination each bill run pins.

Every proposal is bound to one confirmed Source Discovery company; nothing a
model proposes becomes writable without the voucher gate in vouchers.check.
"""

from minkops_platform.errors import ServiceError


class HoldReason(ValueError):
    """A deterministic server-side hold with a stable code for attention labels."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def note_hold(record, error):
    """Record why a proposal is held, keeping a coded reason for its label."""
    record["findings"] = list(dict.fromkeys([*record["findings"], str(error)]))
    if getattr(error, "code", None):
        record["exception_codes"] = list(dict.fromkeys([*record.get("exception_codes", []), error.code]))


def add_note(record, text):
    """An internal observation about a bill; notes never hold it or ask for attention."""
    record["notes"] = list(dict.fromkeys([*record.get("notes", []), text]))


COMPANY_CONTEXT_REQUIRED = "Refresh Source Discovery to collect complete company context before a new bill run."


def tally_target(connection, tenant, user, discovery_id):
    """The run's destination: every company of one confirmed Source Discovery."""
    from minkops_platform import desktop, discovery

    catalog = discovery.require_ready(connection, tenant["id"], discovery_id, ["tally"])
    row = discovery.get_run(connection, tenant["id"], discovery_id)
    if row["actor_id"] != user["id"]:
        raise ServiceError("forbidden", "Use source discovery confirmed by your account.")
    desktop.owned_device(connection, tenant["id"], user["id"], row["device_id"])
    source = next(s["snapshot"] for s in catalog["sources"] if s["tool"] == "tally")
    if "companies" not in source:
        raise ServiceError("conflict", COMPANY_CONTEXT_REQUIRED)
    from .client_context import targets_from_snapshot

    return {
        "device_id": str(row["device_id"]),
        "discovery_id": str(discovery_id),
        "companies": targets_from_snapshot(source, row["device_id"], discovery_id),
        "company_mode": "infer",
        "locked_company_guid": None,
    }


def recheck_target(connection, tenant, user, current):
    if "companies" not in current:
        raise ServiceError("conflict", COMPANY_CONTEXT_REQUIRED)
    from minkops_platform import desktop

    desktop.owned_device(connection, tenant["id"], user["id"], current["device_id"])
    # The approved snapshot stays pinned. The native adapter rechecks exact
    # company/master versions and duplicates immediately before each write.
    return current


def capture_tally_findings(result, config):
    """Hold invalid proposals before approval, preserving independent siblings.

    Discovery references are deterministic authority. An agent's confident
    interpretation must never make an unknown master silently writable.
    """
    from .client_context import select_target
    from .vouchers import resolve, summary

    target = config["tally_target"]
    unresolved = result.setdefault("unresolved", [])
    for record in result["records"]:
        record["data"] = summary(record, config)
        try:
            selected = select_target(record, target)
            record["company_guid"] = selected["references"]["company_guid"]
            record["company_name"] = selected["company"]
            record["preview"] = resolve(record, config).preview()
        except ValueError as error:
            note_hold(record, error)
            record["decision"] = "hold"
            if not any(i["source_file_id"] == record["source_file_id"] for i in unresolved):
                unresolved.append({"source_file_id": record["source_file_id"], "reason": str(error),
                                   **({"code": error.code} if getattr(error, "code", None) else {})})
    return result


def refreshed_tally_target(connection, tenant, user, current):
    """Explicit bill continuation may use refreshed masters in the same company.

    Never reroute a held bill to a different company or device. A pending or
    failed refresh must be confirmed before a new paid extraction can start.
    """
    if "companies" not in current:
        raise ServiceError("conflict", COMPANY_CONTEXT_REQUIRED)
    latest = connection.execute(
        "SELECT id FROM discovery_runs WHERE tenant_id=%s AND actor_id=%s AND device_id=%s AND config->>'depth'='client_context' ORDER BY created_at DESC LIMIT 1",
        (tenant["id"], user["id"], current["device_id"]),
    ).fetchone()
    updated = tally_target(
        connection, tenant, user, latest["id"] if latest else current["discovery_id"]
    )
    if {c["destination_key"] for c in current["companies"]} != {
        c["destination_key"] for c in updated["companies"]
    }:
        raise ServiceError("conflict", "Company scope changed. Start a new bill run.")
    return {**updated, "company_mode": current["company_mode"],
            "locked_company_guid": current["locked_company_guid"]}
