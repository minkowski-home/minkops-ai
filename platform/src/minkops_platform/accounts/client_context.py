"""Pinned discovery evidence and explicit company routing, without accounting state."""

import copy
import hashlib
import json
import re
from datetime import date

MAX_CONTEXT_BYTES = 64_000_000


def text(value):
    return (
        value if isinstance(value, str) else value.get("#text") if isinstance(value, dict) else None
    )


def validate_snapshot(snapshot, config):
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) - {"scope_error"}
        != {"format_version", "period", "companies", "company_scope", "partial"}
        or snapshot["format_version"] != "2"
        or snapshot["period"] != config["period"]
    ):
        raise ValueError("Discovery returned a different period or format.")
    period = snapshot["period"]
    start, end = date.fromisoformat(period["from"]), date.fromisoformat(period["to"])
    if start > end:
        raise ValueError("Invalid discovery period.")
    companies = snapshot["companies"]
    scope = snapshot["company_scope"]
    scope_error = snapshot.get("scope_error")
    if scope_error is not None and (
        not isinstance(scope_error, str) or not 1 <= len(scope_error) <= 300
    ):
        raise ValueError("Invalid company scope failure.")
    if (
        not isinstance(companies, list)
        or not 1 <= len(companies) <= 50
        or type(snapshot["partial"]) is not bool
    ):
        raise ValueError("Invalid company scope.")
    if (
        not isinstance(scope, list)
        or len(scope) != len(companies)
        or any(
            not isinstance(c, dict)
            or set(c) != {"company", "company_guid", "company_number"}
            or any(
                not isinstance(c[k], str) or not c[k].strip() for k in ("company", "company_number")
            )
            or (
                c["company_guid"] is not None
                and (not isinstance(c["company_guid"], str) or not c["company_guid"].strip())
            )
            or not re.fullmatch(r"[0-9]{1,10}", c["company_number"])
            for c in scope
        )
        or any(len({c[key] for c in scope}) != len(scope) for key in ("company", "company_number"))
        or len([c["company_guid"] for c in scope if c["company_guid"] is not None])
        != len({c["company_guid"] for c in scope if c["company_guid"] is not None})
    ):
        raise ValueError("Invalid company scope evidence.")
    expected = {c["company"]: c for c in scope}
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
        if name not in expected:
            raise ValueError("Discovery omitted or replaced a scoped company.")
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
            or guid != expected[name]["company_guid"]
            or str(text(identity.get("COMPANYNUMBER")) or "").strip()
            != expected[name]["company_number"]
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
    if snapshot["partial"] != (bool(scope_error) or any(c["status"] != "ready" for c in companies)):
        raise ValueError("Incorrect discovery completeness.")
    if len(json.dumps(snapshot).encode()) > MAX_CONTEXT_BYTES:
        raise ValueError("Discovery exceeds supported size.")


def master_lookup(company):
    """Derive a company-scoped view; the pinned native export remains untouched.

    Identity collisions with different definitions are unsafe, whereas equal
    names with different GUIDs remain multiple candidates. No master type is
    excluded: statutory and custom definitions can be useful downstream.
    """
    records, by_type, identities, metadata = [], {}, {}, []
    duplicate_count = 0
    for source_index, record in enumerate(company.get("masters", {}).get("records", [])):
        kind, data = record["type"], record["data"]
        if kind == "COMPANY" and "REMOTECMPINFO.LIST" in data:
            remote = data["REMOTECMPINFO.LIST"]
            if (
                not isinstance(remote, dict)
                or text(remote.get("NAME")) != company.get("company_guid")
                or text(remote.get("REMOTECMPNAME")) != company["company"]
                or any(k != "REMOTECMPINFO.LIST" and not k.startswith("@_")
                       and not (k == "#text" and isinstance(v, str) and not v.strip())
                       for k, v in data.items())
            ):
                raise ValueError("Master metadata company identity mismatch.")
            metadata.append(source_index)
            continue
        guid = text(data.get("GUID"))
        name = text(data.get("@_NAME")) or text(data.get("NAME"))
        master_id = text(data.get("MASTERID"))
        encoded = json.dumps(data, sort_keys=True, ensure_ascii=False)
        # Names are a fallback only when Tally provides no native identifier.
        identity = (kind, "guid", guid) if guid else (
            (kind, "master_id", master_id) if master_id else
            (kind, "name", name) if name else (kind, "content", encoded)
        )
        if identity in identities:
            offset, previous = identities[identity]
            if previous != encoded:
                raise ValueError(f"Conflicting master identity in {company['company']}: {kind}.")
            records[offset]["source_record_indexes"].append(source_index)
            duplicate_count += 1
            continue
        offset = len(records)
        identities[identity] = (offset, encoded)
        records.append({"type": kind, "data": copy.deepcopy(data),
                        "source_record_indexes": [source_index]})
        index = by_type.setdefault(kind, {"record_indexes": [], "by_guid": {}, "by_name": {}})
        index["record_indexes"].append(offset)
        if guid:
            index["by_guid"].setdefault(guid, []).append(offset)
        if name:
            index["by_name"].setdefault(name, []).append(offset)
    return {
        "company_guid": company.get("company_guid"), "records": records,
        "by_type": by_type, "metadata_source_record_indexes": metadata,
        "summary": {
            "exported_count": len(company.get("masters", {}).get("records", [])),
            "unique_count": len(records), "duplicate_count": duplicate_count,
            "metadata_count": len(metadata),
            "counts_by_type": {kind: len(index["record_indexes"]) for kind, index in by_type.items()},
        },
    }


