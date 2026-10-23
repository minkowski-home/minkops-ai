"""A scripted model that cites masters as a session must: it looks them up, then proposes them by the
references its lookups and its header gave it.

Tests write proposals as the checks read them, by GUID (`ledger_guid`, `company_guid`, ...); these helpers
turn such a call into the rounds a model takes to make it.
"""

import json
import re

KINDS = {"COMPANY": "company", "LEDGER": "ledger", "VOUCHERTYPE": "voucher_type", "STOCKITEM": "stock_item",
         "GODOWN": "godown", "COSTCENTRE": "cost_centre"}
TOOLS = {"find_company": "company", "find_ledger": "ledger", "voucher_types": "voucher_type",
         "find_stock_item": "stock_item", "godowns": "godown", "cost_centres": "cost_centre"}
FAMILIES = ["payment", "receipt", "contra", "purchase", "journal", "debit note", "credit note", "sales"]


def named(records):
    """{guid: (kind, name)} for a fixture's native masters, its company included."""
    out = {}
    for record in records:
        if record["type"] in KINDS:
            data = record["data"]
            out[data["GUID"]] = (KINDS[record["type"]], data.get("@_NAME") or data.get("NAME"))
    return out


def issued(answers, session):
    """Every reference the session was given: its header's companies, as {("company", name): ref}, and each
    successful lookup's masters, as {(kind, name, company ref): ref}."""
    refs = {}
    header = session.content[0]["text"].splitlines()[0]
    companies = json.loads(header).get("companies")
    if isinstance(companies, list):  # a bill session lists its companies
        refs.update({("company", c["name"]): c["ref"] for c in companies})
    elif isinstance(companies, str):  # a statement chunk names them in one line: "Name (C1); Other (C2)"
        refs.update({("company", name): ref for name, ref in re.findall(r"(.+?) \(([A-Z]\d+)\)(?:; |$)", companies)})
    for answer in answers:
        if not (answer["success"] and answer["name"] in TOOLS):
            continue
        kind = TOOLS[answer["name"]]
        for found in _found(json.loads(answer["text"])):
            if "company_ref" in found:
                refs[("company", found["company"])] = found["company_ref"]
            if "ref" in found and "name" in found:
                if kind == "company":
                    refs[("company", found["name"])] = found["ref"]
                else:
                    refs[(kind, found["name"], found.get("company_ref") or answer["arguments"].get("company"))] = found["ref"]
    return refs


def _found(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _found(item)
    elif isinstance(value, list):
        for item in value:
            yield from _found(item)


def cited(value, names, refs, company=None):
    """`value`, written by GUID, as a session proposes it: each `*_guid` field becomes `*` with its reference,
    a master's taken in the company the enclosing proposal names. A cost category is left out: it follows from
    the cost centre."""
    if isinstance(value, list):
        return [cited(item, names, refs, company) for item in value]
    if not isinstance(value, dict):
        return value
    if value.get("company_guid"):
        company = refs[names[value["company_guid"]]]
    out = {}
    for key, item in value.items():
        if key == "cost_category_guid":
            continue
        if key == "company_guid":
            out["company"] = company if item else None
        elif key.endswith("_guid"):
            out[key.removesuffix("_guid")] = None if item is None else refs[(*names[item], company)]
        else:
            out[key] = cited(item, names, refs, company)
    return out


def _masters(value, company=None):
    """Each master a call cites, as (the company its proposal names, the master's GUID)."""
    if isinstance(value, dict):
        company = value.get("company_guid", company)
        for key, item in value.items():
            if key.endswith("_guid") and key not in ("company_guid", "cost_category_guid"):
                if item is not None:
                    yield company, item
            else:
                yield from _masters(item, company)
    elif isinstance(value, list):
        for item in value:
            yield from _masters(item, company)


def lookups(names, guids, company):
    """The lookups a model makes, in the company it names by `company`, to be given these masters' references."""
    wanted = {}
    for guid in dict.fromkeys(guids):
        kind, name = names[guid]
        wanted.setdefault(kind, []).append(name)
    calls = []
    if wanted.get("ledger"):
        calls.append(("find_ledger", {"company": company, "subjects": wanted["ledger"]}))
    if wanted.get("voucher_type"):
        calls.append(("voucher_types", {"company": company, "families": FAMILIES}))
    if wanted.get("stock_item"):
        calls.append(("find_stock_item", {"company": company, "subjects": wanted["stock_item"]}))
    if wanted.get("godown"):
        calls.append(("godowns", {"company": company}))
    if wanted.get("cost_centre"):
        calls.append(("cost_centres", {"company": company, "subjects": wanted["cost_centre"]}))
    return calls


def looked_up(tool, arguments, names):
    """The rounds of a model that looks up every master this call cites, in the company each of its proposals
    names, then makes the call by the references it was given. `arguments` are written by GUID."""
    by_company = {}
    for company, guid in _masters(arguments):
        by_company.setdefault(company, []).append(guid)

    def lookup(answers, session):
        refs = issued(answers, session)
        return [call for company, guids in by_company.items() for call in lookups(names, guids, refs[names[company]])]

    return [lookup, by_reference(tool, arguments, names)] if by_company else [by_reference(tool, arguments, names)]


def by_reference(tool, arguments, names):
    """The round that makes this call, written by GUID, by the references the session was given so far."""
    return lambda answers, session: [(tool, cited(arguments, names, issued(answers, session)))]


def everything(names, company="C1"):
    """A round that looks up every master the fixture names in one company, so later rounds may cite any."""
    masters = [guid for guid, (kind, _) in names.items() if kind != "company"]
    return lambda answers, session: lookups(names, masters, company)


def referring(round_, names):
    """A scripted round written by GUID, made by the references the session was given: proposals cite them, and
    lookups name their company, and any ledger already given, by reference."""
    def made(answers, session):
        refs = issued(answers, session)
        calls = round_(answers, session) if callable(round_) else round_
        return [(tool, cited(arguments, names, refs) if tool == "propose" else _asked(arguments, names, refs))
                for tool, arguments in calls]
    return made


def _asked(arguments, names, refs):
    out = dict(arguments)
    if out.get("company") in names:
        out["company"] = refs[names[out["company"]]]
    if "ledgers" in out:
        out["ledgers"] = [refs.get((*names[ledger], out.get("company")), names[ledger][1]) if ledger in names else ledger
                          for ledger in out["ledgers"]]
    return out
