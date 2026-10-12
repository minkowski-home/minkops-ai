"""Resolve evidenced selections against pinned native identities before any write.

Recognition belongs to the workflow's AI and full discovery evidence. This module
does not guess by edit distance or silently create aliases. Its job is to make a
chosen identity authoritative for spelling, company scope and native readback.
"""
import hashlib
import json

FIELDS = ("vendor", "purchase_ledger", "tax_ledger")


def ledger_reference(target, name, identity):
    # Include discovery and company even when installations reuse native GUIDs.
    key = [target["discovery_id"], target["destination_key"], "LEDGER",
           identity.get("GUID") or name]
    return "ledger-" + hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()


def resolve_masters(record, target, *, required=False, allow_split=False):
    allocations = record.get("tax_allocations")
    if allocations is not None and not allow_split:
        raise ValueError("This pinned run does not support split tax allocations.")
    selections = record.get("master_refs")
    if selections is None and not required:
        return  # Already-pinned name-based runs retain their original contract.
    if not isinstance(selections, dict) or set(selections) != set(FIELDS):
        raise ValueError("Select discovered master references for this bill.")
    catalog = target.get("ledger_refs", {})
    resolved = {}
    for field in FIELDS:
        selection = selections[field]
        if field == "tax_ledger" and (not record["data"].get("tax") or allocations is not None):
            if selection is not None:
                raise ValueError("Zero or split tax must not select a single tax ledger reference.")
            resolved[field] = None
            continue
        if (not isinstance(selection, dict) or not {"ref", "evidence"} <= set(selection)
                or set(selection) - {"ref", "evidence", "new_supplier"}
                or ("new_supplier" in selection and type(selection["new_supplier"]) is not bool)
                or not isinstance(selection["evidence"], str) or not selection["evidence"].strip()):
            raise ValueError(f"{field} needs an evidenced master reference.")
        ref = selection["ref"]
        if selection.get("new_supplier") and (field != "vendor" or ref is not None):
            raise ValueError("New supplier selection has contradictory master evidence.")
        if ref is None and field == "vendor":
            # A genuinely new supplier remains a held proposal, with its printed
            # name preserved for the existing explicit native creation decision.
            if selection.get("new_supplier") is not True:
                raise ValueError("Supplier match is unresolved; a new supplier has not been established.")
            name = record["data"].get(field)
            if not isinstance(name, str) or not name.strip() or name in target["ledgers"]:
                raise ValueError("An existing supplier needs a discovered reference.")
            continue
        if not isinstance(ref, str) or ref not in catalog:
            raise ValueError(f"{field} reference is outside this company's pinned discovery.")
        master = catalog[ref]
        name = master["name"]
        if target["ledgers"].count(name) != 1:
            raise ValueError(f"{field} has an ambiguous native name; refresh the original system.")
        if target["references"]["ledgers"].get(name) != master["identity"]:
            raise ValueError(f"{field} reference no longer matches its observed identity.")
        resolved[field] = name
    split = []
    if allocations is not None:
        if not isinstance(allocations, list) or not 1 <= len(allocations) <= 8:
            raise ValueError("Select bounded explicit tax allocations.")
        for line in allocations:
            if (not isinstance(line, dict) or not {"ref", "amount", "evidence"} <= set(line)
                    or set(line) - {"ref", "amount", "evidence", "ledger"}
                    or not isinstance(line["ref"], str) or line["ref"] not in catalog
                    or not isinstance(line["evidence"], str) or not line["evidence"].strip()):
                raise ValueError("Tax allocation needs an evidenced company-scoped master reference.")
            master = catalog[line["ref"]]
            name = master["name"]
            if target["ledgers"].count(name) != 1 or target["references"]["ledgers"].get(name) != master["identity"]:
                raise ValueError("Tax allocation has an ambiguous or changed native identity.")
            split.append({**line, "ledger": name})
        from .bills import allocation_entries

        if record["data"].get("tax_ledger") is not None:
            raise ValueError("Do not mix split tax with a single tax ledger.")
        allocation_entries({**record["data"], **resolved}, split)
        names = [resolved.get("vendor", record["data"].get("vendor")), resolved["purchase_ledger"], *(line["ledger"] for line in split)]
        if len(set(names)) != len(names):
            raise ValueError("Supplier, purchase and tax allocations require distinct ledgers.")
    # Resolve atomically so an invalid selection cannot partially change a bill.
    record["data"].update(resolved)
    if allocations is not None:
        record["tax_allocations"] = split
