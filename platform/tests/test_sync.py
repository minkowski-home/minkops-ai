"""The no-AI sync: the companion collects, the server decides, guards and publishes."""

import os
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from minkops_platform import work
from minkops_platform.accounts import mirror, sync
from minkops_platform.errors import ServiceError

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")
TODAY = date(2026, 10, 21)


class Tally:
    """A scripted company as the companion would read it."""

    def __init__(self, name="Test Company", guid=None):
        self.identity = {"name": name, "guid": guid or str(uuid4()), "company_number": "100000",
                         "books_from": "2026-04-01"}
        self.masters, self.vouchers, self.alter = {}, {}, 0

    def bump(self):
        self.alter += 1
        return self.alter

    def ledger(self, name, parent="Sundry Creditors"):
        guid = f"{self.identity['guid']}-L{len(self.masters):04}"
        self.masters[guid] = {"type": "LEDGER", "data": {"@_NAME": name, "GUID": guid, "PARENT": parent,
                                                         "ALTERID": str(self.bump())}}
        return guid

    def voucher(self, day, amount="1000.00", *, guid=None):
        guid = guid or f"{self.identity['guid']}-V{len(self.vouchers):04}"
        self.vouchers[guid] = {"GUID": guid, "MASTERID": str(len(self.vouchers) + 1), "ALTERID": str(self.bump()),
                               "DATE": day.replace("-", ""), "VOUCHERTYPENAME": "Payment", "VOUCHERNUMBER": "1",
                               "ALLLEDGERENTRIES.LIST": [{"LEDGERNAME": "Bank", "AMOUNT": amount}]}
        return guid

    def markers(self):
        masters = [int(m["data"]["ALTERID"]) for m in self.masters.values()]
        vouchers = [int(v["ALTERID"]) for v in self.vouchers.values()]
        return {"alt_mst_id": max(masters, default=0), "alt_vch_id": max(vouchers, default=0),
                "last_voucher_date": max((v["DATE"] for v in self.vouchers.values()), default=None)}

    def counts(self):
        found = {}
        for voucher in self.vouchers.values():
            day = f"{voucher['DATE'][:4]}-{voucher['DATE'][4:6]}-{voucher['DATE'][6:]}"
            found[day] = found.get(day, 0) + 1
        return found


class Companion:
    """Drives the server's page protocol exactly as connectors/desktop/src/sync.js does."""

    def __init__(self, db, device, job):
        self.db, self.device, self.job, self.seq = db, device, job, 0

    def send(self, kind, **body):
        response = sync.accept(self.db, self.device, self.job, {"seq": self.seq, "kind": kind, **body})
        self.seq += 1
        return response

    def run(self, *tallies, census_lie=None):
        plan = sync.plan(self.db, self.device, self.job, today=TODAY)
        by_guid = {t.identity["guid"]: t for t in tallies}
        answer = self.send("companies", companies=[{**t.identity, "markers": t.markers()} for t in tallies])
        done = []
        for step in answer["instructions"]:
            if step["mode"] == "skip":
                continue
            tally = by_guid[step["guid"]]
            after = step.get("after") or {}
            masters = [m for m in tally.masters.values() if int(m["data"]["ALTERID"]) > after.get("alt_mst_id", 0)]
            self.send("masters", company=step["company"], records=masters)
            vouchers = [v for v in tally.vouchers.values() if int(v["ALTERID"]) > after.get("alt_vch_id", 0)]
            self.send("vouchers", company=step["company"], records=vouchers)
            if step["sweep"]:
                ranges = self.send("counts", company=step["company"], counts=tally.counts())["census"]
                for span in ranges:
                    entries = [{"guid": v["GUID"], "alter_id": int(v["ALTERID"]), "number": v["VOUCHERNUMBER"],
                                "date": f"{v['DATE'][:4]}-{v['DATE'][4:6]}-{v['DATE'][6:]}"}
                               for v in tally.vouchers.values()
                               if span["from"].replace("-", "") <= v["DATE"] <= span["to"].replace("-", "")]
                    if census_lie:
                        entries = entries[:census_lie]
                    refetch = self.send("census", company=step["company"], **span, entries=entries)["refetch"]
                    if refetch:
                        self.send("vouchers", company=step["company"], records=[tally.vouchers[g] for g in refetch])
            done.append({"company": step["company"], "complete": True})
        summary = sync.finish(self.db, self.device, self.job, {"companies": done})
        # desktop.finish records the receipt; the job is then terminal.
        self.db.execute("UPDATE desktop_jobs SET state='completed' WHERE id=%s", (self.job["id"],))
        return plan, answer, summary


