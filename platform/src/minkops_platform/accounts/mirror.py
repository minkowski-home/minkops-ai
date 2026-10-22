"""The versioned Tally mirror: storage, publication, collection and reads.

One mirror per PC and company holds every master and the vouchers of its
coverage window, as collected by the no-AI sync. Rows carry `synced_in` and
`superseded_in`; a row is visible at version V when it was synced at or
before V and not superseded by V. A run pins one published version per
company and reads only rows visible at it, so later syncs can publish while
the run is still working. Nothing is copied into runs.

Native records are stored compacted (empty fields dropped) with a content
digest, so a record fetched again unchanged is only marked seen. Callers own
transactions.
"""

import hashlib
import json
import re
from datetime import date

from psycopg.types.json import Jsonb

GSTIN = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
_VISIBLE = "synced_in <= %(v)s AND (superseded_in IS NULL OR superseded_in > %(v)s)"


def text(value):
    """A native scalar as stripped text; attributes and nested lists are not scalars."""
    if isinstance(value, dict):
        value = value.get("#text")
    return value.strip() if isinstance(value, str) else ""


def normalized(value):
    return " ".join(str(value or "").split()).casefold()


def compact(value):
    """Drop empty and whitespace-only native fields; meaningful values ("No", "0") stay."""
    if isinstance(value, dict):
        kept = {key: compact(item) for key, item in value.items()}
        return {key: item for key, item in kept.items() if item not in ("", {}, [], None)}
    if isinstance(value, list):
        kept = [compact(item) for item in value]
        return [item for item in kept if item not in ("", {}, [], None)]
    if isinstance(value, str):
        return value if value.strip() else ""
    return value


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _list(value):
    return value if isinstance(value, list) else [] if value is None else [value]


def _integer(value):
    digits = text(value)
    return int(digits) if digits.lstrip("-").isdigit() else None


def _cents(value):
    from decimal import Decimal, InvalidOperation
    try:
        return int(Decimal(text(value) or "0") * 100)
    except InvalidOperation:
        return 0


def _first_gstin(data, fields):
    for field in fields:
        for item in _list(data.get(field)):
            candidates = [item] if not isinstance(item, dict) else [item.get(k) for k in ("GSTIN", "GSTREGNUMBER", "#text")]
            for candidate in candidates:
                found = GSTIN.search(text(candidate).upper())
                if found:
                    return found.group()
    return None


def master_row(record):
    """Columns for one native master; None when it has no native GUID."""
    data = compact(record["data"])
    guid = text(data.get("GUID"))
    if not guid:
        return None
    name = text(data.get("@_NAME")) or text(data.get("NAME"))
    names = [text(n) for entry in _list(data.get("LANGUAGENAME.LIST"))
             for n in _list((entry.get("NAME.LIST") or {}).get("NAME") if isinstance(entry, dict) else None)]
    aliases = [n for n in dict.fromkeys(names) if n and n != name]
    hsn = next((text(entry.get("HSNCODE")) for key in ("HSNDETAILS.LIST", "GSTDETAILS.LIST")
                for entry in reversed(_list(data.get(key))) if isinstance(entry, dict) and text(entry.get("HSNCODE"))),
               None)
    bank = re.sub(r"\D", "", text(data.get("BANKDETAILS")))
    return {"guid": guid, "type": record["type"], "name": name, "name_key": normalized(name),
            "parent": text(data.get("PARENT")) or None, "alter_id": _integer(data.get("ALTERID")),
            "aliases": aliases,
            "gstin": _first_gstin(data, ("PARTYGSTIN", "LEDGSTREGDETAILS.LIST", "GSTREGNUMBER",
                                         "GSTREGISTRATIONNUMBER", "GSTREGISTRATIONDETAILS.LIST")),
            "bank_account": bank if len(bank) >= 6 else None, "ifsc": text(data.get("IFSCODE")) or None,
            "hsn": hsn, "digest": _digest(data), "data": data}


def _entries(data):
    for key in ("ALLLEDGERENTRIES.LIST", "LEDGERENTRIES.LIST"):
        yield from (entry for entry in _list(data.get(key)) if isinstance(entry, dict))


