"""Transport for a workspace's people: its members, their roles and workflows, and the invitations its admins send.

Only a workspace's admins reach these routes. The rules, such as one workspace per person and an admin always kept,
live in the platform (`members`).
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr, Field

from minkops_platform import members

from .auth import Db, User, dev_link, link, require_csrf, send_mail, tenant_access
from .service import call

router = APIRouter(prefix="/api/tenants/{slug}")


@router.get("/members")
def people(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection, edit=True)
    return members.members(connection, tenant)


class MemberChange(BaseModel):
    role: Literal["admin", "member"] | None = None
    workflow_ids: list[UUID] | None = Field(default=None, max_length=100)


@router.patch("/members/{user_id}")
def change(slug: str, user_id: UUID, body: MemberChange, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection, edit=True)
    return call(members.update, connection, tenant, user, user_id, role=body.role, workflow_ids=body.workflow_ids)


@router.delete("/members/{user_id}")
def remove(slug: str, user_id: UUID, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection, edit=True)
    return call(members.remove, connection, tenant, user, user_id)


@router.get("/invitations")
def invitations(slug: str, user: User, connection: Db):
    tenant, _ = tenant_access(slug, user, connection, edit=True)
    return members.invitations(connection, tenant)


class Invitation(BaseModel):
    email: EmailStr
    role: Literal["admin", "member"] = "member"


def deliver(tenant, actor, sent):
    """Email an invitation's link; on the local stack, which sends no email, the answer carries it."""
    invitation = sent["invitation"]
    url = link(f"/invite/{sent['token']}")
    role = "an admin" if invitation["role"] == "admin" else "a member"
    send_mail(invitation["email"], f"Join {tenant['name']} on Minkops", (
        f"{actor['name']} invited you to join {tenant['name']} on Minkops as {role}.\n\n"
        f"Open this link to create your account and join:\n{url}\n\n"
        f"The link works once, until {invitation['expires_at']:%d %B %Y}."))
    return {"message": f"Invitation sent to {invitation['email']}.", "invitation": invitation,
            **dev_link("invitation_link", url)}


@router.post("/invitations", status_code=201)
def invite(slug: str, body: Invitation, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection, edit=True)
    return deliver(tenant, user, call(members.invite, connection, tenant, user, str(body.email), body.role))


@router.post("/invitations/{invitation_id}/resend")
def resend(slug: str, invitation_id: UUID, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection, edit=True)
    return deliver(tenant, user, call(members.resend, connection, tenant, user, invitation_id))


@router.delete("/invitations/{invitation_id}")
def withdraw(slug: str, invitation_id: UUID, request: Request, user: User, connection: Db):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection, edit=True)
    call(members.withdraw, connection, tenant, user, invitation_id)
    return {"message": "Invitation withdrawn."}
