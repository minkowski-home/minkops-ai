"""Explicit local fixture: empty PR Infra and a populated mock tenant."""

import os
import secrets
from pathlib import Path

import psycopg
from jsonschema import ValidationError
from psycopg.types.json import Jsonb
from pwdlib import PasswordHash

from minkops_platform.installation import install, load_solution, register_employee
from minkops_platform.solution_policy import validate_option

ROOT = Path(__file__).resolve().parents[1]


def seed_demo(url: str, password: str | None = None) -> str:
    password = password or secrets.token_urlsafe(18)
    hash_value = PasswordHash.recommended().hash(password)
    with psycopg.connect(url) as connection:
        connection.execute(
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

        composition = load_solution(ROOT, "mock-client")
        employee_ids = {
            e.metadata["key"]: register_employee(connection, mock, e) for e in composition.employees
        }

        workflows = [
            (
                "account-reconciliation",
                "Account reconciliation",
                "Example workflow awaiting setup.",
                "paused",
                ["accounts-desk"],
                {
                    "type": "object",
                    "properties": {
                        "cadence": {
                            "type": "string",
                            "title": "Check cadence",
                            "enum": ["Daily", "Weekly"],
                        }
                    },
                    "additionalProperties": False,
                },
                {"cadence": "Daily"},
            ),
            (
                "vendor-intake",
                "Vendor intake",
                "Example planned workflow.",
                "planned",
                ["accounts-desk"],
                {"type": "object", "properties": {}, "additionalProperties": False},
                {},
            ),
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

        # Explicit demo composition retains mock-client's enabled tools without
        # discarding other preferences. The production installer still rejects
        # saved settings that a newly paused tool would invalidate.
        for key, name, fallback in (("source-discovery", "destination_mode", "tally"),):
            existing = connection.execute(
                "SELECT config_values FROM workflows WHERE tenant_id=%s AND key=%s FOR UPDATE",
                (mock, key),
            ).fetchone()
            if not existing or name not in existing[0]:
                continue
            try:
                validate_option(composition.workflows[key].tenant_schema, name, existing[0][name])
            except ValidationError:
                connection.execute(
                    """UPDATE workflows SET config_values=jsonb_set(config_values, %s, %s),
                    config_version=config_version+1 WHERE tenant_id=%s AND key=%s""",
                    ([name], Jsonb(fallback), mock, key),
                )
        install(connection, composition, actor_email="demo@example.com")

    return password


if __name__ == "__main__":
    local_password = seed_demo(os.environ["DATABASE_URL"], os.getenv("DEMO_PASSWORD"))
    print("Local mock account: demo@example.com")
    print(f"Local mock password: {local_password}")
