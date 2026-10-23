"""Tenant-scoped catalog, settings, and observable task reads."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

from minkops_api.auth import Db, User, require_csrf, tenant_access
from minkops_platform import attention, clients, members
from minkops_platform.installation import installed_definition
from minkops_platform.run_controls import owns_task, task_control

from .desktop import call

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
            try:
                definition = installed_definition(binding, workflow["key"])
            except (ValueError, OSError):
                # Installed from a definition this version no longer ships: listed, but not runnable.
                continue
            workflow["run_schema"] = definition.run_schema
            workflow["run_defaults"] = definition.metadata["run_defaults"]
    return workflows


def tasks_for(connection, tenant_id, visible=None, runs=None):
    """Recent tasks; `visible` limits client work to the clients a member can reach, and `runs` to the workflows they
    run. A task of no workflow, such as a PC's refresh, reaches everyone."""
    return connection.execute(
        """SELECT id, workflow_id, client_id, title,
                  CASE WHEN control_state='active' THEN status ELSE control_state END AS status,
                  control_state, progress, summary, created_at, updated_at,
                  (SELECT e.event_type FROM task_events e WHERE e.tenant_id=tasks.tenant_id AND e.task_id=tasks.id
                   AND e.event_type IN ('queued','executing','review','writing','completed') ORDER BY e.id DESC LIMIT 1) AS stage
           FROM tasks WHERE tenant_id = %s AND (client_id IS NULL OR %s::uuid[] IS NULL OR client_id = ANY(%s::uuid[]))
               AND (workflow_id IS NULL OR %s::uuid[] IS NULL OR workflow_id = ANY(%s::uuid[]))
           ORDER BY updated_at DESC LIMIT 100""",
        (tenant_id, *(2 * [None if visible is None else list(visible)]), *(2 * [None if runs is None else list(runs)])),
    ).fetchall()


def runnable(connection, tenant, user, member):
    """The tenant's workflows this person runs: every one for an admin, the assigned ones for a member."""
    runs = members.assigned(connection, tenant, user, member)
    return runs, [w for w in workflows_for(connection, tenant["id"]) if runs is None or w["id"] in runs]


@router.get("/workspace")
def workspace(slug: str, user: User, connection: Db):
    tenant, member = tenant_access(slug, user, connection)
    visible = clients.visible_ids(connection, tenant, user, member)
    runs, flows = runnable(connection, tenant, user, member)
    return {
        "tenant": {"slug": tenant["slug"], "name": tenant["name"]},
        "can_edit": user["is_platform_admin"] or (member and member["role"] == "admin"),
        "clients": clients.listing(connection, tenant, user, member),
        "employees": employees_for(connection, tenant["id"]),
        "workflows": flows,
        "tasks": tasks_for(connection, tenant["id"], visible, runs),
        "attention_count": attention.pending_count(connection, tenant["id"], visible,
                                                   None if runs is None else runs.values()),
    }


@router.get("/employees")
def employees(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection)
    return employees_for(connection, tenant["id"])


@router.get("/employees/{employee_id}")
def employee_detail(slug: str, employee_id: str, user: User, connection: Db):
    tenant, member = tenant_access(slug, user, connection)
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
        for workflow in runnable(connection, tenant, user, member)[1]
        if str(row["id"]) in workflow["employee_ids"]
    ]
    return row


@router.get("/workflows")
def workflows(slug: str, user: User, connection: Db):
    tenant, member = tenant_access(slug, user, connection)
    return runnable(connection, tenant, user, member)[1]


@router.get("/workflows/{workflow_id}")
def workflow_detail(slug: str, workflow_id: str, user: User, connection: Db):
    tenant, member = tenant_access(slug, user, connection)
    row = next(
        (
            item
            for item in runnable(connection, tenant, user, member)[1]
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


def reachable_task(connection, tenant, user, member, task_id):
    """The task, or 404 when it is not this tenant's, or belongs to a client or workflow the person does not reach."""
    visible = clients.visible_ids(connection, tenant, user, member)
    runs = members.assigned(connection, tenant, user, member)
    task = connection.execute(
        """SELECT id, workflow_id, title, CASE WHEN control_state='active' THEN status ELSE control_state END AS status,
                  control_state, progress, summary, created_at, updated_at,
                  (SELECT e.event_type FROM task_events e WHERE e.tenant_id=tasks.tenant_id AND e.task_id=tasks.id
                   AND e.event_type IN ('queued','executing','review','writing','completed') ORDER BY e.id DESC LIMIT 1) AS stage
           FROM tasks WHERE tenant_id = %s AND id = %s
               AND (client_id IS NULL OR %s::uuid[] IS NULL OR client_id = ANY(%s::uuid[]))
               AND (workflow_id IS NULL OR %s::uuid[] IS NULL OR workflow_id = ANY(%s::uuid[]))""",
        (tenant["id"], task_id, *(2 * [None if visible is None else list(visible)]),
         *(2 * [None if runs is None else list(runs)])),
    ).fetchone()
    if not task:
        raise HTTPException(404, "Task not found.")
    return task


@router.get("/tasks/{task_id}")
def task_detail(slug: str, task_id: UUID, user: User, connection: Db):
    tenant, member = tenant_access(slug, user, connection)
    task = reachable_task(connection, tenant, user, member, task_id)
    task["can_control"] = owns_task(connection, tenant["id"], task_id, user["id"])
    # A run's task opens its review: the run, and the client whose routes serve it.
    run = connection.execute(
        """SELECT r.id, c.slug FROM runs r JOIN client_businesses c ON c.tenant_id=r.tenant_id AND c.id=r.client_id
           WHERE r.tenant_id=%s AND r.task_id=%s ORDER BY r.created_at LIMIT 1""", (tenant["id"], task_id)).fetchone()
    if run:
        task["run"] = {"id": str(run["id"]), "client": run["slug"]}
    task["events"] = connection.execute(
        """SELECT id, event_type, summary, progress, created_at
           FROM task_events WHERE tenant_id = %s AND task_id = %s ORDER BY id""",
        (tenant["id"], task_id),
    ).fetchall()
    return task


class TaskControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["pause", "resume", "stop"]


@router.post("/tasks/{task_id}/control")
def control_task(slug: str, task_id: UUID, body: TaskControl, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    reachable_task(connection, tenant, user, member, task_id)
    call(task_control, connection, tenant["id"], user, task_id, body.action)
    return task_detail(slug, task_id, user, connection)
