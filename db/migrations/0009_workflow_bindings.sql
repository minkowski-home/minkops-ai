-- Installed composition is trusted state, separate from editable preferences.
ALTER TABLE workflows ADD COLUMN execution_binding jsonb;
ALTER TABLE workflows ADD CONSTRAINT workflows_execution_binding_object
    CHECK (execution_binding IS NULL OR jsonb_typeof(execution_binding) = 'object');

-- Keep the durable rows, IDs, locks, FKs, and historical events. The updatable
-- view retains existing Accounts/native contracts during application rollout.
ALTER TABLE account_runs RENAME TO workflow_runs;
ALTER TABLE workflow_runs DROP CONSTRAINT account_runs_workflow_key_check;
ALTER TABLE workflow_runs ADD CONSTRAINT workflow_runs_registered_workflow
    FOREIGN KEY (tenant_id, workflow_key) REFERENCES workflows (tenant_id, key);
CREATE VIEW account_runs AS SELECT * FROM workflow_runs;

-- Existing installs keep their exact settings/status. New installs use the CLI.
UPDATE workflows SET execution_binding = jsonb_build_object(
    'definition', 'accounts-desk/workflows/' || key,
    'handler', CASE key WHEN 'source-discovery' THEN 'accounts.discovery' ELSE 'accounts.bill' END,
    'presentation', CASE key WHEN 'source-discovery' THEN 'accounts-discovery' ELSE 'accounts-bill' END,
    'policies', '[]'::jsonb, 'capabilities', '["files.snapshot"]'::jsonb
) WHERE key IN ('source-discovery', 'bill-entry') AND EXISTS (
    SELECT 1 FROM workflow_employees link JOIN employees e
      ON e.tenant_id=link.tenant_id AND e.id=link.employee_id
    WHERE link.tenant_id=workflows.tenant_id AND link.workflow_id=workflows.id
      AND e.key='accounts-desk'
);