def targets_from_snapshot(snapshot, device_id, discovery_id):
    targets = []
    for company in snapshot["companies"]:
        if company["status"] != "ready":
            raise ValueError("Complete discovery before Bill Entry.")
        masters = master_lookup(company)["records"]
        collections = []
        for category, kind in [
            ("company", "COMPANY"),
            ("ledgers", "LEDGER"),
            ("voucher_types", "VOUCHERTYPE"),
        ]:
            records = (
                [company["identity"]]
                if category == "company"
                else [r["data"] for r in masters if r["type"] == kind]
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

        target = target_from_references(
            {
                "company": company["company"],
                "port": company["port"],
                "collections": collections,
            },
            device_id,
            discovery_id,
        )
        books_from = books_beginning(company["identity"])
        if books_from:
            target["books_from"] = books_from
        targets.append(target)
    return targets


def books_beginning(identity):
    """Tally's "Books beginning from" date as ISO text, when the export has one.

    Older companions or exports without it simply skip the date preflight.
    """
    from datetime import date

    value = str(text(identity.get("BOOKSFROM")) or "").strip()
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8])).isoformat() if len(value) == 8 else None
    except ValueError:
        return None


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


# Catalogs stamped with this format deliver records without empty values.
CONTEXT_RECORD_FORMAT = "1"


def compact_record(value):
    """Drop empty strings, nulls and empty containers; keep every list position.

    Native exports repeat hundreds of empty tags per voucher, roughly half of
    each record. Empty and absent carry the same evidence, while list offsets
    stay valid for the master index and cited context notes. Values such as 0,
    False and "No" are kept: they carry meaning.
    """
    if isinstance(value, dict):
        kept = {key: compact_record(item) for key, item in value.items()}
        return {key: item for key, item in kept.items() if item not in ("", None, [], {})}
    if isinstance(value, list):
        return [compact_record(item) for item in value]
    return value


def context_assets(catalog):
    """Full records live in lookup files; the manifest is small enough to read first.

    Split at record boundaries for hosted file limits. Never discard records.
    File IDs and bytes derive only from the immutable server-owned catalog, so
    only catalogs stamped with the compact format change delivered bytes.
    """
    compact = catalog.get("context_record_format") == CONTEXT_RECORD_FORMAT
    if catalog.get("format_version") != "2":
        return [], copy.deepcopy(catalog)
    if catalog.get("master_lookup_version") not in (None, "1"):
        raise ValueError("Unsupported master lookup version.")
    files, manifest = (
        [],
        {
            "format_version": catalog["format_version"],
            "run_id": catalog["run_id"],
            "companies": [],
            "files": [],
        },
    )
    if catalog.get("master_lookup_version") == "1":
        manifest["master_lookup_version"] = "1"

    def add(name, value, *, workspace_references=False):
        content = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
        if len(content) > 4_000_000:
            raise ValueError("An individual discovery record exceeds hosted limits.")
        identifier = (
            "discovery-"
            + hashlib.sha256((catalog["run_id"] + ":" + name).encode()).hexdigest()[:24]
        )
        digest = hashlib.sha256(content).hexdigest()
        files.append(
            {"id": identifier, "path": name + ".json", "content": content, "sha256": digest,
             **({"workspace_references": True} if workspace_references else {})}
        )
        manifest["files"].append(
            {"kind": name, "path": "/workspace/inputs/" + identifier + ".json", "sha256": digest}
        )
        return manifest["files"][-1]["path"]

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
            # Preserve the exact files/hashes of previously authorized runs.
            lookup = master_lookup(company) if catalog.get("master_lookup_version") == "1" else None
            locations = []
            for kind in ("masters", "vouchers"):
                chunk, size, number = [], 2, 0
                records = lookup["records"] if kind == "masters" and lookup else company.get(kind, {}).get("records", [])

                def flush():
                    label = "masters-lookup-v1" if kind == "masters" and lookup else kind
                    path = add(f"company-{index}-{label}-{number}", chunk)
                    if kind == "masters" and lookup:
                        locations.extend({"path": path, "offset": offset} for offset in range(len(chunk)))

                for record in records:
                    if compact:
                        record = compact_record(record)
                    length = (
                        len(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()) + 2
                    )
                    if chunk and size + length > 3_500_000:
                        flush()
                        chunk, size, number = [], 2, number + 1
                    chunk.append(record)
                    size += length
                flush()
            if lookup is None:
                continue
            lookup_index = {
                "company_guid": lookup["company_guid"], "summary": lookup["summary"],
                "metadata_source_record_indexes": lookup["metadata_source_record_indexes"],
                "by_type": {
                    kind: {
                        "records": [locations[i] for i in entry["record_indexes"]],
                        "by_guid": {key: [locations[i] for i in offsets] for key, offsets in entry["by_guid"].items()},
                        "by_name": {key: [locations[i] for i in offsets] for key, offsets in entry["by_name"].items()},
                    }
                    for kind, entry in lookup["by_type"].items()
                },
            }
            manifest["companies"][-1]["master_lookup_path"] = add(
                f"company-{index}-master-index-v1", lookup_index, workspace_references=True)
            manifest["companies"][-1]["master_summary"] = lookup["summary"]
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
