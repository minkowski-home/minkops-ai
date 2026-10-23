"""The no-AI Tally sync: plans, idempotent pages, guards and publication.

A sync is one `tally.sync` desktop job. The companion collects; the server
decides. The companion first reports every open company with its markers,
read before anything else. The server then identifies each company by PC,
GUID, BooksFrom, name and number, and answers per company:
- skip, when nothing changed;
- delta, fetching AlterIDs above the stored markers;
- full, rebuilding into a new version after a marker regression, an
  identity change, or a move to another PC, whose Tally copy has markers of
  its own.

Bounded pages of masters, vouchers, counts and census then build that version.
A census may tombstone a voucher only on a date where it agrees with Tally's
own independent count, because a truncated response can still report success.
The finish receipt publishes complete versions with the markers read first and
releases the runs that waited for the sync.

Nothing here uses AI or authorises a write.
"""

import hashlib
import json
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb

from minkops_platform import attention, clients, desktop, work
from minkops_platform.errors import ServiceError
from minkops_platform.run_controls import observe_task

from . import memory, mirror, writes

PROTOCOL = 1
BATCH = 5000
PAGE_RECORDS = 500
SWEEP_EVERY = timedelta(hours=20)
BACKGROUND_EVERY = timedelta(minutes=15)
PAGE_KINDS = {"companies", "masters", "vouchers", "counts", "census", "master_census"}


def window(today, books_from):
    """The current and previous financial years, never before the books begin."""
    year = today.year if today.month >= 4 else today.year - 1
    start = max(date(year - 1, 4, 1), date.fromisoformat(str(books_from)))
    return {"from": start.isoformat(), "to": date(year + 1, 3, 31).isoformat()}


def sweep_due(last_swept, now):
    return not last_swept or not last_swept.get("swept") or now - last_swept["published_at"] >= SWEEP_EVERY


def blocker(device_id):
    """What a run's "Get ready" items wait on until this PC's sync finishes."""
    return {"kind": "sync", "ref": str(device_id)}


def _markers(observed):
    markers = observed.get("markers") or {}
    # A company with no vouchers reports no AltVchId; treat it as 0.
    return {"alt_mst_id": int(markers.get("alt_mst_id") or 0), "alt_vch_id": int(markers.get("alt_vch_id") or 0),
            "last_voucher_date": markers.get("last_voucher_date")}


# --- requests and plans ------------------------------------------------------------

def request(connection, tenant, user, member, device_id, *, reason="requested"):
    """Queue a sync on this PC, or return the one already queued or running."""
    device = connection.execute("SELECT * FROM desktop_devices WHERE tenant_id=%s AND id=%s",
                                (tenant["id"], device_id)).fetchone()
    if not device or device["revoked_at"] or device["expires_at"] <= datetime.now(UTC):
        raise ServiceError("not_found", "This PC is not connected to the workspace.")
    if device["owner_id"] != user["id"] and not clients.is_admin(user, member):
        raise ServiceError("forbidden", "Only the PC's owner or a workspace admin can refresh its Tally copy.")
    return desktop.public_job(queue(connection, device, user["id"], reason=reason))


