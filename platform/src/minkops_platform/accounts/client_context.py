"""Pinned discovery evidence and explicit company routing, without accounting state."""

import copy
import hashlib
import json
from datetime import date

MAX_CONTEXT_BYTES = 64_000_000


def text(value):
    return (
        value if isinstance(value, str) else value.get("#text") if isinstance(value, dict) else None
    )


def validate_snapshot(snapshot, config):
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != {"format_version", "period", "companies", "partial"}
        or snapshot["format_version"] != "2"
        or snapshot["period"] != config["period"]
    ):
        raise ValueError("Discovery returned a different period or format.")
    period = snapshot["period"]
    start, end = date.fromisoformat(period["from"]), date.fromisoformat(period["to"])
    if start > end:
        raise ValueError("Invalid discovery period.")
    companies = snapshot["companies"]
    if (
        not isinstance(companies, list)
        or not 1 <= len(companies) <= 50
        or type(snapshot["partial"]) is not bool
    ):
        raise ValueError("Invalid company scope.")
    names, guids = set(), set()
    for company in companies:
        if not isinstance(company, dict):
            raise ValueError("Invalid company snapshot.")
        name = company.get("company")
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 200
            or name in names
            or company.get("port") != config["port"]
        ):
            raise ValueError("Invalid or duplicate company.")
        names.add(name)
        if company.get("status") == "unavailable":
            if not isinstance(company.get("error"), str) or not 1 <= len(company["error"]) <= 300:
                raise ValueError("Invalid collection failure.")
            continue
        if company.get("status") != "ready" or set(company) != {
            "company",
            "port",
            "status",
            "identity",
            "company_guid",
            "masters",
            "vouchers",
        }:
            raise ValueError("Invalid company snapshot.")
        guid = company["company_guid"]
        identity = company["identity"]
        if (
            not isinstance(identity, dict)
            or (identity.get("@_NAME") or text(identity.get("NAME"))) != name
            or not isinstance(guid, str)
            or not guid.strip()
            or guid in guids
            or text(identity.get("GUID")) != guid
        ):
            raise ValueError("Company identity mismatch.")
        guids.add(guid)
        for kind in ("masters", "vouchers"):
            collection = company[kind]
            if (
                not isinstance(collection, dict)
                or set(collection) != {"status", "count", "records"}
                or collection["status"] != "ready"
                or type(collection["count"]) is not int
                or not isinstance(collection["records"], list)
                or len(collection["records"]) != collection["count"]
            ):
                raise ValueError("Incomplete discovery collection.")
            voucher_ids = set()
            for record in collection["records"]:
                if (
                    not isinstance(record, dict)
                    or set(record) != {"type", "data"}
                    or not isinstance(record["type"], str)
                    or not isinstance(record["data"], dict)
                ):
                    raise ValueError("Invalid native record.")
                if kind == "vouchers":
                    value = text(record["data"].get("DATE"))
                    try:
                        observed = date.fromisoformat(value) if value and len(value) == 8 else None
                    except ValueError:
                        observed = None
                    if (
                        record["type"] != "VOUCHER"
                        or observed is None
                        or not start <= observed <= end
                    ):
                        raise ValueError("Voucher outside discovered period.")
                    identifier = text(record["data"].get("GUID")) or text(
                        record["data"].get("MASTERID")
                    )
                    if not identifier or identifier in voucher_ids:
                        raise ValueError("Missing or duplicate voucher identity.")
                    voucher_ids.add(identifier)
    if snapshot["partial"] != any(c["status"] != "ready" for c in companies):
        raise ValueError("Incorrect discovery completeness.")
    if len(json.dumps(snapshot).encode()) > MAX_CONTEXT_BYTES:
        raise ValueError("Discovery exceeds supported size.")


def targets_from_snapshot(snapshot, device_id, discovery_id):
    targets = []
    for company in snapshot["companies"]:
        if company["status"] != "ready":
            raise ValueError("Complete discovery before Bill Entry.")
        collections = []
        for category, kind in [
            ("company", "COMPANY"),
            ("ledgers", "LEDGER"),
            ("voucher_types", "VOUCHERTYPE"),
        ]:
            records = (
                [company["identity"]]
                if category == "company"
                else [r["data"] for r in company["masters"]["records"] if r["type"] == kind]
            )
            # Write checks need stable scalar identity, while full definitions stay in evidence files.
            records = [
                {
                    k: text(v)
                    for k, v in r.items()
                    if k in ("@_NAME", "NAME", "GUID", "PARENT", "ALTERID")
                }
                for r in records
            ]
            collections.append({"category": category, "status": "ready", "records": records})
        from .bills import target_from_references

        targets.append(
            target_from_references(
                {
                    "company": company["company"],
                    "port": company["port"],
                    "collections": collections,
                },
                device_id,
                discovery_id,
            )
        )
    return targets


