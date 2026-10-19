"""Bill posting profiles: how one company records its supplier documents.

The posting_profile stage of Bill Entry derives the pattern once per company
from discovery (voucher types, invoice-number field, round-off, TDS, party
groups, practice notes). Code validates every identity it names against the
company's discovered masters; a member confirms it once with one click, after
which every bill for that company is proposed and checked against it. A
year-split sibling inherits a confirmed pattern when every identity re-binds by
exact name and parent group; newer discovery keeps a pattern while its
identities still hold, so routine master edits never force re-confirmation.
"""

import copy

from psycopg.types.json import Jsonb

from minkops_platform import attention, profiles
from minkops_platform.errors import ServiceError

KIND = "posting_profile"
NUMBER_FIELDS = {"REFERENCE", "VOUCHERNUMBER", "NARRATION"}
FAMILIES = {"invoice": ("purchase", "journal"), "credit_note": ("debit_note",)}


def _company(config, guid):
    for source in config["source_catalog_snapshot"].get("sources", []):
        for company in (source.get("snapshot") or {}).get("companies", []):
            if company.get("company_guid") == guid:
                return company
    raise ValueError("The company is missing from the pinned discovery.")


def masters_for(config, guid):
    from .vouchers import Masters

    created = [m for m in config.get("created_masters", []) if m.get("company_guid") == guid]
    return Masters(_company(config, guid), created)


def _groups(masters):
    return {masters.name(d) for (kind, _), found in masters.by_key.items() if kind == "GROUP" for d in found} | {
        masters.scalar(d, "PARENT") for (kind, _), found in masters.by_key.items() if kind == "LEDGER" for d in found}


def validate(payload, masters, company_guid):
    """A derived pattern, with every named identity proven to exist; else ValueError."""
    payload = copy.deepcopy(payload)
    if payload.get("company_guid") != company_guid:
        raise ValueError("The posting pattern must describe the routed company.")
    references = {}

    def bind(kind, guid, what):
        found = masters.by_key.get((kind, guid)) if isinstance(guid, str) else None
        if not found or len(found) != 1:
            raise ValueError(f"The posting pattern names an undiscovered {what}.")
        references[guid] = {"type": kind, "NAME": masters.name(found[0]), "PARENT": masters.scalar(found[0], "PARENT")}
        return found[0]

    families = payload.get("families") or {}
    if "invoice" not in families or set(families) - set(FAMILIES):
        raise ValueError("The posting pattern must state how invoices are recorded.")
    for kind, entry in families.items():
        if entry is None and kind == "credit_note":
            continue
        voucher_type = bind("VOUCHERTYPE", (entry or {}).get("voucher_type_guid"), "voucher type")
        if entry.get("family") not in FAMILIES[kind] or masters.family(voucher_type) != entry["family"] \
                or masters.scalar(voucher_type, "ISACTIVE").casefold() == "no":
            raise ValueError(f"The {kind.replace('_', ' ')} voucher type must be an active {entry.get('family')} type.")
    fields = (payload.get("invoice_number") or {}).get("fields")
    if not isinstance(fields, list) or not fields or set(fields) - NUMBER_FIELDS:
        raise ValueError("The posting pattern must say where supplier document numbers are recorded.")
    if payload.get("round_off") is not None:
        bind("LEDGER", payload["round_off"].get("ledger_guid"), "round-off ledger")
        if type(payload["round_off"].get("max_cents")) is not int or not 1 <= payload["round_off"]["max_cents"] <= 100:
            raise ValueError("A round-off never exceeds one rupee.")
    if payload.get("tds") is not None:
        tds = payload["tds"]
        if tds.get("deducted_at") not in ("booking", "payment") or not tds.get("ledgers"):
            raise ValueError("TDS practice needs where it is deducted and its ledgers.")
        for line in tds["ledgers"]:
            bind("LEDGER", line.get("ledger_guid"), "TDS ledger")
            if type(line.get("rate")) not in (int, float) or not 0 < line["rate"] <= 30 or not str(line.get("section") or "").strip():
                raise ValueError("Each TDS ledger needs its section and rate.")
    groups = payload.get("party_groups")
    if not isinstance(groups, list) or not groups or set(groups) - _groups(masters):
        raise ValueError("Supplier party groups must be discovered groups.")
    practice = payload.get("practice", [])
    if not isinstance(practice, list) or len(practice) > 30 or any(
            not isinstance(p, dict) or not str(p.get("statement") or "").strip() for p in practice):
        raise ValueError("Practice notes must be short evidenced statements.")
    payload["references"] = references
    return payload