def queue(connection, device, actor_id, *, reason, fresh=False):
    """The PC's queued or running sync, or a new one; callers have authorised the request.

    `fresh` asks for a read that starts after this request, as a recheck does: a sync already reading Tally may have
    read the books before a person changed them, so another is queued behind it.
    """
    desktop.require_companion(device)
    existing = connection.execute(
        """SELECT * FROM desktop_jobs WHERE device_id=%s AND operation='tally.sync' AND state IN ('queued','executing')
           ORDER BY created_at DESC LIMIT 1 FOR UPDATE""", (device["id"],)).fetchone()
    if existing and existing["state"] == "executing" and existing["lease_until"] < datetime.now(UTC):
        # The companion stopped mid-sync: revert its builds and start afresh.
        fail(connection, device, existing, "The previous refresh stopped before it finished.")
        connection.execute("""UPDATE desktop_jobs SET state='failed',error='The refresh stopped before it finished.',
                              lease_until=NULL,updated_at=now() WHERE id=%s""", (existing["id"],))
    elif existing and not (fresh and existing["state"] == "executing"):
        return existing
    task = connection.execute("INSERT INTO tasks(tenant_id,title,summary) VALUES (%s,%s,%s) RETURNING id",
                              (device["tenant_id"], f"Refresh Tally copy on {device['name']}",
                               "Waiting for the PC.")).fetchone()
    payload = {"reason": reason[:40]}
    job = connection.execute(
        """INSERT INTO desktop_jobs(tenant_id,device_id,actor_id,task_id,operation,input,request_key,request_hash)
           VALUES (%s,%s,%s,%s,'tally.sync',%s,%s,%s) RETURNING *""",
        (device["tenant_id"], device["id"], actor_id, task["id"], Jsonb(payload), uuid4(),
         hashlib.sha256(json.dumps(payload).encode()).hexdigest())).fetchone()
    observe_task(connection, tenant_id=device["tenant_id"], task_id=task["id"], run_id=job["id"], state="queued",
                 summary=f"Waiting for {device['name']}.", progress=0, event_prefix="sync")
    return job


def background(connection, device, *, now=None):
    """Queue an idle PC's periodic refresh, so a run's "Get ready" finds a small delta.

    Every refresh first reports the companies open in Tally, so this is also how
    a PC's companies are found: a newly connected PC is read on its first idle
    poll, and a company opened later within BACKGROUND_EVERY. Companies not yet
    authorised are only identified, never read (`_companies`).

    Only for a PC with nothing queued or running and no sync finished within
    BACKGROUND_EVERY. Background refreshes share one task per PC rather than
    adding one to the dashboard each time. The nightly sweep needs no scheduler
    of its own: every sync checks whether one is due.
    """
    now = now or datetime.now(UTC)
    if connection.execute("SELECT 1 FROM desktop_jobs WHERE device_id=%s AND state IN ('queued','executing') LIMIT 1",
                          (device["id"],)).fetchone():
        return None
    # When this PC's latest sync last changed, which for a finished one is when it ended.
    last = connection.execute(
        """SELECT updated_at FROM desktop_jobs WHERE device_id=%s AND operation='tally.sync'
           ORDER BY updated_at DESC LIMIT 1""", (device["id"],)).fetchone()
    if last and now - last["updated_at"] < BACKGROUND_EVERY:
        return None
    previous = connection.execute(
        """SELECT task_id FROM desktop_jobs WHERE device_id=%s AND operation='tally.sync' AND input->>'reason'='background'
           ORDER BY created_at DESC LIMIT 1""", (device["id"],)).fetchone()
    task = previous or connection.execute(
        "INSERT INTO tasks(tenant_id,title,summary) VALUES (%s,%s,%s) RETURNING id AS task_id",
        (device["tenant_id"], f"Keep Tally copy current on {device['name']}", "Waiting for the PC.")).fetchone()
    payload = {"reason": "background"}
    return connection.execute(
        """INSERT INTO desktop_jobs(tenant_id,device_id,actor_id,task_id,operation,input,request_key,request_hash)
           VALUES (%s,%s,%s,%s,'tally.sync',%s,%s,%s) RETURNING *""",
        (device["tenant_id"], device["id"], device["owner_id"], task["task_id"], Jsonb(payload), uuid4(),
         hashlib.sha256(json.dumps(payload).encode()).hexdigest())).fetchone()


def plan(connection, device, job, *, today=None):
    """What this PC's companion collects: every company the server knows there."""
    known = connection.execute(
        """SELECT id,guid,books_from,name,company_number,status FROM companies WHERE tenant_id=%s AND device_id=%s
           ORDER BY name""", (device["tenant_id"], device["id"])).fetchall()
    return {"protocol": PROTOCOL, "port": device["tally_port"], "batch": BATCH, "page_records": PAGE_RECORDS,
            "today": (today or date.today()).isoformat(),
            "companies": [{"key": str(c["id"]), "guid": c["guid"], "books_from": c["books_from"].isoformat(),
                           "name": c["name"], "company_number": c["company_number"], "status": c["status"]}
                          for c in known]}