def select_target(record, target):
    if "companies" not in target:
        return target  # Existing pinned runs keep their original single-company contract.
    guid = record.get("company_guid")
    if target["company_mode"] == "infer" and not str(record.get("company_evidence") or "").strip():
        raise ValueError("Company selection needs buyer or confirmed context evidence.")
    if target["company_mode"] == "locked":
        locked = target["locked_company_guid"]
        if guid is not None and guid != locked:
            raise ValueError("Bill company conflicts with the locked company.")
        guid = locked
    matches = [c for c in target["companies"] if c["references"]["company_guid"] == guid]
    if len(matches) != 1:
        raise ValueError("Identify exactly one discovered company or hand off this bill.")
    return matches[0]


def context_assets(catalog):
    """Full records live in lookup files; the manifest is small enough to read first.

    Split at record boundaries for hosted file limits. Never discard records.
    File IDs and bytes derive only from the immutable server-owned catalog.
    """
    if catalog.get("format_version") != "2":
        return [], copy.deepcopy(catalog)
    files, manifest = (
        [],
        {
            "format_version": catalog["format_version"],
            "run_id": catalog["run_id"],
            "companies": [],
            "files": [],
        },
    )

    def add(name, value):
        content = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
        if len(content) > 4_000_000:
            raise ValueError("An individual discovery record exceeds hosted limits.")
        identifier = (
            "discovery-"
            + hashlib.sha256((catalog["run_id"] + ":" + name).encode()).hexdigest()[:24]
        )
        digest = hashlib.sha256(content).hexdigest()
        files.append(
            {"id": identifier, "path": name + ".json", "content": content, "sha256": digest}
        )
        manifest["files"].append(
            {"kind": name, "path": "/workspace/inputs/" + identifier + ".json", "sha256": digest}
        )

    add("context-notes", catalog.get("context_notes", []))
    for source in catalog["sources"]:
        if source["tool"] != "tally" or "companies" not in source.get("snapshot", {}):
            continue
        for index, company in enumerate(source["snapshot"]["companies"]):
            manifest["companies"].append(
                {
                    "company": company["company"],
                    "company_guid": company.get("company_guid"),
                    "identity": company.get("identity"),
                    "period": source["snapshot"]["period"],
                }
            )
            for kind in ("masters", "vouchers"):
                chunk, size, number = [], 2, 0
                for record in company.get(kind, {}).get("records", []):
                    length = (
                        len(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()) + 2
                    )
                    if chunk and size + length > 3_500_000:
                        add(f"company-{index}-{kind}-{number}", chunk)
                        chunk, size, number = [], 2, number + 1
                    chunk.append(record)
                    size += length
                add(f"company-{index}-{kind}-{number}", chunk)
    return files, manifest


def validate_notes(notes, catalog):
    from jsonschema import Draft202012Validator
    from minkops_platform.resources import REPOSITORY_ROOT

    schema = json.loads(
        (
            REPOSITORY_ROOT
            / "employees/accounts-desk/workflows/source-discovery/context-note.schema.json"
        ).read_text()
    )
    Draft202012Validator({"type": "array", "maxItems": 100, "items": schema}).validate(notes)
    companies = {
        c["company_guid"]: c
        for s in catalog["sources"]
        if s["tool"] == "tally"
        for c in s.get("snapshot", {}).get("companies", [])
        if c.get("company_guid")
    }
    for note in notes:
        company = companies.get(note["company_guid"])
        if not company:
            raise ValueError("Context note refers to an undiscovered company.")
        identifiers = {
            text(r["data"].get("GUID"))
            or text(r["data"].get("@_NAME"))
            or text(r["data"].get("NAME"))
            for kind in ("masters", "vouchers")
            for r in company.get(kind, {}).get("records", [])
        }
        if not set(note["evidence_ids"]) <= identifiers:
            raise ValueError("Context evidence must refer to collected native records.")
    return copy.deepcopy(notes)
