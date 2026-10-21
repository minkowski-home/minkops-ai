"""Company-scoped bill sessions: route each bill first, then send one company's evidence.

A client with many open companies cannot send every company's discovery to
every bill session (hosted inputs are bounded). A short triage stage reads the
bills against a compact company directory; each bill's posting session then
receives only its routed company's masters (never sampled) and as much of that
company's history as fits. Routing is the AI's; the year-split date check that
can move a bill to its sibling company is deterministic and explained.
"""

import copy
from datetime import date, timedelta

from psycopg.types.json import Jsonb

from minkops_platform.runtime.environments import SESSION_BYTE_LIMIT

from .client_context import books_beginning, context_assets, text

TRIAGE_FILES = 40
TRIAGE_BYTES = 7_500_000
GST_FIELDS = {"GSTIN", "PARTYGSTIN", "LEDGSTIN", "GSTREGISTRATIONNUMBER", "GSTREGNUMBER", "TAXREGISTRATION"}


def _companies(catalog):
    return [c for s in catalog.get("sources", []) if s.get("tool") == "tally"
            for c in (s.get("snapshot") or {}).get("companies", [])]


def directory(catalog):
    """What triage needs to route a bill: names, GST registrations and books periods.

    Companies sharing a GSTIN are siblings (one logical company split by year);
    each sibling's period ends the day before the next sibling's books begin.
    """
    from .supplier_gst import native_values

    entries = []
    for company in _companies(catalog):
        units = [m["data"] for m in company.get("masters", {}).get("records", []) if m["type"] == "TAXUNIT"]
        gstins = sorted(native_values(company.get("identity", {}), GST_FIELDS) | native_values(units, GST_FIELDS))
        identity = company.get("identity", {})
        entries.append({"company_guid": company["company_guid"], "name": company["company"], "gstins": gstins,
                        "state": text(identity.get("STATENAME")) or text(identity.get("PRIORSTATENAME")),
                        "books_from": books_beginning(identity), "period_to": None, "siblings": []})
    for entry in entries:
        group = sorted((e for e in entries if set(e["gstins"]) & set(entry["gstins"])),
                       key=lambda e: e["books_from"] or "")
        entry["siblings"] = [e["company_guid"] for e in group if e is not entry]
        later = [e["books_from"] for e in group if e["books_from"] and entry["books_from"] and e["books_from"] > entry["books_from"]]
        if later:
            entry["period_to"] = (date.fromisoformat(min(later)) - timedelta(days=1)).isoformat()
    return entries


def annotate(target, catalog):
    """Pin each company's period and siblings on the run's targets at launch."""
    by_guid = {e["company_guid"]: e for e in directory(catalog)}
    for company in target.get("companies", []):
        entry = by_guid.get(company["references"]["company_guid"], {})
        company["period_to"] = entry.get("period_to")
        company["siblings"] = entry.get("siblings", [])
    return target


def needs_triage(config):
    target = config.get("tally_target") or {}
    return (target.get("voucher_proposal_version") == 1 and target.get("company_mode") == "infer"
            and len(target.get("companies", [])) > 1)


def fixed_scope(config):
    """The single company a run can only ever enter, when routing is not needed."""
    target = config.get("tally_target") or {}
    if target.get("voucher_proposal_version") != 1 or needs_triage(config):
        return None
    if target.get("company_mode") == "locked":
        return [target["locked_company_guid"]]
    companies = target.get("companies", [])
    return [companies[0]["references"]["company_guid"]] if len(companies) == 1 else None


def assets_for(config, bill_bytes):
    """Discovery assets for one posting session, within the hosted input budget."""
    catalog, scope = config["source_catalog_snapshot"], config.get("company_scope")
    gstins = (config.get("triage") or {}).get("supplier_gstins", [])
    assets, manifest = context_assets(catalog, companies=scope)
    if bill_bytes + sum(len(a["content"]) for a in assets) <= SESSION_BYTE_LIMIT - 100_000:
        return assets, manifest
    masters = sum(len(a["content"]) for a in assets if "-vouchers-" not in a["path"])
    budget = SESSION_BYTE_LIMIT - 200_000 - bill_bytes - masters
    if budget <= 0:
        raise ValueError("This company's discovered masters alone exceed the hosted input limit.")
    return context_assets(catalog, companies=scope, voucher_budget=budget, supplier_gstins=gstins)


