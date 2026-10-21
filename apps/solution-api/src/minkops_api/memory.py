"""HTTP binding for an employee's memory of one client business.

Every member who can reach the client reads it; only workspace admins change
it. The platform service owns scope, versions and the audit trail.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from minkops_platform.accounts import memory

from .accounts import _call
from .auth import Db, User, require_csrf, tenant_access

router = APIRouter(prefix="/api/tenants/{slug}/clients/{client}/memory")
EMPLOYEE = Query(default="accounts-desk", pattern="^[a-z][a-z0-9-]{0,40}$")


class EntryStatus(BaseModel):
    status: Literal["disabled", "confirmed", "retired"]


class Rule(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    workflow_key: str | None = Field(default=None, pattern="^[a-z][a-z0-9-]*$")
    company_id: UUID | None = None


class RuleStatus(BaseModel):
    status: Literal["active", "disabled"]


def _rule(row):
    return {"id": str(row["id"]), "version": row["version"], "text": row["text"], "status": row["status"],
            "workflow": row["workflow_key"], "company_id": str(row["company_id"]) if row["company_id"] else None}


@router.get("")
def page(slug: str, client: str, user: User, connection: Db, employee: str = EMPLOYEE):
    tenant, member = tenant_access(slug, user, connection)
    return _call(memory.page, connection, tenant, user, member, client, employee)


@router.patch("/entries/{entry_id}")
def set_entry(slug: str, client: str, entry_id: UUID, body: EntryStatus, request: Request, user: User,
              connection: Db, employee: str = EMPLOYEE):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return _call(memory.set_entry, connection, tenant, user, member, client, entry_id, body.status, employee)


@router.post("/rules")
def create_rule(slug: str, client: str, body: Rule, request: Request, user: User, connection: Db,
                employee: str = EMPLOYEE):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return _rule(_call(memory.write_instruction, connection, tenant, user, member, client, text=body.text,
                       workflow_key=body.workflow_key, company_id=body.company_id, employee=employee))


@router.put("/rules/{rule_id}")
def edit_rule(slug: str, client: str, rule_id: UUID, body: Rule, request: Request, user: User, connection: Db,
              employee: str = EMPLOYEE):
    """A new version of the rule; proposals that cited an earlier version keep its text."""
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return _rule(_call(memory.write_instruction, connection, tenant, user, member, client, text=body.text,
                       workflow_key=body.workflow_key, company_id=body.company_id, instruction_id=rule_id,
                       employee=employee))


@router.patch("/rules/{rule_id}")
def set_rule(slug: str, client: str, rule_id: UUID, body: RuleStatus, request: Request, user: User, connection: Db,
             employee: str = EMPLOYEE):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return _call(memory.set_instruction, connection, tenant, user, member, client, rule_id, status=body.status,
                 employee=employee)


@router.delete("/rules/{rule_id}")
def delete_rule(slug: str, client: str, rule_id: UUID, request: Request, user: User, connection: Db,
                employee: str = EMPLOYEE):
    require_csrf(request)
    tenant, member = tenant_access(slug, user, connection)
    return _call(memory.delete_instruction, connection, tenant, user, member, client, rule_id, employee)
