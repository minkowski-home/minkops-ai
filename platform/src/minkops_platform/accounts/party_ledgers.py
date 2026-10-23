"""Party ledgers created on a person's approval, in Tally's own terms (plan protocol 8).

A bill's new supplier, or the other side of a bank row, is created only by a person's decision, from a form laid out
like Tally's ledger creation: its name; the group it goes under; whether its balances are kept bill by bill, and its
default credit period; its mailing details; its GST registration. The form starts from what the source prints and how
the company keeps its books (practice.py), and the person confirms or edits it. The server validates it here; the
companion writes exactly these fields and reads the ledger back (connectors/desktop/src/tally.js), and a ledger whose
readback differs from the plan is never used.

Only party ledgers are created. Expense heads, tax ledgers and bank ledgers are a client's chart-of-accounts and
statutory decisions: work that needs one holds, and a recheck finds it once a person has made it in Tally.
"""

import re

from . import mirror, supplier_gst

PROTOCOL = 8
# The companion that writes ledger plans: an older one is asked to update before a ledger is created.
COMPANION = (0, 11, 5)
# Where each kind of party ledger may go, by Tally's reserved group names, with their sub-groups. A bank row's other
# side is never put under bank, tax, capital, stock or expense groups.
GROUPS = {"supplier": ("Sundry Creditors",),
          "counterparty": ("Sundry Creditors", "Sundry Debtors", "Loans & Advances (Asset)", "Current Liabilities")}
REGISTRATIONS = ("Regular", "Composition", "Unregistered")
# Tally's dated master fields, which newer releases export; a company whose ledgers carry none uses the older ones.
DATED = {"LEDMAILINGDETAILS.LIST", "LEDGSTREGDETAILS.LIST"}
CONTROL = re.compile(r"[\x00-\x1f]")


def groups(view, kind, used=()):
    """The groups a ledger of this kind may go under in a company: `used` first (the groups its books already put such
    ledgers under, most used first), then the reserved groups, then their sub-groups by name."""
    parents = {mirror.text(r["data"].get("@_NAME")) or mirror.text(r["data"].get("NAME")): mirror.text(r["data"].get("PARENT"))
               for r in view["masters"]["records"] if r["type"] == "GROUP"}
    tree = {mirror.normalized(name): parent for name, parent in parents.items()}
    under = [name for name in sorted(parents) if name not in GROUPS[kind]
             and mirror.under(parents[name], GROUPS[kind], tree)]
    allowed = [*GROUPS[kind], *under]
    return list(dict.fromkeys([*(group for group in used if group in allowed), *allowed]))


def form(view, *, kind, name, printed=None, billwise=None, used=()):
    """The form a person confirms before a party ledger is created, filled from the source and the company's books.

    `printed` is what a bill prints of its supplier (GSTIN, registration type, state, address, PIN). `billwise` is the
    share of the company's suppliers kept bill by bill: the form follows most of them, and with no supplier yet it
    leaves the choice to the person, once. `used` are the groups the company's bank counterparties sit under, most used
    first; a supplier goes under Sundry Creditors unless the person moves it, and a counterparty starts on the group
    its books use most, or on none when they are too new to say.
    """
    printed = printed or {}
    try:
        number = supplier_gst.gstin(printed.get("gstin"))
    except ValueError:
        number = None
    try:
        state = supplier_gst.jurisdiction(printed.get("state")) if printed.get("state") else None
    except ValueError:
        state = None
    registration = printed.get("registration_type") if printed.get("registration_type") in REGISTRATIONS[:2] else None
    options = groups(view, kind, used)
    return {"name": name, "under": options[0] if kind == "supplier" or used else None, "groups": options,
            "billwise": None if billwise is None else billwise >= 0.5, "credit_period": None,
            "mailing": {"address": [str(line) for line in (printed.get("address") or [])][:4],
                        "state": state or (supplier_gst.state_name(number[:2]) if number else None), "country": "India",
                        "pincode": printed.get("pincode") or None},
            "gst": {"registration_type": registration or ("Regular" if number else "Unregistered"), "gstin": number}}