def ledger_lines(data):
    """A stored voucher's ledger lines as (ledger, signed cents); Tally signs debits negative."""
    return [(text(entry.get("LEDGERNAME")), cents) for entry in _entries(data)
            if (cents := _cents(entry.get("AMOUNT"))) is not None]


def _inventory(data):
    for key in ("ALLINVENTORYENTRIES.LIST", "INVENTORYENTRIES.LIST"):
        yield from (entry for entry in _list(data.get(key)) if isinstance(entry, dict))


def stock_lines(data):
    """A stored voucher's stock lines: item, billed quantity, signed cents, the ledgers and godowns they post to."""
    return [{"item": text(entry.get("STOCKITEMNAME")),
             "quantity": text(entry.get("BILLEDQTY")) or text(entry.get("ACTUALQTY")), "cents": _cents(entry.get("AMOUNT")),
             "ledgers": [text(a.get("LEDGERNAME")) for a in _list(entry.get("ACCOUNTINGALLOCATIONS.LIST"))
                         if isinstance(a, dict)],
             "godowns": list(dict.fromkeys(text(b.get("GODOWNNAME")) for b in _list(entry.get("BATCHALLOCATIONS.LIST"))
                                           if isinstance(b, dict) and text(b.get("GODOWNNAME"))))}
            for entry in _inventory(data)]


def voucher_row(record):
    """Columns for one native voucher; None for a deleted one, retained or not."""
    data = compact(record)
    yes = lambda field: text(data.get(field)).casefold() == "yes"  # noqa: E731
    if yes("ISDELETED") or yes("ISDELETEDVCHRETAINED"):
        return None
    guid, stamp = text(data.get("GUID")), text(data.get("DATE"))
    if not guid or not re.fullmatch(r"\d{8}", stamp):
        raise ValueError("A voucher needs its GUID and date.")
    issued = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:]))
    ledgers = {text(entry.get("LEDGERNAME")) for entry in _entries(data)} | {
        ledger for line in stock_lines(data) for ledger in line["ledgers"]}
    refs = [{"ledger": text(entry.get("LEDGERNAME")), "ledger_key": normalized(text(entry.get("LEDGERNAME"))),
             "name": text(bill.get("NAME")), "bill_type": text(bill.get("BILLTYPE")),
             "amount_cents": _cents(bill.get("AMOUNT")), "date": issued}
            for entry in _entries(data) for bill in _list(entry.get("BILLALLOCATIONS.LIST"))
            if isinstance(bill, dict) and text(bill.get("NAME"))]
    party = text(data.get("PARTYLEDGERNAME"))
    alter = _integer(data.get("ALTERID"))
    if alter is None:
        raise ValueError("A voucher needs its alteration ID.")
    return {"guid": guid, "master_id": _integer(data.get("MASTERID")), "alter_id": alter, "date": issued,
            "voucher_type": text(data.get("VOUCHERTYPENAME")), "number": text(data.get("VOUCHERNUMBER")),
            "reference": text(data.get("REFERENCE")), "party_ledger": party, "party_key": normalized(party),
            "narration": text(data.get("NARRATION")), "cancelled": yes("ISCANCELLED"), "optional": yes("ISOPTIONAL"),
            "postdated": yes("ISPOSTDATED"), "ledgers": sorted(n for n in ledgers if n), "digest": _digest(data),
            "data": data, "bill_refs": refs}


# --- versions -----------------------------------------------------------------

def begin(connection, company, *, kind, reason, markers, coverage, job_id=None):
    """Open the company's next version, read on the PC the company is on; an abandoned version's number is never
    reused."""
    return connection.execute(
        """INSERT INTO mirror_versions(tenant_id,company_id,version,kind,reason,markers,coverage,job_id,device_id)
           SELECT %s,%s,coalesce(max(version),0)+1,%s,%s,%s,%s,%s,%s FROM mirror_versions WHERE company_id=%s
           RETURNING *""",
        (company["tenant_id"], company["id"], kind, reason[:80], Jsonb(markers), Jsonb(coverage), job_id,
         company["device_id"], company["id"])).fetchone()