# --- pages ---------------------------------------------------------------------------

def accept(connection, device, job, page, *, now=None, today=None):
    """Apply one page once; an identical resend returns the stored response."""
    if not isinstance(page, dict) or page.get("kind") not in PAGE_KINDS or not isinstance(page.get("seq"), int):
        raise ServiceError("invalid", "Invalid sync page.")
    digest = hashlib.sha256(json.dumps(page, sort_keys=True, default=str).encode()).hexdigest()
    stored = connection.execute("SELECT digest,response FROM sync_pages WHERE job_id=%s AND seq=%s",
                                (job["id"], page["seq"])).fetchone()
    if stored:
        if stored["digest"] != digest:
            raise ServiceError("conflict", "This sync page was already received with different content.")
        return stored["response"]
    now, today = now or datetime.now(UTC), today or date.today()
    handler = {"companies": _companies, "masters": _masters, "vouchers": _vouchers, "counts": _counts,
               "census": _census, "master_census": _master_census}[page["kind"]]
    response = handler(connection, device, job, page, now=now, today=today)
    connection.execute("INSERT INTO sync_pages(job_id,seq,digest,response) VALUES (%s,%s,%s,%s)",
                       (job["id"], page["seq"], digest, Jsonb(response)))
    # Collection is progress: keep the read's lease alive for long syncs.
    connection.execute("UPDATE desktop_jobs SET lease_until=now()+interval '2 minutes',updated_at=now() WHERE id=%s",
                       (job["id"],))
    return response


def _observe(connection, device, job, observed):
    """The known company this observation is, updated; or a new pending one."""
    identity = {"guid": str(observed["guid"]), "books_from": str(observed["books_from"]),
                "name": str(observed["name"]), "company_number": observed.get("company_number")}
    row = connection.execute(
        "SELECT * FROM companies WHERE tenant_id=%s AND device_id=%s AND guid=%s AND books_from=%s FOR UPDATE",
        (device["tenant_id"], device["id"], identity["guid"], identity["books_from"])).fetchone()
    if row:
        change = clients.identity_change({**row, "books_from": row["books_from"].isoformat()}, identity)
        row = connection.execute(
            "UPDATE companies SET name=%s,company_number=%s,last_seen_at=now() WHERE id=%s RETURNING *",
            (identity["name"], identity["company_number"], row["id"])).fetchone()
        return row, change
    row = connection.execute(
        """INSERT INTO companies(tenant_id,device_id,guid,books_from,name,company_number) VALUES (%s,%s,%s,%s,%s,%s)
           RETURNING *""", (device["tenant_id"], device["id"], identity["guid"], identity["books_from"],
                            identity["name"], identity["company_number"])).fetchone()
    attention.record(connection, job, f"company:{row['id']}", row["name"][:200], "New company found", kind="company",
                     target=_card(connection, row, device))
    return row, "new"


def _card(connection, company, device):
    """What a newly found company's card says, and the client's company it continues, when there is one.

    `card` is for admins, who decide: it names the client. The reason any member reads names only PCs.
    """
    card = {"company_id": str(company["id"]), "name": company["name"], "books_from": company["books_from"].isoformat(),
            "device": device["name"]}
    live, previous = clients.live_copy(connection, company), clients.predecessor(connection, company)
    found = f"{company['name']} is open in Tally on {device['name']}."
    if live:
        card["held_on"] = live["device_name"]
        reason = (f"{found} These books are already a client's on {live['device_name']}, and a client's books are "
                  f"saved to one copy. To move them here, disconnect {live['device_name']} first.")
    elif previous:
        card["continues"] = {"client": previous["client_slug"], "client_name": previous["client_name"],
                             "device": previous["device_name"]}
        reason = (f"{found} These books were on {previous['device_name']}, which is disconnected. Continue them here "
                  "to keep what Minkops learnt for them, their rules and their history.")
    else:
        reason = f"{found} Add it to a client's books?"
    return {"company_id": str(company["id"]), "device_id": str(device["id"]), "device": device["name"],
            "books_from": company["books_from"].isoformat(), "reason": reason, "card": card}


