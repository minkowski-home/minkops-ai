"""A bill's GST as Tally's GST returns read it.

TallyPrime counts a purchase in GSTR-3B and GSTR-2B only when the voucher itself carries the supplier's GST
details (GSTIN, registration type, state, country and place of supply) and each taxable line its taxability,
type of supply and rates, stated in the voucher. It derives neither from the masters for an imported voucher:
without them it files the purchase under Uncertain Transactions, with them it includes it (rehearsed on
TallyPrime in Educational mode, 22 October 2026). It also accepts a tax head the supply's states rule out, and a
line rate its tax does not bear, so the bill's GST is checked here before it is written.
"""
import re
from decimal import Decimal, InvalidOperation

from .supplier_gst import STATES, jurisdiction, native_values, scalar, state_name

# Each tax line's head, as Tally names its duty heads: TallyPrime 3+ first, earlier releases after.
DUTY_HEADS = {"cgst": {"cgst", "central tax"}, "sgst": {"sgst/utgst", "sgst", "utgst", "state tax", "ut tax"},
              "igst": {"igst", "integrated tax"}, "cess": {"cess"}}
HEAD_NAMES = {"cgst": "CGST", "sgst": "SGST", "igst": "IGST", "cess": "cess"}
# Tally spells these jurisdictions with an ampersand; the rest as the GST state code list does.
TALLY_STATES = {"Jammu and Kashmir": "Jammu & Kashmir", "Andaman and Nicobar Islands": "Andaman & Nicobar Islands",
                "Dadra and Nagar Haveli and Daman and Diu": "Dadra & Nagar Haveli and Daman & Diu"}
SUPPLIES = {"goods": "Goods", "services": "Services"}


def _canonical(name):
    """One state's name as the GST state code list spells it, or None."""
    try:
        return jurisdiction(name.replace("&", "and")) if name else None
    except ValueError:
        return None


def tally_state(canonical, *spelled):
    """The state as Tally spells it: as a master already does, else Tally's own spelling of it."""
    return next((s for s in spelled if s and _canonical(s) == canonical), TALLY_STATES.get(canonical, canonical))


def _entries(data, key):
    found = data.get(key)
    return [entry for entry in (found if isinstance(found, list) else [found]) if isinstance(entry, dict)]


def _current(entries, on):
    """The entry applicable on `on` (YYYYMMDD): the latest one applicable from no later than it."""
    dated = [(scalar(entry.get("APPLICABLEFROM")) or "0", entry) for entry in entries]
    applicable = [pair for pair in dated if pair[0] <= on]
    return max(applicable, key=lambda pair: pair[0])[1] if applicable else None


def registrations(view):
    """The company's GST registrations as {name, gstin, state}: none unless GST is switched on in Tally.

    TallyPrime keeps each registration as a tax unit; earlier releases keep one on the company itself.
    """
    identity = view["identity"]
    if scalar(identity.get("ISGSTON")).casefold() != "yes":
        return []
    found = []
    for record in view["masters"]["records"]:
        data = record["data"]
        number = scalar(data.get("GSTREGNUMBER")).upper()
        if record["type"] != "TAXUNIT" or not number or number[:2] not in STATES:
            continue
        spelled = native_values(data, {"STATE"})
        canonical = state_name(number[:2])
        found.append({"name": scalar(data.get("@_NAME") or data.get("NAME")), "gstin": number,
                      "state": tally_state(canonical, *spelled)})
    legacy = scalar(identity.get("GSTREGISTRATIONNUMBER")).upper()
    if not found and legacy[:2] in STATES:
        found.append({"name": None, "gstin": legacy,
                      "state": tally_state(state_name(legacy[:2]), scalar(identity.get("STATENAME")))})
    return found


def supplier_gstins(ledger):
    """Every GSTIN a supplier's ledger carries, over its registration history."""
    return {value.upper() for value in native_values(ledger, {"GSTIN", "PARTYGSTIN", "LEDGSTIN"})}


def supplier(ledger, on):
    """The supplier's GST registration as its ledger holds it on `on` (YYYYMMDD), or None when unregistered."""
    entry = _current(_entries(ledger, "LEDGSTREGDETAILS.LIST"), on)
    mailing = _current(_entries(ledger, "LEDMAILINGDETAILS.LIST"), on) or {}
    if entry is not None:
        number, kind = scalar(entry.get("GSTIN")).upper(), scalar(entry.get("GSTREGISTRATIONTYPE"))
    else:  # releases before TallyPrime 3 keep one registration on the ledger itself
        number = scalar(ledger.get("PARTYGSTIN") or ledger.get("LEDGSTIN")).upper()
        kind = scalar(ledger.get("GSTREGISTRATIONTYPE"))
    if number[:2] not in STATES:
        return None
    state = scalar(mailing.get("STATE")) or scalar(ledger.get("LEDSTATENAME"))
    return {"gstin": number, "registration_type": kind or "Regular",
            "state": tally_state(state_name(number[:2]), state),
            "country": scalar(mailing.get("COUNTRY")) or scalar(ledger.get("COUNTRYNAME")) or "India"}