def building(connection, company_id):
    return connection.execute("SELECT * FROM mirror_versions WHERE company_id=%s AND state='building'",
                              (company_id,)).fetchone()


def latest(connection, company_id):
    return connection.execute(
        "SELECT * FROM mirror_versions WHERE company_id=%s AND state='published' ORDER BY version DESC LIMIT 1",
        (company_id,)).fetchone()


def pins(connection, company_ids):
    """{company_id: latest published version} for the companies that have one read on the PC they are on now.

    A company that moved PCs has no version to pin until its new PC is read: the old PC's copy is not the one its
    entries are saved to.
    """
    rows = connection.execute(
        """SELECT DISTINCT ON (v.company_id) v.company_id, v.version FROM mirror_versions v
           JOIN companies c ON c.id=v.company_id AND c.device_id=v.device_id
           WHERE v.company_id = ANY(%s) AND v.state='published' ORDER BY v.company_id, v.version DESC""",
        (list(company_ids),)).fetchall()
    return {str(row["company_id"]): row["version"] for row in rows}


_COLUMNS = {
    "mirror_masters": ("guid", "type", "name", "name_key", "parent", "alter_id", "aliases", "gstin", "bank_account",
                       "ifsc", "hsn", "digest", "data"),
    "mirror_vouchers": ("guid", "master_id", "alter_id", "date", "voucher_type", "number", "reference", "party_ledger",
                        "party_key", "narration", "cancelled", "optional", "postdated", "ledgers", "digest", "data"),
}


def _upsert(connection, version, table, rows):
    """Supersede changed rows and insert their new content; identical ones are only seen.

    Returns the counts and the rows that changed in this version.
    """
    v, company_id = version["version"], version["company_id"]
    rows = list({row["guid"]: row for row in rows}.values())
    if not rows:
        return {"changed": 0, "unchanged": 0}, []
    current = {row["guid"]: row for row in connection.execute(
        f"SELECT guid,digest,synced_in FROM {table} WHERE company_id=%s AND guid=ANY(%s) AND superseded_in IS NULL",
        (company_id, [row["guid"] for row in rows])).fetchall()}
    seen, superseded, fresh, rebuilt = [], [], [], []
    for row in rows:
        existing = current.get(row["guid"])
        if existing and existing["digest"] == row["digest"]:
            seen.append(row["guid"])
        elif existing and existing["synced_in"] == v:
            rebuilt.append(row)  # Refetched within this unpublished build: replace in place.
        else:
            fresh.append(row)
            if existing:
                superseded.append(row["guid"])
    if seen:
        connection.execute(f"UPDATE {table} SET seen_in=%s WHERE company_id=%s AND guid=ANY(%s) AND superseded_in IS NULL",
                           (v, company_id, seen))
    if superseded:
        connection.execute(f"UPDATE {table} SET superseded_in=%s WHERE company_id=%s AND guid=ANY(%s) AND superseded_in IS NULL",
                           (v, company_id, superseded))
    if rebuilt:
        connection.execute(f"DELETE FROM {table} WHERE company_id=%s AND guid=ANY(%s) AND synced_in=%s",
                           (company_id, [row["guid"] for row in rebuilt], v))
    columns = _COLUMNS[table]
    with connection.cursor() as cursor:
        cursor.executemany(
            f"""INSERT INTO {table}(tenant_id,company_id,synced_in,seen_in,{','.join(columns)})
                VALUES (%s,%s,%s,%s,{','.join(['%s'] * len(columns))})""",
            [(version["tenant_id"], company_id, v, v, *(Jsonb(row[c]) if c == "data" else row[c] for c in columns))
             for row in [*fresh, *rebuilt]])
    return {"changed": len(fresh) + len(rebuilt), "unchanged": len(seen)}, [*fresh, *rebuilt]


def upsert_masters(connection, version, records):
    return _upsert(connection, version, "mirror_masters", [row for row in map(master_row, records) if row])[0]