def disconnected(connection, device):
    """A PC being disconnected: settle the saves it had begun, and offer its companies to the PCs that find them.

    A company found on another PC before this one was disconnected had no continuation to offer; its card now does.
    """
    writes.disconnected(connection, device)
    for found in connection.execute(
            """SELECT f.*, d.name AS device_name FROM companies c
               JOIN companies f ON f.tenant_id=c.tenant_id AND f.guid=c.guid AND f.books_from=c.books_from
                   AND f.status='pending'
               JOIN desktop_devices d ON d.id=f.device_id AND d.revoked_at IS NULL
               WHERE c.device_id=%s AND c.status='authorised' ORDER BY f.id""", (device["id"],)).fetchall():
        connection.execute(
            """UPDATE attention_items SET target=%s,updated_at=now() WHERE tenant_id=%s AND event_key=%s
               AND status='pending'""",
            (Jsonb(_card(connection, found, {"id": found["device_id"], "name": found["device_name"]})),
             found["tenant_id"], f"company:{found['id']}"))


def _decide(previous, observed, change, *, device_id, last_swept, now, reason):
    """skip, delta or full for one authorised company, with why and whether to sweep."""
    markers = _markers(observed)
    if previous is None:
        return "full", "first_sync", True
    if previous["device_id"] != device_id:
        # Markers and AlterIDs belong to one Tally copy: another PC's never measure what this one holds.
        return "full", "pc_changed", True
    if change == "renamed":
        return "full", "identity_changed", True
    stored = previous["markers"]
    if markers["alt_vch_id"] < int(stored.get("alt_vch_id") or 0) or markers["alt_mst_id"] < int(stored.get("alt_mst_id") or 0):
        return "full", "marker_regressed", True
    moved = (markers["alt_vch_id"], markers["alt_mst_id"]) != (int(stored.get("alt_vch_id") or 0),
                                                                 int(stored.get("alt_mst_id") or 0))
    nightly = reason == "nightly" or sweep_due(last_swept, now)
    if not moved and not nightly:
        return "skip", "unchanged", False
    return "delta", "markers_moved" if moved else "nightly", True


def _companies(connection, device, job, page, *, now, today):
    observed = page.get("companies")
    if not isinstance(observed, list) or len(observed) > 50:
        raise ServiceError("invalid", "Report at most 50 open companies.")
    instructions = []
    for entry in observed:
        company, change = _observe(connection, device, job, entry)
        step = {"company": str(company["id"]), "guid": company["guid"], "name": company["name"]}
        if company["status"] != "authorised" or change is None:
            instructions.append({**step, "mode": "skip", "reason": company["status"] if change else "identity_unclear"})
            continue
        stale = mirror.building(connection, company["id"])
        if stale:
            mirror.abandon(connection, stale, "superseded by a later sync")
        previous = mirror.latest(connection, company["id"])
        last_swept = connection.execute(
            """SELECT * FROM mirror_versions WHERE company_id=%s AND state='published' AND swept
               ORDER BY version DESC LIMIT 1""", (company["id"],)).fetchone()
        mode, why, sweep = _decide(previous, entry, change, device_id=device["id"], last_swept=last_swept, now=now,
                                   reason=job["input"].get("reason"))
        if mode == "skip":
            instructions.append({**step, "mode": "skip", "reason": why})
            continue
        coverage = window(today, company["books_from"])
        full_census = why == "nightly" or job["input"].get("reason") == "nightly"
        version = mirror.begin(connection, company, kind=mode, reason=why, markers=_markers(entry), coverage=coverage,
                               job_id=job["id"])
        connection.execute("UPDATE mirror_versions SET stats=stats || %s WHERE company_id=%s AND version=%s",
                           (Jsonb({"full_census": full_census}), company["id"], version["version"]))
        after = None if mode == "full" else {k: int(previous["markers"].get(k) or 0) for k in ("alt_mst_id", "alt_vch_id")}
        instructions.append({**step, "mode": mode, "reason": why, "after": after, "window": coverage, "sweep": sweep})
    return {"instructions": instructions}