def _percent(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return Decimal(0)


def tax_ledger_problem(ledger, head, rate):
    """Why this ledger cannot carry a tax line of this head and printed rate, or None.

    A ledger Tally marks as a GST duty states its head and, often, its rate; otherwise its name may. A line on
    the wrong one would be saved and counted as Tally reads the ledger, not as the bill charges it.
    """
    name = scalar(ledger.get("@_NAME") or ledger.get("NAME"))
    what = f"{HEAD_NAMES[head]} at {rate.normalize():f}%"
    if scalar(ledger.get("TAXTYPE")).casefold() == "gst":
        duty = scalar(ledger.get("GSTDUTYHEAD"))
        if duty and duty.casefold() not in DUTY_HEADS[head]:
            return f"{name} is a {duty} ledger in Tally, so it cannot carry {what}. Choose the {HEAD_NAMES[head]} ledger."
        configured = _percent(scalar(ledger.get("RATEOFTAXCALCULATION")))
        if configured and configured != rate:
            return (f"{name} is set to {configured.normalize():f}% in Tally, but the bill charges {what}. "
                    "Choose the ledger for this rate.")
        return None
    words = set(re.findall(r"[a-z]+", name.casefold()))
    named = {key for key in ("cgst", "sgst", "igst", "cess") if key in words or (key == "sgst" and "utgst" in words)}
    if named and head not in named:
        return f"{name} is named for {', '.join(HEAD_NAMES[k] for k in sorted(named))}, so it cannot carry {what}."
    stated = {_percent(p) for p in re.findall(r"(\d+(?:\.\d+)?)\s*%", name)}
    # A central or state ledger may be named for the combined rate it is half of.
    if stated and rate not in stated and not (head in ("cgst", "sgst") and rate * 2 in stated):
        return f"{name} is named for another rate, so it cannot carry {what}. Choose the ledger for this rate."
    return None


def heads_note(taxes, supplier_gstin, place):
    """A review note when the bill's tax heads are not the ones its states call for, or None.

    `place` is the place of supply's canonical state. CGST and SGST apply within one state and IGST between
    two; a supply from a special economic zone, or an import, is the usual exception a person can confirm.
    """
    if not taxes or not supplier_gstin or supplier_gstin[:2] not in STATES or place is None:
        return None
    origin = state_name(supplier_gstin[:2])
    heads = {tax["head"] for tax in taxes}
    if origin == place and "igst" in heads:
        return (f"The bill charges IGST, but its supplier and place of supply are both in {place}, where CGST and "
                "SGST apply. Check the bill before approving; Tally accepts the tax as printed.")
    if origin != place and heads & {"cgst", "sgst"}:
        return (f"The bill charges CGST and SGST, but its supplier is in {origin} and its place of supply is in "
                f"{place}, where IGST applies. Check the bill before approving; Tally accepts the tax as printed.")
    return None


def place_of_supply(document, registration, company_state):
    """The supply's place as a canonical state: as the bill prints it, else where it is addressed."""
    printed = document.get("place_of_supply")
    if printed:
        found = _canonical(printed)
        if found is None:
            return None, "The place of supply must name one Indian state as the bill prints it, such as Delhi (07)."
        return found, None
    if registration:
        return state_name(registration["gstin"][:2]), None
    return _canonical(company_state), None


def line_rates(lines, taxes):
    """Each taxable line's combined GST rate, as {index: Decimal}, checked against the bill's tax lines.

    `lines` are (index, amount_cents, stated rate or None) for the taxable lines. The tax lines settle what each
    rate taxes: CGST at r on a value is 2r on it, IGST at R is R. A bill at one rate gives it to every line
    that does not say otherwise; at several, each line says its own. Raises ValueError with the reason.
    """
    groups = {}
    for tax in taxes:
        if tax["head"] in ("cgst", "igst"):
            combined = tax["rate"] * 2 if tax["head"] == "cgst" else tax["rate"]
            groups[combined] = groups.get(combined, 0) + tax["taxable_cents"]
    if not groups:
        return {}
    stated = {index: Decimal(str(rate)) for index, _, rate in lines if rate is not None}
    if len(groups) > 1 and len(stated) < len(lines):
        raise ValueError("The bill taxes its lines at more than one GST rate: give each taxable line its gst_rate.")
    only = next(iter(groups)) if len(groups) == 1 else None
    rates = {index: stated.get(index, only) for index, _, _ in lines}
    for rate, taxable in groups.items():
        reached = sum(amount for index, amount, _ in lines if rates[index] == rate)
        if reached != taxable:
            raise ValueError(f"The lines taxed at {rate.normalize():f}% come to {reached / 100:.2f}, but the bill's "
                             f"tax at that rate is on {taxable / 100:.2f}. Give each taxable line its gst_rate; "
                             "an untaxed line is 0.")
    unknown = {rate for rate in rates.values() if rate and rate not in groups}
    if unknown:
        raise ValueError("A line's gst_rate must be a rate the bill's tax lines charge, or 0.")
    return rates


def line_details(rate, supply, cess):
    """What a taxable line states in the voucher for Tally's returns: taxability, supply and every head's rate."""
    half = rate / 2
    return {"taxability": "Taxable", "supply": supply,
            "rates": {"cgst": f"{half.normalize():f}", "sgst": f"{half.normalize():f}", "igst": f"{rate.normalize():f}",
                      "cess": f"{cess.normalize():f}"}}