@pytest.fixture
def pc():
    import factory
    with factory.connect() as db:
        tenant = factory.tenant(db)
        owner = factory.user(db, tenant, role="admin")
        device = factory.device(db, tenant, owner)
        client = factory.client(db, tenant)
        context = {"db": db, "tenant": tenant, "owner": owner, "device": device, "client": client,
                   "member": factory.member(db, tenant, owner)}
        yield context
        db.rollback()


def start(pc, reason="requested"):
    job = sync.request(pc["db"], pc["tenant"], pc["owner"], pc["member"], pc["device"]["id"], reason=reason)
    return pc["db"].execute("SELECT * FROM desktop_jobs WHERE id=%s", (job["id"],)).fetchone()


def authorised(pc, tally):
    """The first sync finds the company; one decision authorises it."""
    _, answer, _ = Companion(pc["db"], pc["device"], start(pc)).run(tally)
    assert answer["instructions"][0]["mode"] == "skip" and answer["instructions"][0]["reason"] == "pending"
    company = pc["db"].execute("SELECT * FROM companies WHERE device_id=%s AND guid=%s",
                               (pc["device"]["id"], tally.identity["guid"])).fetchone()
    item = pc["db"].execute("SELECT * FROM attention_items WHERE tenant_id=%s AND event_key=%s",
                            (pc["tenant"]["id"], f"company:{company['id']}")).fetchone()
    assert (company["status"], item["label"]) == ("pending", "New company found")
    sync.authorise(pc["db"], pc["tenant"], pc["owner"], pc["member"], company["id"], pc["client"]["slug"])
    return company


def test_a_new_company_is_found_authorised_and_mirrored_in_full(pc):
    tally = Tally()
    supplier = tally.ledger("Supplier")
    tally.voucher("2026-09-01")
    company = authorised(pc, tally)
    plan, answer, summary = Companion(pc["db"], pc["device"], start(pc)).run(tally)
    assert plan["port"] == 9000 and [c["guid"] for c in plan["companies"]] == [tally.identity["guid"]]
    step = answer["instructions"][0]
    assert (step["mode"], step["window"]) == ("full", {"from": "2026-04-01", "to": "2027-03-31"})
    assert summary["published"] == [str(company["id"])]
    version = mirror.latest(pc["db"], company["id"])
    assert version["markers"] == tally.markers() and version["kind"] == "full"
    assert [m["guid"] for m in mirror.masters(pc["db"], company["id"], version["version"])] == [supplier]
    item = pc["db"].execute("SELECT status FROM attention_items WHERE event_key=%s", (f"company:{company['id']}",)).fetchone()
    assert item["status"] == "done"


def test_unchanged_markers_skip_and_moved_markers_fetch_only_the_delta(pc):
    tally = Tally()
    tally.ledger("Supplier")
    tally.voucher("2026-09-01")
    company = authorised(pc, tally)
    Companion(pc["db"], pc["device"], start(pc)).run(tally)
    _, answer, summary = Companion(pc["db"], pc["device"], start(pc)).run(tally)
    assert answer["instructions"][0]["mode"] == "skip" and summary["published"] == []
    before = tally.markers()
    tally.voucher("2026-09-02")
    _, answer, summary = Companion(pc["db"], pc["device"], start(pc)).run(tally)
    step = answer["instructions"][0]
    assert (step["mode"], step["after"]) == ("delta", {"alt_mst_id": before["alt_mst_id"], "alt_vch_id": before["alt_vch_id"]})
    version = mirror.latest(pc["db"], company["id"])
    assert version["version"] == 2 and len(mirror.vouchers(pc["db"], company["id"], 2)) == 2


