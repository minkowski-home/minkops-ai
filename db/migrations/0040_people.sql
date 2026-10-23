-- People and their workspaces (docs/workspace-access.md). A person belongs to
-- one workspace and joins it only through an invitation: we invite each
-- workspace's first admin, and its admins invite everyone else. An admin runs
-- every workflow; a member runs the workflows an admin assigns them.
-- Workflow execution never reads any of this: it only decides what people see
-- and do.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM memberships GROUP BY user_id HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'A person belongs to several workspaces. Keep one membership each before upgrading.';
    END IF;
END $$;
ALTER TABLE memberships ADD CONSTRAINT memberships_one_workspace UNIQUE (user_id);

-- One open invitation per workspace and address; a resend replaces its link.
DELETE FROM invitations i USING invitations newer
WHERE i.accepted_at IS NULL AND newer.accepted_at IS NULL AND i.tenant_id = newer.tenant_id
  AND lower(i.email) = lower(newer.email) AND (i.created_at, i.id) < (newer.created_at, newer.id);
CREATE UNIQUE INDEX invitations_open ON invitations (tenant_id, lower(email)) WHERE accepted_at IS NULL;

-- A password reset a person asks for by email: its link works once, within the hour.
CREATE TABLE password_resets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX password_resets_user ON password_resets (user_id, created_at DESC);

-- The sessions a person sees and ends: the browser that opened each, and when it was last used.
ALTER TABLE sessions ADD COLUMN user_agent text CHECK (char_length(user_agent) <= 300),
    ADD COLUMN last_seen_at timestamptz;
CREATE INDEX sessions_user ON sessions (user_id) WHERE revoked_at IS NULL;

-- The workflows a member runs. Removing the member or the workflow removes the assignment.
CREATE TABLE workflow_assignments (
    tenant_id uuid NOT NULL,
    workflow_id uuid NOT NULL,
    user_id uuid NOT NULL,
    assigned_by uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, workflow_id, user_id),
    FOREIGN KEY (tenant_id, workflow_id) REFERENCES workflows(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, user_id) REFERENCES memberships(tenant_id, user_id) ON DELETE CASCADE
);
CREATE INDEX workflow_assignments_member ON workflow_assignments (tenant_id, user_id);
-- Members keep every workflow they could run before assignments existed.
INSERT INTO workflow_assignments (tenant_id, workflow_id, user_id)
SELECT m.tenant_id, w.id, m.user_id FROM memberships m JOIN workflows w ON w.tenant_id = m.tenant_id
WHERE m.role = 'member';

-- An open practice question names the workflow its answer changes, so it reaches the members who run it
-- (accounts/practice.py QUESTIONS). Admins see every question.
UPDATE attention_items a
SET target = a.target || jsonb_build_object('workflows', CASE q.probe WHEN 'bank_payments'
    THEN '["statement-entry"]'::jsonb ELSE '["bill-entry"]'::jsonb END)
FROM practice_questions q
WHERE a.kind = 'practice' AND a.target->>'question_id' = q.id::text;
