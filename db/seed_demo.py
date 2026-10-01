"""Explicit local fixture: empty PR Infra and a populated mock tenant."""

import json
import os
import secrets
from pathlib import Path

import psycopg
from minkops_platform.workflows import load_definition, register_workflow
from psycopg.types.json import Jsonb
from pwdlib import PasswordHash

ROOT = Path(__file__).resolve().parents[1]


def seed_demo(url: str, password: str | None = None) -> str:
    password = password or secrets.token_urlsafe(18)
    hash_value = PasswordHash.recommended().hash(password)
    with psycopg.connect(url) as connection:
        pr = connection.execute(
            """INSERT INTO tenants (slug, name) VALUES ('pr-infra', 'PR Infra')
               ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id"""
        ).fetchone()[0]
        mock = connection.execute(
            """INSERT INTO tenants (slug, name) VALUES ('mock-tenant', 'Mock tenant')
               ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id"""
        ).fetchone()[0]
        user = connection.execute(
            """INSERT INTO users (email, name, password_hash, email_verified_at, is_platform_admin)
               VALUES ('demo@example.com', 'Demo Operator', %s, now(), true)
               ON CONFLICT ((lower(email))) DO UPDATE
               SET password_hash = EXCLUDED.password_hash, is_platform_admin = true
               RETURNING id""",
            (hash_value,),
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO memberships (tenant_id, user_id, role)
               VALUES (%s, %s, 'admin') ON CONFLICT (tenant_id, user_id)
               DO UPDATE SET role = 'admin'""",
            (mock, user),
        )

        employees = [
            ("image-desk", "Image desk", "Receives images and prepares structured records.",
             {"type": "object", "properties": {
                 "review_mode": {"type": "string", "title": "Review mode",
                                 "enum": ["Only exceptions", "All outputs"]},
                 "notify_in_app": {"type": "boolean", "title": "In-app updates"}
             }, "additionalProperties": False},
             {"review_mode": "Only exceptions", "notify_in_app": True}),
            ("accounts-desk", "Accounts desk", "Keeps account records ready for review.",
             {"type": "object", "properties": {
                 "daily_digest": {"type": "boolean", "title": "Daily digest"}
             }, "additionalProperties": False},
             {"daily_digest": False}),
        ]
        employee_ids = {}
        for key, name, description, schema, values in employees:
            employee_ids[key] = connection.execute(
                """INSERT INTO employees (tenant_id, key, name, description, config_schema, config_values)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (tenant_id, key) DO UPDATE SET
                   name = EXCLUDED.name, description = EXCLUDED.description,
                   config_schema = EXCLUDED.config_schema
                   RETURNING id""",
                (mock, key, name, description, Jsonb(schema), Jsonb(values)),
            ).fetchone()[0]

        workflows = [
            ("image-to-excel-test", "Image to Excel", "Test image extraction and spreadsheet output.",
             "active", ["image-desk"],
             {"type": "object", "properties": {
                 "approval_required": {"type": "boolean", "title": "Ask before saving"},
                 "output_format": {"type": "string", "title": "Output format",
                                   "enum": ["Excel", "CSV"]}
             }, "additionalProperties": False},
             {"approval_required": True, "output_format": "Excel"}),
            ("account-reconciliation", "Account reconciliation", "Example workflow awaiting setup.",
             "paused", ["accounts-desk"],
             {"type": "object", "properties": {
                 "cadence": {"type": "string", "title": "Check cadence",
                             "enum": ["Daily", "Weekly"]}
             }, "additionalProperties": False},
             {"cadence": "Daily"}),
            ("vendor-intake", "Vendor intake", "Example planned workflow.",
             "planned", ["image-desk", "accounts-desk"],
             {"type": "object", "properties": {}, "additionalProperties": False}, {}),
        ]
        workflow_ids = {}
        for key, name, description, status, owners, schema, values in workflows:
            workflow_ids[key] = connection.execute(
                """INSERT INTO workflows
                   (tenant_id, key, name, description, status, config_schema, config_values)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (tenant_id, key) DO UPDATE SET
                   name = EXCLUDED.name, description = EXCLUDED.description,
                   config_schema = EXCLUDED.config_schema
                   RETURNING id""",
                (mock, key, name, description, status, Jsonb(schema), Jsonb(values)),
            ).fetchone()[0]
            for owner in owners:
                connection.execute(
                    """INSERT INTO workflow_employees (tenant_id, workflow_id, employee_id)
                       VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                    (mock, workflow_ids[key], employee_ids[owner]),
                )

        registrations = json.loads((ROOT / "db/fixtures/mock_workflows.json").read_text())
        for key, defaults in registrations.items():
            definition = load_definition(ROOT / "employees/accounts-desk/workflows" / key)
            workflow_ids[key] = register_workflow(connection, mock, definition, defaults)
            connection.execute("""UPDATE workflows SET status='active'
                WHERE tenant_id=%s AND id=%s AND status='planned'""", (mock,workflow_ids[key]))

        samples = [
            ("Extract the latest receipt", "running", 65,
             "Image received. Fields are being checked.",
             [("received", "Image received", 15), ("extracting", "Fields extracted", 65)]),
            ("Review a low-confidence field", "attention", 80,
             "The date needs a quick human check.",
             [("received", "Image received", 15), ("review", "Date needs review", 80)]),
            ("Hand off the approved sheet", "handoff", 90,
             "Waiting for the next owner.",
             [("prepared", "Sheet prepared", 80), ("handoff", "Ready to hand off", 90)]),
        ]
        for title, status, progress, summary, events in samples:
            row = connection.execute(
                "SELECT id FROM tasks WHERE tenant_id = %s AND title = %s",
                (mock, title),
            ).fetchone()
            if row:
                continue
            task_id = connection.execute(
                """INSERT INTO tasks (tenant_id, workflow_id, title, status, progress, summary)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (mock, workflow_ids["image-to-excel-test"], title, status, progress, summary),
            ).fetchone()[0]
            for event_type, event_summary, event_progress in events:
                connection.execute(
                    """INSERT INTO task_events (tenant_id, task_id, event_type, summary, progress)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (mock, task_id, event_type, event_summary, event_progress),
                )
    return password


if __name__ == "__main__":
    local_password = seed_demo(os.environ["DATABASE_URL"], os.getenv("DEMO_PASSWORD"))
    print("Local mock account: demo@example.com")
    print(f"Local mock password: {local_password}")