def test_a_deletion_found_by_the_census_becomes_a_tombstone(pc):
    tally = Tally()
    first, second = tally.voucher("2026-09-01"), tally.voucher("2026-09-02")
    company = authorised(pc, tally)
    Companion(pc["db"], pc["device"], start(pc)).run(tally)
    del tally.vouchers[second]
    tally.bump()  # Deleting moves Tally's counter, so the next sync runs.
    tally.ledger("Moved the masters counter too")
    Companion(pc["db"], pc["device"], start(pc)).run(tally)
    version = mirror.latest(pc["db"], company["id"])["version"]
    assert [v["guid"] for v in mirror.vouchers(pc["db"], company["id"], version)] == [first]


def test_a_census_that_disagrees_with_the_counts_never_records_a_deletion(pc):
    tally = Tally()
    tally.voucher("2026-09-01")
    tally.voucher("2026-09-01")
    company = authorised(pc, tally)
    Companion(pc["db"], pc["device"], start(pc)).run(tally)
    tally.ledger("Move the counter")
    # A truncated census reports one voucher where Tally's own count says two.
    _, _, summary = Companion(pc["db"], pc["device"], start(pc, reason="nightly")).run(tally, census_lie=1)
    version = mirror.latest(pc["db"], company["id"])
    assert len(mirror.vouchers(pc["db"], company["id"], version["version"])) == 2
    assert version["stats"]["census_mismatch_dates"] == ["2026-09-01"]


def test_a_changed_voucher_seen_only_in_the_census_is_refetched(pc):
    tally = Tally()
    guid = tally.voucher("2026-09-01")
    company = authorised(pc, tally)
    Companion(pc["db"], pc["device"], start(pc)).run(tally)
    # Renumbering after a deletion changes the number without a new AlterID.
    tally.vouchers[guid]["VOUCHERNUMBER"] = "9"
    tally.ledger("Move the counter")
    Companion(pc["db"], pc["device"], start(pc, reason="nightly")).run(tally)
    version = mirror.latest(pc["db"], company["id"])["version"]
    assert mirror.vouchers(pc["db"], company["id"], version)[0]["number"] == "9"


def test_a_marker_that_goes_backwards_rebuilds_in_full(pc):
    tally = Tally()
    tally.voucher("2026-09-01")
    tally.voucher("2026-09-02")
    company = authorised(pc, tally)
    Companion(pc["db"], pc["device"], start(pc)).run(tally)
    # An older backup was restored: the counters dropped and a voucher vanished.
    tally.vouchers.pop(next(iter(tally.vouchers)))
    tally.alter = 1
    for voucher in tally.vouchers.values():
        voucher["ALTERID"] = "1"
    _, answer, _ = Companion(pc["db"], pc["device"], start(pc)).run(tally)
    assert (answer["instructions"][0]["mode"], answer["instructions"][0]["reason"]) == ("full", "marker_regressed")
    version = mirror.latest(pc["db"], company["id"])["version"]
    assert len(mirror.vouchers(pc["db"], company["id"], version)) == 1


def test_a_renamed_company_rebuilds_and_a_split_sibling_is_a_new_company(pc):
    tally = Tally()
    tally.voucher("2026-09-01")
    company = authorised(pc, tally)
    Companion(pc["db"], pc["device"], start(pc)).run(tally)
    tally.identity["name"] = "Test Company (renamed)"
    _, answer, _ = Companion(pc["db"], pc["device"], start(pc)).run(tally)
    assert (answer["instructions"][0]["mode"], answer["instructions"][0]["reason"]) == ("full", "identity_changed")
    assert pc["db"].execute("SELECT name FROM companies WHERE id=%s", (company["id"],)).fetchone()["name"] == \
        "Test Company (renamed)"
    sibling = Tally(name="Test Company (from 1-Apr-2027)", guid=tally.identity["guid"])
    sibling.identity["books_from"] = "2027-04-01"
    _, answer, _ = Companion(pc["db"], pc["device"], start(pc)).run(sibling)
    assert answer["instructions"][0]["reason"] == "pending"