def upsert_vouchers(connection, version, records):
    """Upsert live vouchers; a record Tally reports as deleted becomes a tombstone."""
    live, deleted = [], []
    for record in records:
        row = voucher_row(record)
        if row is None:
            deleted.append(text(record.get("GUID")))
        else:
            live.append(row)
    counts, changed = _upsert(connection, version, "mirror_vouchers", live)
    v, company_id = version["version"], version["company_id"]
    if changed:
        guids = [row["guid"] for row in changed]
        connection.execute("DELETE FROM mirror_bill_refs WHERE company_id=%s AND voucher_guid=ANY(%s) AND synced_in=%s",
                           (company_id, guids, v))
        connection.execute("""UPDATE mirror_bill_refs SET superseded_in=%s WHERE company_id=%s AND voucher_guid=ANY(%s)
                              AND superseded_in IS NULL""", (v, company_id, guids))
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO mirror_bill_refs(tenant_id,company_id,voucher_guid,synced_in,ledger,ledger_key,name,
                   bill_type,amount_cents,date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [(version["tenant_id"], company_id, row["guid"], v, ref["ledger"], ref["ledger_key"], ref["name"],
                  ref["bill_type"], ref["amount_cents"], ref["date"]) for row in changed for ref in row["bill_refs"]])
    if deleted:
        counts["deleted"] = tombstone(connection, version, "vouchers", [g for g in deleted if g])
    return counts


def tombstone(connection, version, kind, guids):
    """Supersede rows that no longer exist in Tally; returns how many disappeared."""
    table = {"masters": "mirror_masters", "vouchers": "mirror_vouchers"}[kind]
    v, company_id = version["version"], version["company_id"]
    connection.execute(f"DELETE FROM {table} WHERE company_id=%s AND guid=ANY(%s) AND synced_in=%s", (company_id, guids, v))
    count = connection.execute(
        f"UPDATE {table} SET superseded_in=%s WHERE company_id=%s AND guid=ANY(%s) AND superseded_in IS NULL",
        (v, company_id, guids)).rowcount
    if kind == "vouchers":
        connection.execute("""UPDATE mirror_bill_refs SET superseded_in=%s WHERE company_id=%s AND voucher_guid=ANY(%s)
                              AND superseded_in IS NULL""", (v, company_id, guids))
    return count


def record_counts(connection, version, counts):
    """Store Tally's independent per-date counts {YYYY-MM-DD: n} for the census guard."""
    connection.execute("UPDATE mirror_versions SET counts=coalesce(counts,'{}'::jsonb) || %s WHERE company_id=%s AND version=%s",
                       (Jsonb(counts), version["company_id"], version["version"]))


def publish(connection, version, *, stats=None, swept=False):
    """Make a complete version visible. A full rebuild retires what it did not see;
    vouchers dated before the coverage window leave the mirror."""
    v, company_id = version["version"], version["company_id"]
    if version["kind"] == "full":
        for table in ("mirror_masters", "mirror_vouchers"):
            unseen = connection.execute(
                f"""UPDATE {table} SET superseded_in=%s WHERE company_id=%s AND superseded_in IS NULL
                    AND synced_in < %s AND seen_in < %s RETURNING guid""", (v, company_id, v, v)).fetchall()
            if table == "mirror_vouchers" and unseen:
                connection.execute("""UPDATE mirror_bill_refs SET superseded_in=%s WHERE company_id=%s
                    AND voucher_guid=ANY(%s) AND superseded_in IS NULL""", (v, company_id, [r["guid"] for r in unseen]))
    early = [r["guid"] for r in connection.execute(
        "SELECT guid FROM mirror_vouchers WHERE company_id=%s AND superseded_in IS NULL AND date < %s",
        (company_id, version["coverage"]["from"])).fetchall()]
    if early:
        tombstone(connection, version, "vouchers", early)
    return connection.execute(
        """UPDATE mirror_versions SET state='published',published_at=now(),swept=%s,stats=stats || %s
           WHERE company_id=%s AND version=%s AND state='building' RETURNING *""",
        (swept, Jsonb(stats or {}), company_id, v)).fetchone()