def _version(connection, device, job, page):
    company = connection.execute("SELECT * FROM companies WHERE tenant_id=%s AND id=%s AND device_id=%s",
                                 (device["tenant_id"], page.get("company"), device["id"])).fetchone()
    version = company and mirror.building(connection, company["id"])
    if not version or version["job_id"] != job["id"]:
        raise ServiceError("conflict", "This company is not being collected by this sync.")
    return company, version


def _records(page, limit=PAGE_RECORDS):
    records = page.get("records")
    if not isinstance(records, list) or len(records) > limit or not all(isinstance(r, dict) for r in records):
        raise ServiceError("invalid", f"A sync page carries at most {limit} records.")
    return records


def _masters(connection, device, job, page, **_):
    _, version = _version(connection, device, job, page)
    records = _records(page)
    if any(set(r) != {"type", "data"} or not isinstance(r["type"], str) for r in records):
        raise ServiceError("invalid", "Masters are {type, data} records.")
    return mirror.upsert_masters(connection, version, records)


def _vouchers(connection, device, job, page, **_):
    _, version = _version(connection, device, job, page)
    try:
        return mirror.upsert_vouchers(connection, version, _records(page))
    except ValueError as error:
        raise ServiceError("invalid", str(error)) from error


def _counts(connection, device, job, page, **_):
    """Record Tally's per-date counts and name the dates whose census is needed."""
    _, version = _version(connection, device, job, page)
    counts = page.get("counts")
    if not isinstance(counts, dict) or any(not isinstance(n, int) or n < 0 for n in counts.values()):
        raise ServiceError("invalid", "Counts are {date: count}.")
    mirror.record_counts(connection, version, counts)
    connection.execute("UPDATE mirror_versions SET stats=stats || '{\"counted\":true}' WHERE company_id=%s AND version=%s",
                       (version["company_id"], version["version"]))
    coverage = version["coverage"]
    mirrored = mirror.voucher_counts(connection, version["company_id"], version["version"], coverage["from"], coverage["to"])
    full = version["stats"].get("full_census")
    dates = sorted(set(counts) | set(mirrored)) if full else sorted(
        day for day in set(counts) | set(mirrored) if counts.get(day, 0) != mirrored.get(day, 0))
    if dates and not full:
        # A deletion renumbers later vouchers of auto-numbered types without
        # changing their AlterIDs: recheck numbers from the first changed date.
        dates = sorted(day for day in set(counts) | set(mirrored) if day >= dates[0])
    return {"census": _spans(dates)}


def _spans(dates, limit=BATCH):
    """Contiguous runs of the listed dates, as census requests."""
    spans = []
    for day in dates:
        if spans and (date.fromisoformat(day) - date.fromisoformat(spans[-1]["to"])).days <= 31:
            spans[-1]["to"] = day
        else:
            spans.append({"from": day, "to": day})
    return spans