def scoped_config(config, guid, triage=None):
    """A posting child's config: one routed company, plus what triage observed."""
    catalog = config.get("source_catalog_snapshot")
    scoped = config
    if catalog:
        sources = []
        for source in catalog.get("sources", []):
            snapshot = source.get("snapshot", {})
            if source.get("tool") != "tally" or "companies" not in snapshot:
                sources.append(source)
                continue
            snapshot = {**snapshot, "companies": [c for c in snapshot["companies"]
                                                    if c.get("company_guid") == guid]}
            if "company_scope" in snapshot:
                snapshot["company_scope"] = [c for c in snapshot["company_scope"]
                                             if c.get("company_guid") == guid]
            sources.append({**source, "snapshot": snapshot})
        # Filter before copying: four posting lanes must not each decode and
        # retain every open company's native records after routing is settled.
        scoped = {**config, "source_catalog_snapshot": {**catalog, "sources": sources}}
    child = copy.deepcopy(scoped)
    child["company_scope"] = [guid]
    child["tally_target"]["companies"] = [c for c in child["tally_target"]["companies"]
                                          if c["references"]["company_guid"] == guid]
    if triage:
        child["triage"] = triage
    return child


def route(entry, routes):
    """The company a triaged bill belongs to, applying the year-split date rule.

    Returns (company_guid, note) or (None, (code, reason)).
    """
    guid = entry.get("company_guid")
    if entry.get("exception") or guid not in routes:
        exception = entry.get("exception") or {}
        return None, (exception.get("code", "company_unresolved"),
                      exception.get("detail", "Identify exactly one discovered company for this bill."))
    issued = next((d.get("date") for d in entry.get("documents", []) if d.get("date")), None)
    company = routes[guid]
    if not issued or _within(company, issued):
        return guid, None
    fits = [routes[s] for s in company.get("siblings", []) if s in routes and _within(routes[s], issued)]
    if len(fits) == 1:
        moved = fits[0]
        return moved["references"]["company_guid"], (
            f"Bill dated {issued} belongs to {moved['company']}, the same business's company for that period "
            f"(routed from {company['company']}).")
    return None, ("date_outside_company_period",
                  f"Bill date {issued} is outside {company['company']}'s books period and no single sibling company covers it.")


def _within(company, issued):
    return (not company.get("books_from") or issued >= company["books_from"]) and (
        not company.get("period_to") or issued <= company["period_to"])


def triage_chunks(files):
    """Bills grouped for triage sessions within the hosted input limits."""
    chunks, current, size = [], [], 0
    for file in files:
        length = len(file["content"])
        if current and (len(current) >= TRIAGE_FILES or size + length > TRIAGE_BYTES):
            chunks.append(current)
            current, size = [], 0
        current.append(str(file["id"]))
        size += length
    return [*chunks, current] if current else chunks


def expand(connection, parent, triage_child):
    """Turn a finished triage session into one scoped posting child per bill."""
    from .batch import create_child

    # The triage child pinned the evidence (and any refresh) its bills were routed with.
    base = {**triage_child["config"], "agent_output_schema": parent["config"].get("agent_output_schema")}
    routes = {c["references"]["company_guid"]: c for c in base["tally_target"]["companies"]}
    entries = {e["source_file_id"]: e for e in ((triage_child.get("result") or {}).get("bills") or [])}
    for file_id in triage_child["file_ids"]:
        if triage_child["state"] == "failed":
            outcome = None, ("extraction_failed", triage_child.get("error") or "Routing needs attention.")
        else:
            outcome = route(entries.get(file_id, {"exception": {"code": "company_unresolved",
                                                                "detail": "Routing returned no company for this bill."}}), routes)
        guid, detail = outcome
        if guid is None:
            child = create_child(connection, parent, file_id, config={**base, "company_scope": None})
            code, reason = detail
            connection.execute("UPDATE account_runs SET state='review',result=%s WHERE id=%s", (Jsonb(
                {"records": [], "findings": [], "unresolved": [{"source_file_id": file_id, "code": code, "reason": reason}]}),
                child["id"]))
            continue
        documents = entries[file_id].get("documents", [])
        triage = {"company_evidence": entries[file_id].get("company_evidence", ""),
                  "supplier_gstins": sorted({d["supplier_gstin"] for d in documents if d.get("supplier_gstin")}),
                  **({"note": detail} if detail else {})}
        create_child(connection, parent, file_id, config=scoped_config(base, guid, triage))
    connection.execute("UPDATE account_runs SET config=config || '{\"expanded\":true}'::jsonb WHERE id=%s",
                       (triage_child["id"],))