def abandon(connection, version, reason=None):
    """Revert everything an unpublished version touched."""
    v, company_id = version["version"], version["company_id"]
    for table in ("mirror_masters", "mirror_vouchers", "mirror_bill_refs"):
        connection.execute(f"DELETE FROM {table} WHERE company_id=%s AND synced_in=%s", (company_id, v))
        connection.execute(f"UPDATE {table} SET superseded_in=NULL WHERE company_id=%s AND superseded_in=%s", (company_id, v))
    for table in ("mirror_masters", "mirror_vouchers"):
        connection.execute(f"UPDATE {table} SET seen_in=synced_in WHERE company_id=%s AND seen_in=%s", (company_id, v))
    connection.execute("""UPDATE mirror_versions SET state='abandoned',stats=stats || %s
                          WHERE company_id=%s AND version=%s""",
                       (Jsonb({"abandoned": reason or "incomplete"}), company_id, v))


def collect(connection, company_id):
    """Delete rows no pinned or current version can see any more."""
    floor = connection.execute(
        """SELECT least(
               (SELECT max(version) FROM mirror_versions WHERE company_id=%(c)s AND state='published'),
               (SELECT min((pins->>%(k)s)::integer) FROM runs WHERE pins ? %(k)s
                    AND state NOT IN ('completed','failed'))) AS floor""",
        {"c": company_id, "k": str(company_id)}).fetchone()["floor"]
    if floor is None:
        return 0
    return sum(connection.execute(f"DELETE FROM {table} WHERE company_id=%s AND superseded_in <= %s",
                                  (company_id, floor)).rowcount
               for table in ("mirror_masters", "mirror_vouchers", "mirror_bill_refs"))


def lost(connection, company_id, before, after, *, examples=5):
    """What one version holds that a later one lacks, within the dates both cover.

    {missing, older, examples}: vouchers visible at `before` and absent at `after`, the latest few of them, and
    vouchers whose AlterID at `after` is lower, an earlier edit. Used when a company moved PCs: the new PC's copy
    may be an older backup.
    """
    span = {"c": company_id, "b": before["version"], "a": after["version"], "limit": examples,
            "from": max(before["coverage"]["from"], after["coverage"]["from"]),
            "to": min(before["coverage"]["to"], after["coverage"]["to"])}
    visible = "{t}.synced_in <= %({v})s AND ({t}.superseded_in IS NULL OR {t}.superseded_in > %({v})s)"
    pairs = f"""FROM mirror_vouchers b LEFT JOIN mirror_vouchers a ON a.company_id=b.company_id AND a.guid=b.guid
                    AND {visible.format(t="a", v="a")}
                WHERE b.company_id=%(c)s AND {visible.format(t="b", v="b")} AND b.date BETWEEN %(from)s AND %(to)s"""
    counts = connection.execute(
        f"""SELECT count(*) FILTER (WHERE a.guid IS NULL) AS missing,
                   count(*) FILTER (WHERE a.alter_id < b.alter_id) AS older {pairs}""", span).fetchone()
    rows = connection.execute(
        f"SELECT b.* {pairs} AND a.guid IS NULL ORDER BY b.date DESC, b.guid LIMIT %(limit)s", span).fetchall()
    return {"missing": counts["missing"], "older": counts["older"], "examples": rows}


# --- reads at a pinned version -----------------------------------------------------

def masters(connection, company_id, version, *, types=None, guids=None):
    return connection.execute(
        f"""SELECT * FROM mirror_masters WHERE company_id=%(c)s AND {_VISIBLE}
            AND (%(types)s::text[] IS NULL OR type = ANY(%(types)s))
            AND (%(guids)s::text[] IS NULL OR guid = ANY(%(guids)s)) ORDER BY type, name_key, guid""",
        {"c": company_id, "v": version, "types": types, "guids": guids}).fetchall()


def vouchers(connection, company_id, version, *, date_from=None, date_to=None, guids=None, limit=None):
    return connection.execute(
        f"""SELECT * FROM mirror_vouchers WHERE company_id=%(c)s AND {_VISIBLE}
            AND (%(from)s::date IS NULL OR date >= %(from)s) AND (%(to)s::date IS NULL OR date <= %(to)s)
            AND (%(guids)s::text[] IS NULL OR guid = ANY(%(guids)s))
            ORDER BY date, guid LIMIT %(limit)s""",
        {"c": company_id, "v": version, "from": date_from, "to": date_to, "guids": guids, "limit": limit}).fetchall()