def holds(payload, masters):
    """Does a pattern still describe the company in newer discovery?

    Only identity and grouping matter; an edited master (new ALTERID) still holds.
    """
    for guid, ref in payload.get("references", {}).items():
        found = masters.by_key.get((ref["type"], guid))
        if not found or len(found) != 1 or masters.scalar(found[0], "PARENT") != ref["PARENT"]:
            return False
        if ref["type"] == "VOUCHERTYPE" and masters.scalar(found[0], "ISACTIVE").casefold() == "no":
            return False
    return True


def carry_forward(payload, masters, company_guid):
    """A sibling's confirmed pattern re-bound by exact name and parent, or None."""
    index = {}
    for (kind, guid), found in masters.by_key.items():
        for data in found:
            index.setdefault((kind, masters.name(data), masters.scalar(data, "PARENT")), []).append(guid)
    mapping = {}
    for guid, ref in payload.get("references", {}).items():
        matches = index.get((ref["type"], ref["NAME"], ref["PARENT"]), [])
        if len(matches) != 1:
            return None
        mapping[guid] = matches[0]

    def rebind(value):
        if isinstance(value, dict):
            return {k: rebind(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rebind(v) for v in value]
        return mapping.get(value, value) if isinstance(value, str) else value

    carried = rebind({k: v for k, v in payload.items() if k != "references"})
    carried["company_guid"] = company_guid
    try:
        return validate(carried, masters, company_guid)
    except ValueError:
        return None


def attach(connection, run, config, guid):
    """Give a posting session its company's active pattern, or make it wait for one.

    Returns the profile; the caller's config gains either `posting_profiles` or
    `awaits`. Deriving is single-flight: concurrent batches share one session.
    """
    from .batch import create_child

    discovery_id = config["tally_target"]["discovery_id"]
    live = profiles.current(connection, run["tenant_id"], KIND, guid, lock=True)
    if live and live["status"] == "active" and live["provenance"].get("discovery_id") != discovery_id:
        if holds(live["payload"], masters_for(config, guid)):
            live = profiles.reprove(connection, live, {**live["provenance"], "discovery_id": discovery_id})
        else:
            profiles.invalidate(connection, live, "Newer discovery no longer contains an identity this pattern uses.")
            live = None
    if live is None:
        live = _inherited(connection, run, config, guid)
    if live is None:
        live, created = profiles.ensure(connection, run["tenant_id"], KIND, guid, actor=run["actor_id"],
                                        provenance={"discovery_id": discovery_id, "run_id": str(run["id"])})
        if created:
            derivation = create_child(connection, run, None, file_ids=[], stage="posting_profile",
                                      config={**config, "company_scope": [guid], "posting_profile_id": str(live["id"])})
            connection.execute("UPDATE client_profiles SET derivation_run_id=%s WHERE id=%s", (derivation["id"], live["id"]))
    if live["status"] == "active":
        config["posting_profiles"] = {**config.get("posting_profiles", {}), guid: _pinned(live)}
        config.pop("awaits", None)
    else:
        config["awaits"] = {"profile": str(live["id"])}
    return live


def _pinned(profile):
    return {"id": str(profile["id"]), "version": profile["version"], **profile["payload"]}


def _inherited(connection, run, config, guid):
    target = next(c for c in config["tally_target"]["companies"] if c["references"]["company_guid"] == guid)
    masters = masters_for(config, guid)
    for sibling in target.get("siblings", []):
        source = profiles.current(connection, run["tenant_id"], KIND, sibling)
        if source and source["status"] == "active":
            carried = carry_forward(source["payload"], masters, guid)
            if carried:
                return profiles.create(connection, run["tenant_id"], KIND, guid, carried, status="active",
                                       actor=run["actor_id"],
                                       provenance={"discovery_id": config["tally_target"]["discovery_id"],
                                                   "carried_from": str(source["id"])})
    return None


def proposed(connection, run, payload):
    """A derivation finished: store the pattern and ask for one confirmation."""
    profile = profiles.get(connection, run["tenant_id"], run["config"]["posting_profile_id"], lock=True)
    if profile is None or profile["status"] != "deriving":
        return
    profile = profiles.propose(connection, profile, payload, derivation_run_id=run["id"])
    company = next(c["company"] for c in run["config"]["tally_target"]["companies"]
                   if c["references"]["company_guid"] == profile["scope_key"])
    waiting = connection.execute(
        "SELECT count(*) AS n FROM workflow_runs WHERE tenant_id=%s AND config->'awaits'->>'profile'=%s",
        (run["tenant_id"], str(profile["id"]))).fetchone()["n"]
    attention.record(connection, run, f"profile:{profile['id']}", company, "Confirm posting pattern", kind="profile",
                     target={"profile_id": str(profile["id"]), "company": company, "company_guid": profile["scope_key"],
                             "summary": payload.get("summary", []), "waiting": waiting, "actions": ["confirm", "nothing"]})


def decide(connection, tenant, user, item_id, action):
    """Confirm or decline a proposed pattern from its attention card."""
    item = attention.get(connection, tenant["id"], item_id)
    if item["kind"] != "profile" or item["status"] != "pending":
        raise ServiceError("conflict", "This posting pattern is no longer awaiting a decision.")
    profile = profiles.get(connection, tenant["id"], item["target"]["profile_id"], lock=True)
    if profile is None or profile["status"] != "proposed":
        raise ServiceError("conflict", "This posting pattern is no longer awaiting a decision.")
    if action == "confirm":
        profile = profiles.confirm(connection, profile, user["id"])
        _release(connection, profile)
        attention.audit(connection, item, user["id"], "confirmed", "Posting pattern confirmed.")
    elif action == "nothing":
        profiles.decline(connection, profile, "Not confirmed by a member.")
        fail_waiters(connection, profile, "The posting pattern was not confirmed. Enter these bills in Tally.")
        attention.audit(connection, item, user["id"], "deferred", "Posting pattern not confirmed; bills left for Tally.")
    else:
        raise ServiceError("invalid", "Choose Confirm or Do nothing.")
    connection.execute("UPDATE attention_items SET status='done',done_by=%s,done_at=now(),updated_at=now() WHERE id=%s",
                       (user["id"], item["id"]))
    return {"status": profile["status"] if action == "confirm" else "superseded"}


def _release(connection, profile):
    """Waiting sessions (and their batches) receive the active pattern and resume."""
    pinned = Jsonb({profile["scope_key"]: _pinned(profile)})
    waiters = connection.execute(
        """UPDATE workflow_runs SET config=(config-'awaits') || jsonb_build_object('posting_profiles',
            coalesce(config->'posting_profiles','{}'::jsonb) || %s::jsonb), updated_at=now()
        WHERE tenant_id=%s AND config->'awaits'->>'profile'=%s RETURNING parent_run_id""",
        (pinned, profile["tenant_id"], str(profile["id"]))).fetchall()
    parents = {str(w["parent_run_id"]) for w in waiters if w["parent_run_id"]}
    if parents:
        connection.execute(
            """UPDATE workflow_runs SET config=config || jsonb_build_object('posting_profiles',
                coalesce(config->'posting_profiles','{}'::jsonb) || %s::jsonb) WHERE tenant_id=%s AND id::text = ANY(%s)""",
            (pinned, profile["tenant_id"], list(parents)))


def fail_waiters(connection, profile, reason):
    connection.execute(
        """UPDATE workflow_runs SET state='failed',error=%s,config=config-'awaits',updated_at=now()
        WHERE tenant_id=%s AND config->'awaits'->>'profile'=%s AND state='queued'""",
        (reason, profile["tenant_id"], str(profile["id"])))


def sweep(connection):
    """Release scopes whose derivation failed, so bills hold instead of waiting forever."""
    failed = connection.execute(
        """SELECT p.* FROM client_profiles p JOIN workflow_runs r ON r.tenant_id=p.tenant_id AND r.id=p.derivation_run_id
        WHERE p.kind=%s AND p.status='deriving' AND r.state='failed' FOR UPDATE OF p SKIP LOCKED""", (KIND,)).fetchall()
    for profile in failed:
        profiles.fail(connection, profile, "The posting pattern could not be derived.")
        fail_waiters(connection, profile, "Minkops could not derive this company's posting pattern. Enter these bills in Tally.")


def misses(connection, run, result):
    """Bills that did not fit their company's active pattern count against it."""
    for guid, pinned in (run["config"].get("posting_profiles") or {}).items():
        count = sum("posting_profile_miss" in r.get("exception_codes", []) for r in result.get("records", [])
                    if r.get("company_guid") == guid)
        if count:
            profile = profiles.get(connection, run["tenant_id"], pinned["id"], lock=True)
            if profile and profile["status"] == "active":
                profiles.record_miss(connection, profile, count)
