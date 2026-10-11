# Workflow support diagnostics

Apply `db/migrations/0002_workflow_diagnostics.sql` with the normal migration
runner before releasing the API/worker. The bounded production `--drain` and
continuous local worker both use four independent AI lanes. Native destination
writes retain their existing ordering, approval and reconciliation rules.

Engineers/support with database access can inspect a task and all its child runs:

```sql
SELECT d.created_at, r.id AS run_id, r.parent_run_id, r.workflow_key,
       r.state, r.session_id, r.turn_id, d.level, d.event_type,
       d.summary, d.details, r.error
FROM workflow_run_diagnostics d
JOIN workflow_runs r ON (r.tenant_id, r.id) = (d.tenant_id, d.run_id)
WHERE r.tenant_id = :tenant_id AND r.task_id = :task_id
ORDER BY d.created_at, d.id;
```

`worker.claimed` includes run age and queued wait in milliseconds. Stage records
cover preparation, hosted execution/result retrieval, schema/business validation,
outcome persistence and environment cleanup. AI start records include file IDs,
byte sizes, pinned model and whether execution resumes a saved session. Hosted
events retain event kinds and session/turn identifiers with database timestamps.
This establishes overlapping AI execution and separates queue/provider/validation
delay; it does not attribute provider time to undocumented internal operations.

Errors include exception type, code frame locations, HTTP status/SQLSTATE when
available, and exact schema path/rule. Raw schema instances remain in the existing
saved proposal; raw provider exceptions, reasoning, documents, request XML and
credentials are excluded from diagnostics. The product timeline remains concise.
Each diagnostic uses a short independent transaction so failure rollback cannot
erase it or accidentally commit business work. Database/lock timeouts are bounded;
a diagnostic outage emits a server fallback without changing business outcomes.

Native job events, human-readable errors and verified receipts are already durable:

```sql
SELECT id, device_id, operation, state, input, result, error, created_at, updated_at
FROM desktop_jobs
WHERE tenant_id = :tenant_id AND task_id = :task_id
ORDER BY created_at;
```

Windows crash details remain in the companion's local diagnostic file. No customer
diagnostics screen or public diagnostics endpoint is introduced. These records
currently follow run retention and cascade on run deletion; choose an explicit
time-based retention policy when the support evidence volume warrants it.