def test_pages_are_accepted_once_and_a_changed_resend_conflicts(pc):
    tally = Tally()
    tally.voucher("2026-09-01")
    authorised(pc, tally)
    companion = Companion(pc["db"], pc["device"], start(pc))
    answer = companion.send("companies", companies=[{**tally.identity, "markers": tally.markers()}])
    companion.seq = 0
    assert companion.send("companies", companies=[{**tally.identity, "markers": tally.markers()}]) == answer
    companion.seq = 0
    with pytest.raises(ServiceError) as conflict:
        companion.send("companies", companies=[])
    assert conflict.value.kind == "conflict"


def test_an_incomplete_or_failed_sync_publishes_nothing_and_keeps_the_previous_version(pc):
    tally = Tally()
    tally.voucher("2026-09-01")
    company = authorised(pc, tally)
    Companion(pc["db"], pc["device"], start(pc)).run(tally)
    tally.voucher("2026-09-02")
    job = start(pc)
    companion = Companion(pc["db"], pc["device"], job)
    step = companion.send("companies", companies=[{**tally.identity, "markers": tally.markers()}])["instructions"][0]
    companion.send("vouchers", company=step["company"], records=list(tally.vouchers.values()))
    summary = sync.fail(pc["db"], pc["device"], job, "Tally isn't open on this PC.")
    pc["db"].execute("UPDATE desktop_jobs SET state='failed' WHERE id=%s", (job["id"],))
    assert summary["abandoned"] == [str(company["id"])]
    assert mirror.latest(pc["db"], company["id"])["version"] == 1
    assert len(mirror.vouchers(pc["db"], company["id"], 1)) == 1


def test_a_finished_sync_releases_runs_that_waited_for_it(pc):
    import factory
    tally = Tally()
    authorised(pc, tally)
    flow = factory.workflow(pc["db"], pc["tenant"])
    run = work.launch(pc["db"], tenant_id=pc["tenant"]["id"], client_id=pc["client"]["id"], workflow=flow,
                      handler="desk.test", definition_version="1.0.0", bundle={"x": 1}, actor_id=pc["owner"]["id"],
                      request_key=uuid4(), request_hash="h", config={}, title="Bill entry",
                      items=[work.ItemSpec("bill", {"file_id": "a"}, waiting_on=sync.blocker(pc["device"]["id"]))])
    Companion(pc["db"], pc["device"], start(pc)).run(tally)
    assert pc["db"].execute("SELECT state FROM run_items WHERE run_id=%s", (run["id"],)).fetchone()["state"] == "queued"


def test_the_window_covers_the_current_and_previous_financial_years_from_books_start():
    assert sync.window(date(2026, 10, 21), date(2020, 4, 1)) == {"from": "2025-04-01", "to": "2027-03-31"}
    assert sync.window(date(2027, 2, 1), date(2026, 4, 1)) == {"from": "2026-04-01", "to": "2027-03-31"}
    assert sync.window(date(2027, 4, 1), date(2026, 4, 1)) == {"from": "2026-04-01", "to": "2028-03-31"}


def test_a_nightly_sweep_is_due_after_twenty_hours():
    published = datetime(2026, 10, 21, 0, 0, tzinfo=UTC)
    assert not sync.sweep_due({"published_at": published, "swept": True}, datetime(2026, 10, 21, 19, tzinfo=UTC))
    assert sync.sweep_due({"published_at": published, "swept": True}, datetime(2026, 10, 21, 21, tzinfo=UTC))
