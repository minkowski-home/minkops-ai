-- Shared attention state; native receipts and human decisions have separate audit entries.
CREATE TABLE attention_items (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL,
 task_id uuid NOT NULL, event_key text NOT NULL, identifier text NOT NULL,
 label text NOT NULL CHECK (length(label) BETWEEN 1 AND 80), kind text NOT NULL,
 target jsonb NOT NULL DEFAULT '{}', status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done')),
 authorized_by uuid REFERENCES users(id), done_by uuid REFERENCES users(id),
 done_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (tenant_id,event_key), UNIQUE (tenant_id,id),
 FOREIGN KEY (tenant_id,task_id) REFERENCES tasks(tenant_id,id)
);
CREATE INDEX attention_pending ON attention_items(tenant_id,updated_at DESC,id) WHERE status='pending';
CREATE TABLE attention_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, tenant_id uuid NOT NULL,
 item_id uuid NOT NULL, actor_id uuid REFERENCES users(id), action text NOT NULL,
 summary text NOT NULL CHECK (length(summary) <= 300), created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (tenant_id,item_id) REFERENCES attention_items(tenant_id,id)
);
ALTER TABLE desktop_jobs DROP CONSTRAINT desktop_jobs_operation_check;
ALTER TABLE desktop_jobs ADD CONSTRAINT desktop_jobs_operation_check CHECK
 (operation IN ('tally.probe','files.refresh','accounts.save','tally.save','sources.discover','tally.references','attention.refresh','attention.supplier'));
