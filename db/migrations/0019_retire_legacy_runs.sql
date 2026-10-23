-- Bills and statements are now planned only as protocol-5 vouchers; the
-- fixed-field, Excel and Tally-references paths that served older runs are gone.
-- Retire unfinished work still pinned to them the way Stop does: cancel its
-- unfinished writes and its jobs, fail its runs, stop its tasks and leave one
-- shared attention item. Verified saves, receipts and history stay intact, and a
-- new run is safe: vouchers already in Tally are recognised as duplicates.
CREATE TEMPORARY TABLE retired_runs AS
SELECT r.tenant_id, r.id, r.task_id, r.workflow_key, r.parent_run_id
FROM workflow_runs r
WHERE r.state NOT IN ('completed', 'failed')
  AND ((r.workflow_key = 'bill-entry'
        AND coalesce(r.config #>> '{tally_target,voucher_proposal_version}', '') <> '1')
    OR (r.workflow_key = 'statement-entry'
        AND EXISTS (
            SELECT 1
            FROM jsonb_array_elements(CASE WHEN jsonb_typeof(r.result -> 'records') = 'array'
                                           THEN r.result -> 'records' ELSE '[]'::jsonb END) AS row(value)
            WHERE row.value #>> '{plan,format_version}' = '4'
              AND coalesce(row.value ->> 'status', '') NOT IN ('saved', 'duplicate', 'rejected'))));

UPDATE account_tally_writes w SET cancelled_at = now()
FROM retired_runs r
WHERE w.tenant_id = r.tenant_id AND w.run_id = r.id AND w.finished_at IS NULL AND w.cancelled_at IS NULL;

-- No handler serves these operations any more; a late receipt is rejected and
-- the attention item below asks the operator to verify Tally instead.
UPDATE desktop_jobs j
SET state = 'failed', error = 'This run used a retired contract. Start a new run.', updated_at = now()
WHERE j.state IN ('queued', 'executing') AND j.operation <> 'attention.refresh'
  AND (j.operation IN ('accounts.save', 'tally.references')
       OR EXISTS (SELECT 1 FROM retired_runs r WHERE r.tenant_id = j.tenant_id AND r.task_id = j.task_id));

UPDATE workflow_runs w
SET state = 'failed', updated_at = now(),
    error = 'Retired: this run used a bill or statement contract Minkops no longer writes. Verify any underway save in Tally. Start a new run.',
    config = w.config || '{"timeout_cancel_pending": true}'::jsonb
FROM retired_runs r
WHERE w.tenant_id = r.tenant_id AND w.id = r.id;

INSERT INTO task_events (tenant_id, task_id, event_type, summary, progress)
SELECT t.tenant_id, t.id, 'control.stop', 'Retired: verify any underway save in Tally, then start a new run.', t.progress
FROM tasks t
WHERE EXISTS (SELECT 1 FROM retired_runs r WHERE r.tenant_id = t.tenant_id AND r.task_id = t.id);

UPDATE tasks t
SET control_state = 'stopped', updated_at = now(),
    summary = 'Retired: verify any underway save in Tally, then start a new run.'
WHERE EXISTS (SELECT 1 FROM retired_runs r WHERE r.tenant_id = t.tenant_id AND r.task_id = t.id);

INSERT INTO attention_items (tenant_id, task_id, event_key, identifier, label, kind, target)
SELECT tenant_id, task_id, 'retired:' || id,
       CASE workflow_key WHEN 'statement-entry' THEN 'Statement entry run' ELSE 'Bill entry run' END,
       'Run retired', 'manual',
       jsonb_build_object('reason', 'This run used a contract Minkops no longer writes. Verify any underway save in Tally, then start a new run.')
FROM retired_runs
WHERE parent_run_id IS NULL
ON CONFLICT (tenant_id, event_key) DO NOTHING;

INSERT INTO attention_events (tenant_id, item_id, actor_id, action, summary)
SELECT a.tenant_id, a.id, NULL, 'retired', 'Unfinished work on a retired contract was stopped during an upgrade.'
FROM attention_items a
JOIN retired_runs r ON r.tenant_id = a.tenant_id AND a.event_key = 'retired:' || r.id;

DROP TABLE retired_runs;

-- Historical runs from before pinned runtime bindings now carry the binding the
-- application used to infer from their workflow key.
UPDATE workflow_runs
SET config = config || jsonb_build_object('runtime_binding', CASE workflow_key
        WHEN 'source-discovery' THEN '{"handler": "accounts.discovery", "presentation": "accounts-discovery"}'::jsonb
        ELSE '{"handler": "accounts.bill", "presentation": "accounts-bill"}'::jsonb END)
WHERE workflow_key IN ('source-discovery', 'bill-entry') AND NOT config ? 'runtime_binding';
