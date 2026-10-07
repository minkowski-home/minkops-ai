"""Tenant-scoped catalog, settings, and observable task reads."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from jsonschema import Draft202012Validator
from minkops_platform.runtime.launch import installed_definition
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from minkops_api.auth import Db, User, require_csrf, tenant_access

router = APIRouter(prefix="/api/tenants/{slug}")


def employees_for(connection, tenant_id):
    return connection.execute(
        """SELECT id, key, name, description, status, config_schema,
                  config_values, config_version
           FROM employees WHERE tenant_id = %s ORDER BY name""",
        (tenant_id,),
    ).fetchall()


def workflows_for(connection, tenant_id):
    workflows = connection.execute(
        """SELECT id, key, name, description, status, config_schema,
                  config_values, config_version, execution_binding
           FROM workflows WHERE tenant_id = %s ORDER BY name""",
        (tenant_id,),
    ).fetchall()
    owners = connection.execute(
        "SELECT workflow_id, employee_id FROM workflow_employees WHERE tenant_id = %s",
        (tenant_id,),
    ).fetchall()
    by_workflow: dict[Any, list[str]] = {}
    for owner in owners:
        by_workflow.setdefault(owner["workflow_id"], []).append(str(owner["employee_id"]))
    for workflow in workflows:
        workflow["employee_ids"] = by_workflow.get(workflow["id"], [])
        binding = workflow.pop("execution_binding")
        workflow["presentation"] = binding.get("presentation") if binding else None
        workflow["run_schema"] = None
        workflow["run_defaults"] = None
        if binding:
            definition = installed_definition(binding, workflow["key"])
            workflow["run_schema"] = definition.run_schema
            workflow["run_defaults"] = definition.metadata["run_defaults"]
    return workflows


def tasks_for(connection, tenant_id):
    return connection.execute(
        """SELECT id, workflow_id, title, status, progress, summary, created_at, updated_at
           FROM tasks WHERE tenant_id = %s ORDER BY updated_at DESC""",
        (tenant_id,),
    ).fetchall()


@router.get("/workspace")
def workspace(slug: str, user: User, connection: Db):
    tenant, member = tenant_access(slug, user, connection)
    return {
        "tenant": {"slug": tenant["slug"], "name": tenant["name"]},
        "can_edit": user["is_platform_admin"] or (member and member["role"] == "admin"),
        "employees": employees_for(connection, tenant["id"]),
        "workflows": workflows_for(connection, tenant["id"]),
        "tasks": tasks_for(connection, tenant["id"]),
    }


@router.get("/employees")
def employees(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return employees_for(connection, tenant["id"])


@router.get("/employees/{employee_id}")
def employee_detail(slug: str, employee_id: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    row = connection.execute(
        """SELECT id, key, name, description, status, config_schema,
                  config_values, config_version FROM employees
           WHERE tenant_id = %s AND id = %s""",
        (tenant["id"], employee_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Employee not found.")
    row["workflows"] = [
        workflow
        for workflow in workflows_for(connection, tenant["id"])
        if str(row["id"]) in workflow["employee_ids"]
    ]
    return row


@router.get("/workflows")
def workflows(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return workflows_for(connection, tenant["id"])


@router.get("/workflows/{workflow_id}")
def workflow_detail(slug: str, workflow_id: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    row = next(
        (
            item
            for item in workflows_for(connection, tenant["id"])
            if str(item["id"]) == workflow_id
        ),
        None,
    )
    if not row:
        raise HTTPException(404, "Workflow not found.")
    return row


class SettingsUpdate(BaseModel):
    config_values: dict[str, Any] | None = None
    status: str | None = None


def update_settings(
    kind: str,
    slug: str,
    item_id: str,
    body: SettingsUpdate,
    request: Request,
    user: dict,
    connection,
):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection, edit=True)
    row = connection.execute(
        f"""SELECT id, status, config_schema, config_values, config_version
            FROM {kind} WHERE tenant_id = %s AND id = %s FOR UPDATE""",
        (tenant["id"], item_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, f"{kind[:-1].capitalize()} not found.")
    if body.config_values is None and body.status is None:
        raise HTTPException(422, "No changes provided.")
    values = body.config_values if body.config_values is not None else row["config_values"]
    errors = list(Draft202012Validator(row["config_schema"]).iter_errors(values))
    if errors:
        raise HTTPException(422, errors[0].message)
    allowed = {"employees": {"active", "inactive"}, "workflows": {"active", "paused", "planned"}}[
        kind
    ]
    status = body.status if body.status is not None else row["status"]
    if status not in allowed:
        raise HTTPException(422, "Invalid status.")
    updated = connection.execute(
        f"""UPDATE {kind} SET status = %s, config_values = %s
            WHERE tenant_id = %s AND id = %s
            RETURNING id, key, name, description, status, config_schema,
                      config_values, config_version""",
        (status, Jsonb(values), tenant["id"], item_id),
    ).fetchone()
    connection.execute(
        """INSERT INTO event_outbox (tenant_id, event_type, aggregate_id, payload)
           VALUES (%s, %s, %s, %s)""",
        (
            tenant["id"],
            f"{kind[:-1]}.settings_updated",
            row["id"],
            Jsonb(
                {
                    "actor_id": str(user["id"]),
                    "status": status,
                    "config_values": values,
                    "config_version": row["config_version"],
                }
            ),
        ),
    )
    return updated


@router.patch("/employees/{employee_id}")
def update_employee(
    slug: str, employee_id: str, body: SettingsUpdate, request: Request, user: User, connection: Db
):
    return update_settings("employees", slug, employee_id, body, request, user, connection)


@router.patch("/workflows/{workflow_id}")
def update_workflow(
    slug: str, workflow_id: str, body: SettingsUpdate, request: Request, user: User, connection: Db
):
    return update_settings("workflows", slug, workflow_id, body, request, user, connection)


@router.get("/tasks/{task_id}")
def task_detail(slug: str, task_id: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    task = connection.execute(
        """SELECT id, workflow_id, title, status, progress, summary, created_at, updated_at
           FROM tasks WHERE tenant_id = %s AND id = %s""",
        (tenant["id"], task_id),
    ).fetchone()
    if not task:
        raise HTTPException(404, "Task not found.")
    task["events"] = connection.execute(
        """SELECT id, event_type, summary, progress, created_at
           FROM task_events WHERE tenant_id = %s AND task_id = %s ORDER BY id""",
        (tenant["id"], task_id),
    ).fetchall()
    return task