def _census(connection, device, job, page, **_):
    """Tombstone missing vouchers and ask for changed ones, on dates the counts confirm."""
    _, version = _version(connection, device, job, page)
    entries = page.get("entries")
    if not isinstance(entries, list) or not all(isinstance(e, dict) and {"guid", "alter_id", "date"} <= set(e) for e in entries):
        raise ServiceError("invalid", "Census entries are {guid, alter_id, number, date}.")
    span = (str(page.get("from")), str(page.get("to")))
    counts = connection.execute("SELECT counts FROM mirror_versions WHERE company_id=%s AND version=%s",
                                (version["company_id"], version["version"])).fetchone()["counts"] or {}
    by_date = {}
    for entry in entries:
        by_date.setdefault(str(entry["date"]), []).append(entry)
    mirrored = {}
    for row in mirror.vouchers(connection, version["company_id"], version["version"], date_from=span[0], date_to=span[1]):
        mirrored.setdefault(row["date"].isoformat(), []).append(row)
    missing, refetch, disagreed = [], [], []
    for day in sorted(set(by_date) | set(mirrored)):
        census = by_date.get(day, [])
        if len(census) != counts.get(day, 0):
            disagreed.append(day)  # Never record a deletion the counts do not confirm.
            continue
        present = {e["guid"]: e for e in census}
        for row in mirrored.get(day, []):
            entry = present.get(row["guid"])
            if entry is None:
                missing.append(row["guid"])
            elif int(entry["alter_id"]) != row["alter_id"] or str(entry.get("number", row["number"])) != row["number"]:
                refetch.append(row["guid"])
        known = {row["guid"] for row in mirrored.get(day, [])}
        refetch.extend(guid for guid in present if guid not in known)
    if missing:
        mirror.tombstone(connection, version, "vouchers", missing)
    connection.execute(
        """UPDATE mirror_versions SET stats=stats || jsonb_build_object('census_mismatch_dates',
               coalesce(stats->'census_mismatch_dates','[]'::jsonb) || %s, 'tombstoned',
               coalesce((stats->>'tombstoned')::integer,0) + %s)
           WHERE company_id=%s AND version=%s""",
        (Jsonb(disagreed), len(missing), version["company_id"], version["version"]))
    return {"refetch": sorted(set(refetch)), "tombstoned": len(missing), "disagreed": disagreed}


def _master_census(connection, device, job, page, **_):
    """Retire masters deleted in Tally, when the census matches Tally's own count."""
    _, version = _version(connection, device, job, page)
    entries, kind, count = page.get("entries"), page.get("type"), page.get("count")
    if not isinstance(entries, list) or not isinstance(kind, str) or not isinstance(count, int):
        raise ServiceError("invalid", "A master census names its type, count and entries.")
    if len(entries) != count:
        return {"refetch": [], "tombstoned": 0, "disagreed": [kind]}
    present = {str(e["guid"]): int(e.get("alter_id") or 0) for e in entries}
    rows = mirror.masters(connection, version["company_id"], version["version"], types=[kind])
    missing = [row["guid"] for row in rows if row["guid"] not in present]
    if missing:
        mirror.tombstone(connection, version, "masters", missing)
    known = {row["guid"]: row["alter_id"] for row in rows}
    return {"refetch": sorted(g for g, alter in present.items() if known.get(g) not in (alter,)),
            "tombstoned": len(missing)}


# --- outcome ---------------------------------------------------------------------------

def finish(connection, device, job, result):
    """Publish each complete company, abandon the rest, then release waiting runs."""
    complete = {str(c["company"]) for c in (result or {}).get("companies", []) if c.get("complete") is True}
    published, abandoned = [], []
    for version in connection.execute("SELECT * FROM mirror_versions WHERE job_id=%s AND state='building'",
                                      (job["id"],)).fetchall():
        key = str(version["company_id"])
        if key in complete:
            published.append(mirror.publish(connection, version, swept=bool(version["stats"].get("counted"))))
        else:
            mirror.abandon(connection, version, "incomplete")
            abandoned.append(key)
    from .bill_entry import entered_by_hand as bills_entered
    from .practice import probe, unprobed
    from .statement_entry import entered_by_hand as rows_entered
    for version in published:
        company = connection.execute("SELECT * FROM companies WHERE id=%s", (version["company_id"],)).fetchone()
        _compare_copies(connection, job, company, version)
        memory.revalidate(connection, company, version)
        if company["status"] == "authorised":
            # Work its client's runs hold that a person has since entered in Tally by hand is found there.
            bills_entered(connection, company, version["version"])
            rows_entered(connection, company, version["version"])
        probe(connection, company, version, job)
        mirror.collect(connection, company["id"])
    # Books unchanged since a probe was added have not met it yet.
    for company in connection.execute(
            "SELECT * FROM companies WHERE device_id=%s AND status='authorised' AND NOT (id = ANY(%s)) ORDER BY id",
            (device["id"], [version["company_id"] for version in published])).fetchall():
        latest = mirror.latest(connection, company["id"])
        if latest and unprobed(latest):
            probe(connection, company, latest, job)
    released = work.release(connection, device["tenant_id"], blocker(device["id"]))
    summary = {"published": [str(v["company_id"]) for v in published], "abandoned": abandoned, "released": released}
    observe_task(connection, tenant_id=device["tenant_id"], task_id=job["task_id"], run_id=job["id"], state="completed",
                 summary=f"Tally copy refreshed: {len(published)} compan{'y' if len(published) == 1 else 'ies'} updated.",
                 progress=100, event_prefix="sync")
    return summary


