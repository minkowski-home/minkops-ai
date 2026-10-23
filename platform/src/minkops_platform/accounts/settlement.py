"""Bill-wise settlement: the bills a ledger has open, and which of them a bank row settles.

A ledger that keeps balances bill by bill (Tally's ISBILLWISEON) carries each
amount under a bill: a purchase opens one with a New Ref, a payment settles it
with an Agst Ref, and money paid or received ahead of its bill is an Advance or
On Account. A statement row to such a ledger carries that allocation on its
counter line (plan protocol 6).

Open bills are read from the run's pinned books (mirror.open_bills), less what
the run's other rows already settle, so two rows never settle one balance
twice; `lock` serialises those claims within a run.

Which bills a payment settles is a judgment the books seldom make for certain.
An allocation is written without a person's choice only when it is the one
evident allocation: the narration names its bills, its bills are the only open
bills whose balances add up to the amount, or nothing is open to settle.
Anything else holds as `bill_unresolved`, with the allocations `offers` lists
for one click.

Allocations are lists of {type, name, amount_cents}: Agst Ref and Advance name
their bill, On Account names none. Amounts are positive; the line's side signs
them, as the plan does.
"""

import re
from itertools import combinations

from . import mirror
from .vouchers import rupees

# The references a bank row makes: it settles a bill, or pays ahead of one. New Ref opens bills, as purchases do.
TYPES = ("Agst Ref", "Advance", "On Account")
# An exact match combines at most this many bills, and three only among this many open ones.
EXACT, SEARCH = 3, 60


class Unresolved(Exception):
    """An allocation the books leave to a person: why, and the choices offered."""

    def __init__(self, reason, choices):
        super().__init__(reason)
        self.reason, self.choices = reason, choices


def lock(connection, run):
    """Serialise bill claims within a run until the transaction ends; take it after any record locks."""
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"settlement:{run['id']}",))


def open_bills(connection, run, company, ledger, *, record=None):
    """A ledger's bills with a balance at the run's pinned version, less what the run's other rows settle.

    `company` carries its pinned `version`. `record` is the row being settled:
    neither it nor its repeats in overlapping statements, the same bank
    transaction, count against it. Each repeated transaction counts once.
    """
    identity = (record["facts"] or {}).get("identity") if record else None
    claims = {row["name"]: row["cents"] for row in connection.execute(
        """SELECT bill->>'name' AS name,
                  sum(CASE WHEN (claim.facts->>'amount_cents')::bigint < 0 THEN -1 ELSE 1 END
                      * (bill->>'amount_cents')::bigint)::bigint AS cents
           FROM (SELECT DISTINCT ON (coalesce(r.facts->>'identity', r.id::text)) r.facts, r.proposal
                 FROM run_records r
                 WHERE r.run_id=%(run)s AND r.company_id=%(company)s
                     AND r.status IN ('proposed','held','approved','writing','saved')
                     AND r.proposal->'resolved'->'data'->>'counter_ledger' = %(ledger)s
                     AND jsonb_typeof(r.proposal->'resolved'->'bills') = 'array'
                     AND r.id IS DISTINCT FROM %(self)s::uuid AND (r.facts->>'identity') IS DISTINCT FROM %(identity)s
                 ORDER BY coalesce(r.facts->>'identity', r.id::text), r.id) AS claim,
                jsonb_array_elements(claim.proposal->'resolved'->'bills') AS bill
           WHERE bill->>'type' = 'Agst Ref' GROUP BY bill->>'name'""",
        {"run": run["id"], "company": company["id"], "ledger": ledger, "self": record["id"] if record else None,
         "identity": identity}).fetchall()}
    bills = []
    for bill in mirror.open_bills(connection, company["id"], company["version"], [ledger]):
        balance = bill["balance_cents"] + claims.get(bill["name"], 0)
        if balance:
            bills.append({**bill, "balance_cents": balance})
    return bills


