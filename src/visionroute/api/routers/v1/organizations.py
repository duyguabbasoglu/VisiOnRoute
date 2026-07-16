"""Organization, membership, and invitation management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from visionroute.api.deps import (
    TenantSession,
    get_app_settings,
    require_permission,
)
from visionroute.api.errors import NotFoundError
from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.errors import DomainConflictError, ValidationFailedError
from visionroute.application.identity.service import IdentityService
from visionroute.config.settings import Settings
from visionroute.domain.permissions import ROLE_LABELS_TR, Permission, RoleKey
from visionroute.infrastructure.db.models.identity import (
    Invitation,
    Membership,
    Organization,
    OrganizationSettings,
    User,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _tenant(ctx: RequestContext) -> uuid.UUID:
    # TenantSession guarantees a tenant, but narrow it explicitly for safety
    # even under `python -O` (where asserts are stripped).
    if ctx.organization_id is None:  # pragma: no cover - defensive
        raise NotFoundError("Organizasyon bağlamı bulunamadı.")
    return ctx.organization_id


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    timezone: str
    currency: str


class OrganizationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    timezone: str | None = Field(default=None, max_length=60)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class MemberResponse(BaseModel):
    membership_id: str
    user_id: str
    email: str
    full_name: str
    role: str
    role_label: str
    status: str
    joined_at: datetime


class MemberRoleUpdateRequest(BaseModel):
    role: RoleKey


class InvitationCreateRequest(BaseModel):
    email: EmailStr
    role: RoleKey


class InvitationResponse(BaseModel):
    id: str
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    # Returned only at creation time so the admin can share it if e-mail
    # delivery is unavailable; never retrievable afterwards.
    invitation_token: str | None = None


async def _load_org(
    db: TenantSession, organization_id: uuid.UUID
) -> tuple[Organization, OrganizationSettings]:
    organization = await db.get(Organization, organization_id)
    settings_row = await db.get(OrganizationSettings, organization_id)
    if organization is None or settings_row is None:
        raise NotFoundError("Organizasyon bulunamadı.")
    return organization, settings_row


@router.get("/current", response_model=OrganizationResponse)
async def get_current_organization(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_READ)],
) -> OrganizationResponse:
    organization, org_settings = await _load_org(db, _tenant(ctx))
    return OrganizationResponse(
        id=str(organization.id),
        name=organization.name,
        slug=organization.slug,
        status=organization.status,
        timezone=org_settings.timezone,
        currency=org_settings.currency,
    )


@router.patch("/current", response_model=OrganizationResponse)
async def update_current_organization(
    body: OrganizationUpdateRequest,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_UPDATE)],
) -> OrganizationResponse:
    organization, org_settings = await _load_org(db, _tenant(ctx))
    changes: dict[str, str] = {}
    if body.name is not None:
        organization.name = body.name
        changes["name"] = body.name
    if body.timezone is not None:
        org_settings.timezone = body.timezone
        changes["timezone"] = body.timezone
    if body.currency is not None:
        org_settings.currency = body.currency.upper()
        changes["currency"] = org_settings.currency
    if changes:
        await record_audit(
            db,
            ctx,
            action="organization.updated",
            resource_type="organization",
            resource_id=str(organization.id),
            data=changes,
        )
    return OrganizationResponse(
        id=str(organization.id),
        name=organization.name,
        slug=organization.slug,
        status=organization.status,
        timezone=org_settings.timezone,
        currency=org_settings.currency,
    )


@router.get("/current/members", response_model=list[MemberResponse])
async def list_members(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_MEMBERS_READ)],
) -> list[MemberResponse]:
    result = await db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.organization_id)
        .order_by(Membership.created_at)
    )
    return [
        MemberResponse(
            membership_id=str(membership.id),
            user_id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=membership.role_key,
            role_label=ROLE_LABELS_TR.get(RoleKey(membership.role_key), membership.role_key),
            status=membership.status,
            joined_at=membership.created_at,
        )
        for membership, user in result.all()
    ]


@router.patch("/current/members/{membership_id}", response_model=MemberResponse)
async def update_member_role(
    membership_id: uuid.UUID,
    body: MemberRoleUpdateRequest,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_MEMBERS_MANAGE)],
) -> MemberResponse:
    result = await db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.id == membership_id,
            Membership.organization_id == ctx.organization_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise NotFoundError("Üyelik bulunamadı.")
    membership, user = row

    if membership.role_key == RoleKey.OWNER.value and body.role != RoleKey.OWNER:
        raise DomainConflictError("Organizasyon sahibinin rolü bu ekrandan değiştirilemez.")
    if body.role == RoleKey.OWNER:
        raise ValidationFailedError(["Sahiplik bu uç noktadan atanamaz."])

    membership.role_key = body.role.value
    await record_audit(
        db,
        ctx,
        action="membership.role_changed",
        resource_type="membership",
        resource_id=str(membership.id),
        data={"new_role": body.role.value, "user_id": str(user.id)},
    )
    return MemberResponse(
        membership_id=str(membership.id),
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=membership.role_key,
        role_label=ROLE_LABELS_TR[body.role],
        status=membership.status,
        joined_at=membership.created_at,
    )


@router.delete("/current/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    membership_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_MEMBERS_MANAGE)],
) -> None:
    result = await db.execute(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.organization_id == ctx.organization_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Üyelik bulunamadı.")
    if membership.role_key == RoleKey.OWNER.value:
        raise DomainConflictError("Organizasyon sahibi üyelikten çıkarılamaz.")
    if membership.user_id == ctx.user_id:
        raise DomainConflictError("Kendi üyeliğinizi kaldıramazsınız.")
    await db.delete(membership)
    await record_audit(
        db,
        ctx,
        action="membership.removed",
        resource_type="membership",
        resource_id=str(membership.id),
        data={"user_id": str(membership.user_id)},
    )


@router.post(
    "/current/invitations",
    status_code=status.HTTP_201_CREATED,
    response_model=InvitationResponse,
)
async def create_invitation(
    body: InvitationCreateRequest,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_INVITATIONS_MANAGE)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> InvitationResponse:
    service = IdentityService(db, settings.refresh_token_ttl_seconds)
    invitation, token = await service.create_invitation(ctx, email=body.email, role_key=body.role)
    return InvitationResponse(
        id=str(invitation.id),
        email=invitation.email,
        role=invitation.role_key,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        invitation_token=token,
    )


@router.get("/current/invitations", response_model=list[InvitationResponse])
async def list_invitations(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_INVITATIONS_MANAGE)],
) -> list[InvitationResponse]:
    result = await db.execute(
        select(Invitation)
        .where(Invitation.organization_id == ctx.organization_id)
        .order_by(Invitation.created_at.desc())
        .limit(200)
    )
    return [
        InvitationResponse(
            id=str(invitation.id),
            email=invitation.email,
            role=invitation.role_key,
            expires_at=invitation.expires_at,
            accepted_at=invitation.accepted_at,
        )
        for invitation in result.scalars()
    ]
