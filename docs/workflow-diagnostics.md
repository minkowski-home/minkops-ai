# Workflow support diagnostics

Support engineers with database access can follow a run end to end. Every query
is scoped to one tenant; take the run from its task (`runs.task_id`). Nothing here
is shown to customers, and no diagnostics endpoint exists.

**The run and its items.** Each item is one bill file, statement chunk or layout,
with its state, attempts and the last failure's code and reason:

```sql
SELECT ordinal, kind, state, attempt, error_code, error, waiting_on, queued_at, started_at, finished_at
FROM run_items WHERE tenant_id = :tenant_id AND run_id = :run_id ORDER BY ordinal;
```

**What each session looked up and proposed.** Every tool call is logged once per
session and call ID, with the answer the model was given:

```sql
SELECT c.session_id, c.name, c.success, c.duration_ms, c.arguments, left(c.answer, 500) AS answer
FROM tool_calls c JOIN run_items i ON i.id = c.item_id
WHERE i.tenant_id = :tenant_id AND i.run_id = :run_id ORDER BY i.ordinal, c.created_at;
```

**Sessions and spend.** Each attempt's provider session, with the usage its turn
reported (`work.usage` sums them for a run):

```sql
SELECT i.ordinal, s.attempt, s.session_id, s.opened_at, s.finished_at, s.closed, s.usage
FROM item_sessions s JOIN run_items i ON i.id = s.item_id
WHERE i.tenant_id = :tenant_id AND i.run_id = :run_id ORDER BY i.ordinal, s.opened_at;
```

**What waits for a person.** A record's status, holds and the reasons its
reviewer reads:

```sql
SELECT position, kind, status, hold_codes, review_reasons, version
FROM run_records WHERE tenant_id = :tenant_id AND run_id = :run_id ORDER BY item_id, position;
```

**Native work.** Syncs, saves and checks on the PC, with their receipts, and the
diagnostics a PC sent (versions, the Tally session and recent outcomes; never
bill data):

```sql
SELECT id, device_id, operation, state, input, result, error, created_at, updated_at
FROM desktop_jobs WHERE tenant_id = :tenant_id AND task_id = :task_id ORDER BY created_at;
```

Windows crash details stay in the companion's local diagnostic file, and Send
diagnostics stores a PC's summary in `desktop_diagnostics` for 30 days (see
[Windows app](windows-app.md#tally-session-diagnostics-and-uncertain-writes)).
Provider reasoning, documents, request XML and credentials are never recorded.