def allocate(bills, *, amount_cents, payment, text, proposed=None):
    """The counter line's bills for a row of this amount: the one evident allocation.

    `bills` are the ledger's open bills (open_bills). A payment settles credit
    balances, a receipt debit ones. `text` is the row's narration and
    reference; `proposed` is the session's allocation, or None to let the books
    decide. Raises ValueError for an allocation that cannot be written, and
    Unresolved when the choice is a person's.
    """
    dues = _dues(bills, payment)
    if proposed is not None:
        check(bills, proposed, amount_cents=amount_cents, payment=payment)
    if not dues:
        return proposed if proposed is not None else [_on_account(amount_cents)]
    named = [due for due in dues if _named(due["name"], text)]
    exact = _exact(dues, amount_cents)
    candidates = _candidates(dues, amount_cents, named, exact, proposed)
    evident = [allocation for allocation in candidates if _evident(allocation, dues, text, exact)]
    if len(evident) == 1 and (proposed is None or _key(evident[0]) == _key(proposed)):
        return evident[0]
    raise Unresolved(_why(named, exact, evident),
                     [{"label": _label(allocation, dues), "bills": allocation} for allocation in candidates])


def offers(bills, *, amount_cents, payment, text):
    """Every allocation a person may choose from for this row, as {label, bills}."""
    dues = _dues(bills, payment)
    if not dues:
        return [{"label": _label([_on_account(amount_cents)], dues), "bills": [_on_account(amount_cents)]}]
    named = [due for due in dues if _named(due["name"], text)]
    return [{"label": _label(allocation, dues), "bills": allocation}
            for allocation in _candidates(dues, amount_cents, named, _exact(dues, amount_cents), None)]


def check(bills, allocation, *, amount_cents, payment):
    """Refuse an allocation the open bills cannot take, saying why."""
    dues = {due["name"]: due["due_cents"] for due in _dues(bills, payment)}
    known, seen = {bill["name"] for bill in bills}, set()
    for bill in allocation:
        kind, name, cents = bill["type"], bill.get("name"), bill["amount_cents"]
        if kind == "Agst Ref":
            if name not in dues:
                raise ValueError(f"{name} is not an open bill this {'payment' if payment else 'receipt'} can settle; "
                                 "open_bills lists the bills that are.")
            if cents > dues[name]:
                raise ValueError(f"{name} has {rupees(dues[name])} open, less than {rupees(cents)}.")
        elif kind == "Advance":
            if not name or name in known:
                raise ValueError("An Advance names a new bill, such as the payment's reference"
                                 + (f"; {name} is already open." if name else "."))
        elif kind == "On Account":
            if name is not None:
                raise ValueError("On Account names no bill.")
        else:
            raise ValueError("A bank row settles bills with Agst Ref, or pays ahead of one with Advance or On "
                             "Account; New Ref opens a bill.")
        if (name or kind) in seen:
            raise ValueError(f"{name or kind} is named twice.")
        seen.add(name or kind)
    if sum(bill["amount_cents"] for bill in allocation) != amount_cents:
        raise ValueError(f"The bills must add up to the counter line's {rupees(amount_cents)}.")


def _dues(bills, payment):
    """The bills a row settles in its direction, each with what it has open."""
    return [{**bill, "due_cents": bill["balance_cents"] if payment else -bill["balance_cents"]}
            for bill in bills if bill["balance_cents"] and (bill["balance_cents"] > 0) == payment]


def _named(name, text):
    """Whether the narration or reference names this bill: its letters and digits, as consecutive words."""
    key = re.sub(r"[^0-9A-Z]", "", name.upper())
    if len(key) < 3 or not any(char.isdigit() for char in key):
        return False
    words = re.findall(r"[0-9A-Z]+", text.upper())
    for start in range(len(words)):
        joined = ""
        for word in words[start:]:
            joined += word
            if joined == key:
                return True
            if not key.startswith(joined):
                break
    return False