def _text(value, what, limit):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit or CONTROL.search(value):
        raise ValueError(f"{what} must be 1 to {limit} characters of plain text.")
    return value.strip()


def _mailing(value):
    """Mailing details as Tally keeps them, or None when the form gives none."""
    value = value or {}
    address = [line.strip() for line in value.get("address") or [] if isinstance(line, str) and line.strip()]
    if len(address) > 4 or any(len(line) > 250 or CONTROL.search(line) for line in address):
        raise ValueError("Give at most four address lines of plain text.")
    state = value.get("state") or None
    if state:
        try:
            state = supplier_gst.jurisdiction(state)
        except ValueError:
            raise ValueError(f"{state} is not a state or union territory Tally knows.") from None
    pincode = (value.get("pincode") or "").strip() or None
    if pincode and not re.fullmatch(r"[1-9][0-9]{5}", pincode):
        raise ValueError("A PIN code is six digits.")
    if not (address or state or pincode):
        return None
    return {"address": address, "state": state, "country": "India", "pincode": pincode}


def _gst(value, mailing, view):
    """GST registration details as Tally keeps them, or None for a party registered under none."""
    value = value or {}
    registration = value.get("registration_type") or "Unregistered"
    if registration not in REGISTRATIONS:
        raise ValueError("Choose a GST registration type: Regular, Composition or Unregistered.")
    if registration == "Unregistered":
        if value.get("gstin"):
            raise ValueError("An unregistered party has no GSTIN; choose its registration type.")
        return None
    try:
        number = supplier_gst.gstin(value.get("gstin"))
    except ValueError as error:
        raise ValueError(f"The GSTIN is not valid: {error}") from None
    state = supplier_gst.state_name(number[:2])
    if mailing and mailing["state"] and mailing["state"] != state:
        raise ValueError(f"The GSTIN is registered in {state}, not {mailing['state']}.")
    fields = {"GSTIN", "PARTYGSTIN", "LEDGSTIN", "GSTREGISTRATIONNUMBER", "GSTREGNUMBER"}
    if number in supplier_gst.native_values(view["identity"], fields) or any(
            number in supplier_gst.native_values(r["data"], fields) for r in view["masters"]["records"]
            if r["type"] in ("LEDGER", "TAXUNIT")):
        raise ValueError(f"{number} is already in this company's books: choose that ledger instead.")
    return {"registration_type": registration, "gstin": number, "state": state}


def plan(view, company, submitted, *, kind):
    """The native plan for the ledger a person approved, from their form; ValueError names what to correct.

    The name must be no ledger's or group's already; the group one this kind of ledger may go under; a credit period
    0 to 365 days, for a ledger kept bill by bill; a GSTIN valid, in the state given, and on no other master.
    """
    if not isinstance(submitted, dict):
        raise ValueError("Fill in the new ledger's details.")
    name = _text(submitted.get("name"), "The ledger's name", 200)
    taken = {mirror.normalized(mirror.text(r["data"].get("@_NAME")) or mirror.text(r["data"].get("NAME")))
             for r in view["masters"]["records"] if r["type"] in ("LEDGER", "GROUP")}
    if mirror.normalized(name) in taken:
        raise ValueError(f"{name} is already a ledger or group in {company['name']}: choose it, or name the new "
                         "ledger otherwise.")
    under = submitted.get("under")
    if under not in groups(view, kind):
        raise ValueError(f"Choose a group a {'supplier' if kind == 'supplier' else 'party'} ledger may go under: "
                         f"{', '.join(GROUPS[kind])} or one of their sub-groups.")
    billwise, period = submitted.get("billwise"), submitted.get("credit_period")
    if type(billwise) is not bool:
        raise ValueError("Choose whether the ledger's balances are kept bill by bill.")
    if period is not None and (type(period) is not int or not 0 <= period <= 365 or not billwise):
        raise ValueError("A default credit period is 0 to 365 days, for a ledger whose balances are kept bill by bill.")
    mailing = _mailing(submitted.get("mailing"))
    gst = _gst(submitted.get("gst"), mailing, view)
    dated = any(r["type"] == "LEDGER" and DATED & set(r["data"]) for r in view["masters"]["records"])
    applicable = company["books_from"].isoformat()
    return {"kind": "ledger", "protocol": PROTOCOL, "company": company["name"], "company_guid": company["guid"],
            "shape": "dated" if dated else "legacy",
            "ledger": {"name": name, "under": under, "billwise": billwise, "credit_period": period or None,
                       "mailing": mailing, "gst": {**gst, "applicable_from": applicable} if gst else None,
                       "applicable_from": applicable},
            "destination_key": f"ledger:{company['guid']}",
            "identity": {"hash": gst["gstin"] if gst else mirror.normalized(name)}}


