"""Purchase voucher types come from discovered masters, never a hard-coded name.

Practices book purchases under their own types (*Purchase GST*, *Purchase -
Local*). A type's base is Tally's predefined type: its RESERVEDNAME when Tally
marks it predefined, otherwise the base of its PARENT, followed by name. The
companion applies the same rule to live masters before every write
(connectors/desktop/src/tally.js), so selection here and the duplicate checks
there always agree on which vouchers record a purchase.
"""

from .client_context import text

PURCHASE = "purchase"
MAX_CHAIN = 10


def _name(record):
    return (text(record.get("@_NAME")) or text(record.get("NAME")) or "").strip()


def base_types(records):
    """Each type's predefined base, by casefolded name; None for a broken chain."""
    by_name = {_name(r).casefold(): r for r in records if _name(r)}

    def resolve(name, depth):
        record = by_name.get(name.casefold())
        if record is None:
            return name  # A predefined base the export did not include.
        reserved = (text(record.get("@_RESERVEDNAME")) or "").strip()
        if reserved:
            return reserved
        parent = (text(record.get("PARENT")) or "").strip()
        if not parent or parent.casefold() == name.casefold():
            return _name(record)
        return None if depth >= MAX_CHAIN else resolve(parent, depth + 1)

    return {key: resolve(_name(record), 0) for key, record in by_name.items()}


def candidates(records, vouchers):
    """Active purchase-family types with how often discovered vouchers used them."""
    bases = base_types(records)
    used = {}
    for voucher in vouchers:
        kind = (text(voucher.get("data", {}).get("VOUCHERTYPENAME")) or "").strip().casefold()
        used[kind] = used.get(kind, 0) + 1
    found = []
    for record in records:
        name = _name(record)
        base = bases.get(name.casefold())
        if not name or not base or base.casefold() != PURCHASE:
            continue
        if (text(record.get("ISACTIVE")) or "").strip().casefold() == "no":
            continue
        found.append({
            "name": name,
            "guid": text(record.get("GUID")),
            "used": used.get(name.casefold(), 0),
            "identity": {"NAME": name, "GUID": text(record.get("GUID")),
                         "PARENT": text(record.get("PARENT")), "ALTERID": text(record.get("ALTERID"))},
        })
    return sorted(found, key=lambda c: c["name"].casefold())


def summary(records, vouchers):
    """What the launch screen offers: candidates and an unambiguous default."""
    found = candidates(records, vouchers)
    ranked = sorted(found, key=lambda c: -c["used"])
    default = None
    if len(found) == 1:
        default = found[0]["guid"]
    elif ranked and ranked[0]["used"] and (len(ranked) == 1 or ranked[0]["used"] > ranked[1]["used"]):
        default = ranked[0]["guid"]
    return {"candidates": [{k: c[k] for k in ("name", "guid", "used")} for c in found], "default": default}


def pin(company, found, choice):
    """The identity a run writes with, or a ValueError naming the user's action."""
    name = company["company"]
    if choice is not None:
        match = [c for c in found if c["guid"] == choice]
        if len(match) != 1:
            raise ValueError(
                f"The chosen voucher type is no longer an active purchase voucher type in {name}. "
                "Refresh Source Discovery, then choose again.")
        return match[0]["identity"]
    if len(found) == 1:
        return found[0]["identity"]
    if not found:
        raise ValueError(f"{name} has no active purchase voucher type in Tally. Activate or create one, "
                         "then refresh Source Discovery.")
    raise ValueError(f"Choose the purchase voucher type for {name} when starting the run.")


def apply_choices(scope, choices):
    """Pin a voucher type per company for this run.

    A locked run needs its company resolved before it starts. An inferred run
    records unresolved companies so only bills routed to them hold.
    """
    companies = {c["references"]["company_guid"]: c for c in scope["companies"]}
    if (not isinstance(choices, dict)
            or any(k not in companies or not isinstance(v, str) or not 1 <= len(v) <= 200
                   for k, v in choices.items())):
        raise ValueError("Choose a valid purchase voucher type for each company.")
    locked = scope.get("company_mode") == "locked"
    for guid, company in companies.items():
        if locked and guid != scope.get("locked_company_guid"):
            continue
        try:
            company["voucher_type"] = pin(company, company.get("purchase_voucher_types", []), choices.get(guid))
        except ValueError as error:
            if locked:
                raise
            company["voucher_type_error"] = str(error)
    scope["voucher_type_version"] = 1
    return scope