def _compare_copies(connection, job, company, version):
    """After a company moves PCs, name the vouchers the old PC's copy held that this PC's copy lacks.

    A copy restored from an older backup misses what was entered since, including saves Minkops verified. Tally's
    copy is the books Minkops works from, so nothing is re-entered on its own: one card lists what is missing, for
    the accountant to restore the latest copy or enter it again.
    """
    before = connection.execute(
        """SELECT v.*, d.name AS device_name FROM mirror_versions v JOIN desktop_devices d ON d.id=v.device_id
           WHERE v.company_id=%s AND v.state='published' AND v.version < %s ORDER BY v.version DESC LIMIT 1""",
        (company["id"], version["version"])).fetchone()
    if not before or before["device_id"] == version["device_id"]:
        return
    lost = mirror.lost(connection, company["id"], before, version)
    if not (lost["missing"] or lost["older"]):
        return
    here = connection.execute("SELECT name FROM desktop_devices WHERE id=%s", (version["device_id"],)).fetchone()["name"]
    parts = []
    if lost["missing"]:
        examples = "; ".join(f"{row['voucher_type']} {row['number'] or '(no number)'} of {row['date'].isoformat()}"
                             + (f" ({row['party_ledger']})" if row["party_ledger"] else "") for row in lost["examples"])
        parts.append(f"{lost['missing']} voucher{'s' if lost['missing'] != 1 else ''} in the copy Minkops read on "
                     f"{before['device_name']} {'are' if lost['missing'] != 1 else 'is'} missing here, such as "
                     f"{examples}.")
    if lost["older"]:
        parts.append(f"{lost['older']} voucher{'s' if lost['older'] != 1 else ''} here "
                     f"{'show' if lost['older'] != 1 else 'shows'} an earlier edit than {before['device_name']} had.")
    attention.record(connection, job, f"company:{company['id']}:copy:{version['version']}", company["name"][:200],
                     "Older copy of the books", target={"reason": (
                         f"{company['name']} on {here} looks older than on {before['device_name']}. " + " ".join(parts)
                         + f" Restore the latest copy in Tally on {here} and refresh, or enter them again: Minkops now "
                         f"reads and saves to the copy on {here}.")[:1000]})


def fail(connection, device, job, error):
    """A failed collection publishes nothing; waiting runs keep a named blocker."""
    abandoned = []
    for version in connection.execute("SELECT * FROM mirror_versions WHERE job_id=%s AND state='building'",
                                      (job["id"],)).fetchall():
        mirror.abandon(connection, version, str(error)[:200])
        abandoned.append(str(version["company_id"]))
    observe_task(connection, tenant_id=device["tenant_id"], task_id=job["task_id"], run_id=job["id"], state="failed",
                 summary=str(error)[:300], progress=0, event_prefix="sync")
    return {"published": [], "abandoned": abandoned}


