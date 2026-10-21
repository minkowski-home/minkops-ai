"""Printed GST identity and same-company templates for permanent supplier masters.

Validation establishes structural consistency, not government registration
status. Cross-state creation is held in v1 until its tax treatment has a
separately supported contract; existing supplier vouchers remain unaffected.
"""
import re

STATES = dict(zip(
    [f"{i:02}" for i in range(1, 39)],
    ["Jammu and Kashmir", "Himachal Pradesh", "Punjab", "Chandigarh", "Uttarakhand", "Haryana", "Delhi", "Rajasthan",
     "Uttar Pradesh", "Bihar", "Sikkim", "Arunachal Pradesh", "Nagaland", "Manipur", "Mizoram", "Tripura", "Meghalaya",
     "Assam", "West Bengal", "Jharkhand", "Odisha", "Chhattisgarh", "Madhya Pradesh", "Gujarat", "Daman and Diu",
     "Dadra and Nagar Haveli and Daman and Diu", "Maharashtra", "Andhra Pradesh (Old)", "Karnataka", "Goa", "Lakshadweep",
     "Kerala", "Tamil Nadu", "Puducherry", "Andaman and Nicobar Islands", "Telangana", "Andhra Pradesh", "Ladakh"], strict=True))
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def state_name(code):
    if code not in STATES or code in ("25", "28"):
        raise ValueError("Unsupported or obsolete GST state code.")
    return STATES[code]


def gstin(value):
    if not isinstance(value, str):
        raise ValueError("A printed GSTIN is required.")
    value = value.strip().upper()
    if not re.fullmatch(r"[0-9]{2}[A-Z]{3}[ABCFGHJLPT][A-Z][0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]", value):
        raise ValueError("Invalid GSTIN or embedded PAN format.")
    state_name(value[:2])
    total, factor = 0, 2
    for character in reversed(value[:14]):
        product = ALPHABET.index(character) * factor
        total += product // 36 + product % 36
        factor = 3 - factor
    if value[-1] != ALPHABET[(36 - total % 36) % 36]:
        raise ValueError("GSTIN check character does not match.")
    return value


def _text(value, limit=250):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or re.search(r"[\x00-\x1f]", value):
        raise ValueError("Printed supplier details are incomplete.")
    return value.strip()


def _normal(value):
    return " ".join(str(value or "").split()).casefold()


def jurisdiction(value):
    """Resolve known printed jurisdiction names and optional matching GST codes.

    Never use fuzzy substrings: `Andhra Pradesh (37)` is valid evidence while
    the same name paired with another code cannot authorize a permanent master.
    """
    text = _normal(value).replace("&", "and")
    aliases = {"orissa": "odisha", "pondicherry": "puducherry", "uttaranchal": "uttarakhand",
               "nct delhi": "delhi", "new delhi": "delhi"}
    code = None
    match = re.fullmatch(r"(.+?)\s*(?:\((\d{1,2})\)|\s*-\s*(\d{1,2}))", text)
    leading = re.fullmatch(r"(\d{1,2})\s*-\s*(.+)", text)
    if match:
        text, code = match[1].strip(), (match[2] or match[3]).zfill(2)
    elif leading:
        code, text = leading[1].zfill(2), leading[2].strip()
    text = aliases.get(text, text)
    names = {_normal(state_name(k)): k for k in STATES if k not in ("25", "28")}
    found = names.get(text)
    if found is None or (code is not None and found != code):
        raise ValueError("GST jurisdiction name and code must identify one supported state.")
    return state_name(found)


def validate_details(details, *, company_state, tax):
    if not isinstance(details, dict):
        raise ValueError("Printed GST details are required.")
    number = gstin(details.get("gstin"))
    state = state_name(number[:2])
    if details.get("state_code") != number[:2] or jurisdiction(details.get("state")) != state:
        raise ValueError("Supplier state differs from its GSTIN.")
    if jurisdiction(company_state) != state or jurisdiction(details.get("place_of_supply")) != state:
        raise ValueError("Cross-state or unconfirmed place of supply needs manual review in v1.")
    registration = details.get("registration_type")
    if registration not in ("Regular", "Composition") or (registration == "Composition" and tax):
        raise ValueError("Supplier registration type conflicts with the printed tax.")
    address = details.get("address")
    if not isinstance(address, list) or not 1 <= len(address) <= 4:
        raise ValueError("A printed supplier address is required.")
    address = [_text(line) for line in address]
    pin = details.get("pincode")
    if not isinstance(pin, str) or not re.fullmatch(r"[1-9][0-9]{5}", pin):
        raise ValueError("A printed six-digit PIN code is required.")
    evidence = details.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("Supplier details require source evidence.")
    by_field = {}
    for entry in evidence:
        if (not isinstance(entry, dict) or type(entry.get("page")) is not int or entry["page"] < 1
                or not isinstance(entry.get("quote"), str) or not entry["quote"].strip()):
            raise ValueError("Supplier details require printed field evidence.")
        by_field.setdefault(entry.get("field"), []).append(entry["quote"])
    if not {"gstin", "registration_type", "state", "place_of_supply", "address"} <= set(by_field):
        raise ValueError("Supplier details require printed field evidence.")
    if not any(number in re.sub(r"\s", "", quote).upper() for quote in by_field["gstin"]):
        raise ValueError("GSTIN evidence must contain the printed GSTIN.")
    for field, values in (("registration_type", [registration]), ("state", [state]),
                          ("place_of_supply", [state]), ("address", [*address, pin])):
        printed = _normal(" ".join(by_field[field]))
        # A recognized printed alias remains valid source evidence even though
        # the permanent master uses the canonical jurisdiction name.
        if field in ("state", "place_of_supply"):
            present = any(_normal(value) in printed for value in (state, details[field]))
        else:
            present = all(_normal(value) in printed for value in values)
        if not present:
            raise ValueError("Supplier field evidence must contain its approved values.")
    return {"gstin": number, "registration_type": registration, "state_code": number[:2], "state": state,
            "place_of_supply": state, "address": address, "pincode": pin}