def voucher_counts(connection, company_id, version, date_from, date_to):
    rows = connection.execute(
        f"""SELECT date, count(*) AS n FROM mirror_vouchers WHERE company_id=%(c)s AND {_VISIBLE}
            AND date BETWEEN %(from)s AND %(to)s GROUP BY date""",
        {"c": company_id, "v": version, "from": date_from, "to": date_to}).fetchall()
    return {row["date"].isoformat(): row["n"] for row in rows}


def open_bills(connection, company_id, version, ledgers):
    """The bills of these ledgers (by name) with a balance at a pinned version, oldest first.

    Each is {ledger, name, date, balance_cents, advance}, the balance signed as
    Tally signs amounts, credit positive. References in cancelled or optional
    vouchers settle nothing. A bill is balanced only from its origin: a New Ref
    or Advance in a mirrored voucher, or a ledger's opening bill when the books
    begin inside the mirror's window. Before that, what settled an opening bill
    is not mirrored, nor is the origin of a bill a mirrored reference settles,
    so such bills are left out rather than balanced wrongly.
    """
    keys = [normalized(ledger) for ledger in ledgers]
    window = connection.execute(
        """SELECT v.coverage->>'from' AS start, c.books_from FROM mirror_versions v
           JOIN companies c ON c.id=v.company_id WHERE v.company_id=%s AND v.version=%s""",
        (company_id, version)).fetchone()
    bills = {}
    if window and window["books_from"].isoformat() >= window["start"]:
        for row in connection.execute(
                f"""SELECT name, name_key, data FROM mirror_masters WHERE company_id=%(c)s AND {_VISIBLE}
                    AND type='LEDGER' AND name_key = ANY(%(keys)s)""", {"c": company_id, "v": version, "keys": keys}):
            for bill in (item for item in _list(row["data"].get("BILLALLOCATIONS.LIST")) if isinstance(item, dict)):
                name, stamp, cents = text(bill.get("NAME")), text(bill.get("BILLDATE")), _cents(bill.get("OPENINGBALANCE"))
                if name and cents and re.fullmatch(r"\d{8}", stamp):
                    bills[(row["name_key"], name)] = {
                        "ledger": row["name"], "name": name, "date": date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:])),
                        "balance_cents": cents, "advance": text(bill.get("ISADVANCE")).casefold() == "yes",
                        "opened": True}
    for ref in connection.execute(
            """SELECT r.ledger_key, r.name, min(r.ledger) AS ledger, sum(r.amount_cents)::bigint AS cents,
                      min(r.date) AS used,
                      min(r.date) FILTER (WHERE r.bill_type IN ('New Ref','Advance')) AS opened,
                      bool_or(r.bill_type = 'Advance') AS advance
               FROM mirror_bill_refs r JOIN mirror_vouchers v
                   ON v.company_id=r.company_id AND v.guid=r.voucher_guid AND v.synced_in=r.synced_in
               WHERE r.company_id=%(c)s AND r.ledger_key = ANY(%(keys)s) AND NOT v.cancelled AND NOT v.optional
                   AND r.synced_in <= %(v)s AND (r.superseded_in IS NULL OR r.superseded_in > %(v)s)
               GROUP BY r.ledger_key, r.name""", {"c": company_id, "v": version, "keys": keys}):
        bill = bills.setdefault((ref["ledger_key"], ref["name"]), {
            "ledger": ref["ledger"], "name": ref["name"], "date": ref["opened"] or ref["used"], "balance_cents": 0,
            "advance": False, "opened": ref["opened"] is not None})
        bill["balance_cents"] += ref["cents"]
        bill["advance"] = bill["advance"] or ref["advance"]
        bill["opened"] = bill["opened"] or ref["opened"] is not None
    return sorted(({key: value for key, value in bill.items() if key != "opened"} for bill in bills.values()
                   if bill["opened"] and bill["balance_cents"]), key=lambda bill: (bill["date"], bill["name"]))