def _period(value):
    digits = re.match(r"\s*(\d+)", supplier_gst.scalar(value))
    return int(digits.group(1)) if digits and int(digits.group(1)) else None


def verified(plan, receipt):
    """The created ledger as Tally holds it, from the companion's readback, or why it cannot be trusted: (master, None)
    or (None, problem). Every field the plan wrote must read back as written. The whole master is kept, not only its
    identity: the entry made with it is checked against its bill-by-bill setting and GST registration."""
    if receipt.get("outcome") == "attention":
        return None, str(receipt.get("message") or "") or "The ledger could not be created and verified in Tally."
    if receipt.get("company_guid") != plan["company_guid"]:
        return None, "Tally answered for another company, so the ledger was not verified."
    master, ledger = receipt.get("ledger"), plan["ledger"]
    scalar = supplier_gst.scalar
    if not isinstance(master, dict) or not scalar(master.get("GUID")) or mirror.normalized(
            scalar(master.get("@_NAME") or master.get("NAME"))) != mirror.normalized(ledger["name"]):
        return None, f"Tally does not show the ledger {ledger['name']}."
    values = lambda keys: supplier_gst.native_values(master, keys)  # noqa: E731
    differs = []
    if scalar(master.get("PARENT")) != ledger["under"]:
        differs.append(f"it is under {scalar(master.get('PARENT')) or 'no group'}")
    if (scalar(master.get("ISBILLWISEON")).casefold() == "yes") != ledger["billwise"]:
        differs.append("its bill-by-bill setting")
    if _period(master.get("BILLCREDITPERIOD")) != ledger["credit_period"]:
        differs.append("its credit period")
    mailing, gst = ledger["mailing"] or {}, ledger["gst"] or {}
    for keys, wanted, what in (
            ({"ADDRESS"}, set(mailing.get("address") or []), "its address"),
            ({"STATENAME", "LEDSTATENAME", "STATE", "LEDSTATE"}, {mailing["state"]} if mailing.get("state") else set(),
             "its state"),
            ({"PINCODE", "LEDPINCODE"}, {mailing["pincode"]} if mailing.get("pincode") else set(), "its PIN code"),
            ({"GSTIN", "PARTYGSTIN", "LEDGSTIN"}, {gst["gstin"]} if gst else set(), "its GSTIN"),
            ({"GSTREGISTRATIONTYPE", "LEDGSTREGISTRATIONTYPE"}, {gst["registration_type"]} if gst else set(),
             "its GST registration type")):
        if wanted and values(keys) != wanted:
            differs.append(what)
    if differs:
        return None, (f"The ledger {ledger['name']} in Tally differs from what was approved: {', '.join(differs)}. "
                      "Review it there.")
    return {**mirror.compact(master), "@_NAME": scalar(master.get("@_NAME") or master.get("NAME"))}, None