def scalar(value):
    return str(value.get("#text", "") if isinstance(value, dict) else value or "").strip()


def native_values(value, names):
    """Full discovery retains version-specific nested native GST registrations."""
    values = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in names:
                values.update(scalar(item) for item in (child if isinstance(child, list) else [child]) if scalar(item))
            if isinstance(child, (dict, list)):
                values.update(native_values(child, names))
    elif isinstance(value, list):
        for child in value:
            values.update(native_values(child, names))
    return values


def creation_plan(run, record, selected):
    details = record.get("supplier_details")
    if details is None:
        if record["data"].get("tax"):
            raise ValueError("GST supplier details are missing.")
        return None
    guid = selected["references"]["company_guid"]
    companies = [company for source in run["config"].get("source_catalog_snapshot", {}).get("sources", [])
                 if source.get("tool") == "tally" for company in source.get("snapshot", {}).get("companies", [])
                 if company.get("company_guid") == guid]
    if len(companies) != 1:
        raise ValueError("Confirm full same-company Source Discovery first.")
    company = companies[0]
    state = scalar(company["identity"].get("STATENAME")) or scalar(company["identity"].get("PRIORSTATENAME"))
    validated = validate_details(details, company_state=state, tax=record["data"].get("tax"))
    ledgers = [master["data"] for master in company["masters"]["records"] if master["type"] == "LEDGER"]
    gst_fields = {"GSTIN", "PARTYGSTIN", "LEDGSTIN"}
    if validated["gstin"] in native_values(company["identity"], gst_fields | {"GSTREGISTRATIONNUMBER"}):
        raise ValueError("Supplier GSTIN matches the destination company; verify the printed party roles.")
    if any(validated["gstin"] in native_values(master, gst_fields) for master in ledgers):
        raise ValueError("A discovered ledger already carries this GSTIN; resolve its identity first.")
    groups = {scalar(master["data"].get("@_NAME") or master["data"].get("NAME")): scalar(master["data"].get("PARENT"))
              for master in company["masters"]["records"] if master["type"] == "GROUP"}

    def creditor(master):
        parent = scalar(master.get("PARENT"))
        for _ in range(50):
            if _normal(parent) == "sundry creditors":
                return True
            if not parent or parent not in groups:
                return False
            parent = groups[parent]
        return False

    templates = []
    for master in ledgers:
        numbers = native_values(master, gst_fields)
        if not creditor(master) or len(numbers) != 1 or not scalar(master.get("GUID")):
            continue
        try:
            gstin(next(iter(numbers)))
        except ValueError:
            continue
        if validated["registration_type"] not in native_values(master, {"GSTREGISTRATIONTYPE", "LEDGSTREGISTRATIONTYPE"}):
            continue
        templates.append(master)
    if not templates:
        raise ValueError("No compatible GST-registered supplier template exists in this company.")
    master = min(templates, key=lambda m: (scalar(m.get("GUID")), scalar(m.get("@_NAME") or m.get("NAME"))))
    return {"version": 1, **validated, "applicable_from": record["data"]["date"], "template": {"name": scalar(master.get("@_NAME") or master.get("NAME")),
            "guid": scalar(master["GUID"]), "alter_id": scalar(master.get("ALTERID"))}}


def verified_supplier(master, expected):
    """Readback must retain every approved statutory and mailing value."""
    if not isinstance(master, dict) or not scalar(master.get("GUID")) or scalar(master.get("PARENT")) != "Sundry Creditors":
        return False
    fields = [({"GSTIN", "PARTYGSTIN", "LEDGSTIN"}, {expected["gstin"]}),
              ({"GSTREGISTRATIONTYPE", "LEDGSTREGISTRATIONTYPE"}, {expected["registration_type"]}),
              ({"STATENAME", "LEDSTATENAME", "STATE", "LEDSTATE"}, {expected["state"]}),
              ({"PLACEOFSUPPLY", "LEDPLACEOFSUPPLY"}, {expected["place_of_supply"]}),
              ({"PINCODE", "LEDPINCODE"}, {expected["pincode"]}),
              ({"ADDRESS"}, set(expected["address"]))]
    return all(native_values(master, keys) == values for keys, values in fields)