def search_masters(connection, company_id, version, types, subject, *, limit=8):
    """Masters of these types matching one subject: by GSTIN, bank account number, HSN, or every word of a name.

    A statement often masks an account number ("XXXXXX1234"), so its digits
    match the end of a ledger's account number. An HSN heading matches the
    codes under it. Names match on all words, in the name or any alias; an
    exact name sorts first.
    """
    digits = re.sub(r"\D", "", subject)
    found = GSTIN.search(subject.upper())
    words = [word for word in normalized(subject).split() if len(word) > 1][:8]
    if not (found or len(digits) >= 4 or words):
        return []
    return connection.execute(
        f"""SELECT * FROM mirror_masters WHERE company_id=%(c)s AND {_VISIBLE} AND type = ANY(%(types)s) AND (
                gstin = %(gstin)s
                OR (%(digits)s::text IS NOT NULL AND bank_account LIKE '%%' || %(digits)s)
                OR (%(digits)s::text IS NOT NULL AND hsn LIKE %(digits)s || '%%')
                OR (cardinality(%(words)s::text[]) > 0 AND NOT EXISTS (
                    SELECT 1 FROM unnest(%(words)s::text[]) AS word
                    WHERE position(word IN name_key || ' ' || lower(array_to_string(aliases, ' '))) = 0)))
            ORDER BY (name_key = %(key)s) DESC, length(name), guid LIMIT %(limit)s""",
        {"c": company_id, "v": version, "types": list(types), "gstin": found.group(0) if found else None,
         "digits": digits if len(digits) >= 4 else None, "words": words, "key": normalized(subject),
         "limit": limit}).fetchall()


def named(connection, company_id, version, kind, subjects):
    """Masters of one type whose GUID, or whose name ignoring case and spacing, is one of these subjects."""
    return connection.execute(
        f"""SELECT * FROM mirror_masters WHERE company_id=%(c)s AND {_VISIBLE} AND type=%(t)s
                AND (guid = ANY(%(s)s) OR name_key = ANY(%(k)s)) ORDER BY name_key, guid""",
        {"c": company_id, "v": version, "t": kind, "s": list(subjects),
         "k": [normalized(subject) for subject in subjects]}).fetchall()


def ledger_history(connection, company_id, version, ledgers, *, limit=10):
    """The newest vouchers that post to any of these ledgers, cancelled and optional ones excluded."""
    return connection.execute(
        f"""SELECT * FROM mirror_vouchers WHERE company_id=%(c)s AND {_VISIBLE} AND ledgers && %(ledgers)s::text[]
                AND NOT cancelled AND NOT optional ORDER BY date DESC, guid LIMIT %(limit)s""",
        {"c": company_id, "v": version, "ledgers": list(ledgers), "limit": limit}).fetchall()


def vouchers_mentioning(connection, company_id, version, needle, date_from, date_to, *, limit=10):
    """Vouchers in a date window whose reference or narration contains this text, such as a UTR."""
    return connection.execute(
        f"""SELECT * FROM mirror_vouchers WHERE company_id=%(c)s AND {_VISIBLE} AND date BETWEEN %(from)s AND %(to)s
                AND NOT cancelled AND (position(%(needle)s IN upper(reference)) > 0
                                       OR position(%(needle)s IN upper(narration)) > 0)
            ORDER BY date DESC, guid LIMIT %(limit)s""",
        {"c": company_id, "v": version, "needle": needle.upper(), "from": date_from, "to": date_to,
         "limit": limit}).fetchall()


def company_view(connection, company, version):
    """The company in the shape the voucher and statement gates already read.

    Equivalent to a confirmed discovery company: identity plus every master as
    {type, data}. Only the pinned version's rows are included.
    """
    rows = masters(connection, company["id"], version)
    identity = next((row["data"] for row in rows if row["type"] == "COMPANY"), {"@_NAME": company["name"],
                                                                              "GUID": company["guid"]})
    return {"company": company["name"], "company_guid": company["guid"], "port": company.get("port") or 9000,
            "identity": identity, "masters": {"records": [{"type": row["type"], "data": row["data"]}
                                                          for row in rows if row["type"] != "COMPANY"]}}