def _exact(dues, amount):
    """At most two sets of open bills, oldest first, whose balances add up to the amount exactly."""
    found = []
    for size in range(1, EXACT + 1):
        if size > 2 and len(dues) > SEARCH:
            break
        for subset in combinations(dues, size):
            if sum(due["due_cents"] for due in subset) == amount:
                found.append([{"type": "Agst Ref", "name": due["name"], "amount_cents": due["due_cents"]}
                              for due in subset])
                if len(found) == 2:
                    return found
    return found


def _fill(dues, amount):
    """Each bill in full, oldest first, until the amount runs out; what is left goes on account."""
    allocation, left = [], amount
    for due in dues:
        if not left:
            break
        taken = min(due["due_cents"], left)
        allocation.append({"type": "Agst Ref", "name": due["name"], "amount_cents": taken})
        left -= taken
    return [*allocation, _on_account(left)] if left else allocation


def _on_account(amount):
    return {"type": "On Account", "amount_cents": amount}


def _candidates(dues, amount, named, exact, proposed):
    """The session's allocation, the named bills, exact matches, oldest first and on account; each once."""
    candidates, seen = [], set()
    for allocation in ([proposed] if proposed is not None else []) + ([_fill(named, amount)] if named else []) + [
            *exact, _fill(dues, amount), [_on_account(amount)]]:
        if _key(allocation) not in seen:
            seen.add(_key(allocation))
            candidates.append(allocation)
    return candidates


def _evident(allocation, dues, text, exact):
    """Named bills settled, with any rest only when nothing else stays open, or the only exact match."""
    against = [bill for bill in allocation if bill["type"] == "Agst Ref"]
    if against and all(_named(bill["name"], text) for bill in against):
        taken = {bill["name"]: bill["amount_cents"] for bill in against}
        return len(against) == len(allocation) or all(taken.get(due["name"]) == due["due_cents"] for due in dues)
    return len(exact) == 1 and _key(allocation) == _key(exact[0])


def _key(allocation):
    return tuple(sorted((bill["type"], bill.get("name") or "", bill["amount_cents"]) for bill in allocation))


def _why(named, exact, evident):
    names = _names([due["name"] for due in named]) if named else ""
    if named and len(evident) > 1:
        return f"The narration names {names}, but other open bills add up to this amount."
    if len(evident) == 1:
        settled = [bill["name"] for bill in evident[0] if bill["type"] == "Agst Ref"]
        if named and settled == [due["name"] for due in named]:
            return f"The narration names {names}, but the proposal settles it otherwise."
        return (f"Only {_names(settled)} {'adds' if len(settled) == 1 else 'add'} up to this amount, but the proposal "
                "settles it otherwise.")
    if named:
        return f"The narration names {names}, but not where the rest of this amount goes."
    if len(exact) > 1:
        return "Several sets of open bills add up to this amount, and the narration names none of them."
    return "No set of open bills adds up to this amount, and the narration names none of them."


def _label(allocation, dues):
    """An allocation as a person reads it on its button."""
    open_ = {due["name"]: due["due_cents"] for due in dues}
    against = [bill for bill in allocation if bill["type"] == "Agst Ref"]
    full = [bill["name"] for bill in against if bill["amount_cents"] == open_.get(bill["name"])]
    parts = ([f"{_names(full)} in full"] if full else []) + [
        f"{rupees(bill['amount_cents'])} of {bill['name']} ({rupees(open_[bill['name']])} open)"
        for bill in against if bill["amount_cents"] != open_.get(bill["name"])]
    rest = [f"{rupees(bill['amount_cents'])} on account" if bill["type"] == "On Account"
            else f"{rupees(bill['amount_cents'])} as Advance {bill['name']}"
            for bill in allocation if bill["type"] != "Agst Ref"]
    if not parts:
        only = allocation[0]
        return ("On account, settling no bill" if only["type"] == "On Account"
                else f"Advance {only['name']}, settling no bill")
    return f"Settle {_joined(parts)}" + (f", and {_joined(rest)}" if rest else "")


def _names(names):
    return _joined(names if len(names) <= 3 else [*names[:3], f"{len(names) - 3} more"])


def _joined(items):
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"