def companies(connection, tenant, user, member, device_id):
    """Companies seen on a PC, with their decision and latest mirror version.

    Admins and the PC's owner see every company there; other members see only
    authorised companies of client businesses they can reach.
    """
    device = connection.execute("SELECT owner_id FROM desktop_devices WHERE tenant_id=%s AND id=%s",
                                (tenant["id"], device_id)).fetchone()
    if not device:
        raise ServiceError("not_found", "PC not found.")
    everything = clients.is_admin(user, member) or device["owner_id"] == user["id"]
    visible = None if everything else clients.visible_ids(connection, tenant, user, member)
    rows = connection.execute(
        """SELECT c.id,c.name,c.guid,c.books_from,c.company_number,c.status,c.client_id,cb.name AS client,
                  c.last_seen_at,v.version,v.kind,v.published_at,v.markers
           FROM companies c LEFT JOIN client_businesses cb ON cb.tenant_id=c.tenant_id AND cb.id=c.client_id
           LEFT JOIN LATERAL (SELECT version,kind,published_at,markers FROM mirror_versions
                              WHERE company_id=c.id AND state='published' ORDER BY version DESC LIMIT 1) v ON true
           WHERE c.tenant_id=%s AND c.device_id=%s ORDER BY c.name, c.books_from""",
        (tenant["id"], device_id)).fetchall()
    return [row for row in rows if everything or (row["status"] == "authorised"
                                                  and (visible is None or row["client_id"] in visible))]


def set_port(connection, tenant, user, member, device_id, port):
    """The port this PC's Tally serves on, carried into every later plan."""
    device = connection.execute("SELECT * FROM desktop_devices WHERE tenant_id=%s AND id=%s FOR UPDATE",
                                (tenant["id"], device_id)).fetchone()
    if not device:
        raise ServiceError("not_found", "PC not found.")
    if device["owner_id"] != user["id"] and not clients.is_admin(user, member):
        raise ServiceError("forbidden", "Only the PC's owner or a workspace admin can change its Tally port.")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ServiceError("invalid", "Choose a port from 1 to 65535.")
    connection.execute("UPDATE desktop_devices SET tally_port=%s WHERE id=%s", (port, device_id))
    return {"device_id": str(device_id), "tally_port": port}


def authorise(connection, tenant, user, member, company_id, client_slug):
    """One decision adds a company to a client's books, closes its card and mirrors it.

    When it continues the client's company from a disconnected PC (`clients.authorise_company`), what was left on
    that PC follows: saves it had not begun are sent from here, and the client's runs that waited for it wait for
    this PC's first refresh, which reads the books in full (`_decide`).
    """
    company = clients.authorise_company(connection, tenant, user, member, company_id, client_slug)
    moved = company.get("continued_from")
    _close(connection, tenant, user, company_id, "confirmed",
           f"Company continued here from another PC, for {client_slug}." if moved else f"Company added to {client_slug}.")
    if moved:
        previous = connection.execute("SELECT * FROM desktop_devices WHERE id=%s", (moved,)).fetchone()
        writes.continued(connection, company, previous)
        work.rewait(connection, tenant["id"], blocker(moved), blocker(company["device_id"]), client_id=company["client_id"])
    # An outdated or offline PC syncs once it updates or reconnects.
    with suppress(ServiceError):
        request(connection, tenant, user, member, company["device_id"], reason="authorised")
    return company


def decline(connection, tenant, user, member, company_id):
    """One decision keeps a newly found company out of every client's books, and closes its card."""
    company = clients.decline_company(connection, tenant, user, member, company_id)
    _close(connection, tenant, user, company_id, "declined", "Company kept out of every client's books.")
    return company


def _close(connection, tenant, user, company_id, action, summary):
    item = connection.execute(
        """UPDATE attention_items SET status='done',done_by=%s,done_at=now(),updated_at=now()
           WHERE tenant_id=%s AND event_key=%s AND status='pending' RETURNING *""",
        (user["id"], tenant["id"], f"company:{company_id}")).fetchone()
    if item:
        attention.audit(connection, item, user["id"], action, summary)
