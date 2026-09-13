"""Organization, membership, security policy and invitation management endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from visionroute.api.deps import (
    PlatformSession,
    TenantSession,
    VerifiedEmailContext,
    get_app_settings,
    get_optional_field_cipher,
    require_permission,
)
from visionroute.api.errors import NotFoundError
from visionroute.api.ratelimit import enforce_rate_limit
from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.errors import DomainConflictError, ValidationFailedError
from visionroute.application.identity.account_security import AccountSecurityService
from visionroute.application.identity.service import IdentityService
from visionroute.application.mail.service import MailService
from visionroute.config.settings import Settings
from visionroute.domain.permissions import ROLE_LABELS_TR, Permission, RoleKey
from visionroute.infrastructure.db.models.identity import (
    Invitation,
    Membership,
    Organization,
    OrganizationSettings,
    User,
)
from visionroute.infrastructure.db.models.mail import EmailMessage
from visionroute.infrastructure.security.crypto import FieldCipher

router = APIRouter(prefix="/organizations", tags=["organizations"])

AppSettings = Annotated[Settings, Depends(get_app_settings)]
OptionalCipher = Annotated[FieldCipher | None, Depends(get_optional_field_cipher)]


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


class OrganizationSecurity(BaseModel):
    mfa_required: bool


class MemberResponse(BaseModel):
    membership_id: str
    user_id: str
    email: str
    full_name: str
    role: str
    role_label: str
    status: str
    joined_at: datetime
    mfa_enabled: bool
    email_verified: bool


class MemberRoleUpdateRequest(BaseModel):
    role: RoleKey


class InvitationCreateRequest(BaseModel):
    email: EmailStr
    role: RoleKey


class InvitationResponse(BaseModel):
    id: str
    email: str
    role: str
    role_label: str
    status: str  # pending | accepted | revoked | expired
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    last_sent_at: datetime | None
    # Latest invitation e-mail delivery state: pending | sending | sent | dead_letter
    email_status: str | None


async def _load_org(
    db: TenantSession, organization_id: uuid.UUID
) -> tuple[Organization, OrganizationSettings]:
    organization = await db.get(Organization, organization_id)
    settings_row = await db.get(OrganizationSettings, organization_id)
    if organization is None or settings_row is None:
        raise NotFoundError("Organizasyon bulunamadı.")
    return organization, settings_row


def _org_out(
    organization: Organization, org_settings: OrganizationSettings
) -> OrganizationResponse:
    return OrganizationResponse(
        id=str(organization.id),
        name=organization.name,
        slug=organization.slug,
        status=organization.status,
        timezone=org_settings.timezone,
        currency=org_settings.currency,
    )


def _member_out(membership: Membership, user: User) -> MemberResponse:
    return MemberResponse(
        membership_id=str(membership.id),
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=membership.role_key,
        role_label=ROLE_LABELS_TR.get(RoleKey(membership.role_key), membership.role_key),
        status=membership.status,
        joined_at=membership.created_at,
        mfa_enabled=user.mfa_enabled_at is not None,
        email_verified=user.email_verified_at is not None,
    )


def _invitation_status(invitation: Invitation, now: datetime) -> str:
    if invitation.accepted_at is not None:
        return "accepted"
    if invitation.revoked_at is not None:
        return "revoked"
    if invitation.expires_at <= now:
        return "expired"
    return "pending"


def _invitation_out(invitation: Invitation, email_status: str | None) -> InvitationResponse:
    return InvitationResponse(
        id=str(invitation.id),
        email=invitation.email,
        role=invitation.role_key,
        role_label=ROLE_LABELS_TR.get(RoleKey(invitation.role_key), invitation.role_key),
        status=_invitation_status(invitation, datetime.now(UTC)),
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        revoked_at=invitation.revoked_at,
        last_sent_at=invitation.last_sent_at,
        email_status=email_status,
    )


def _identity(db: TenantSession, settings: Settings, cipher: FieldCipher | None) -> IdentityService:
    return IdentityService(
        db,
        settings.refresh_token_ttl_seconds,
        mail=MailService(db, cipher),
        invitation_ttl_days=settings.invitation_ttl_days,
    )


# ------------------------------------------------------------------ organization


@router.get("/current", response_model=OrganizationResponse)
async def get_current_organization(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_READ)],
) -> OrganizationResponse:
    return _org_out(*await _load_org(db, _tenant(ctx)))


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
    return _org_out(organization, org_settings)


@router.get("/current/security", response_model=OrganizationSecurity)
async def get_security_policy(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_READ)],
) -> OrganizationSecurity:
    _organization, org_settings = await _load_org(db, _tenant(ctx))
    return OrganizationSecurity(mfa_required=bool(org_settings.security.get("mfa_required", False)))


@router.patch("/current/security", response_model=OrganizationSecurity)
async def update_security_policy(
    body: OrganizationSecurity,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_UPDATE)],
) -> OrganizationSecurity:
    """İki adımlı doğrulamayı organizasyon genelinde zorunlu kılar."""
    _organization, org_settings = await _load_org(db, _tenant(ctx))
    if body.mfa_required and not ctx.mfa_enabled:
        raise DomainConflictError(
            "Bu politikayı etkinleştirmeden önce kendi hesabınızda iki adımlı doğrulamayı açın."
        )
    org_settings.security = {**org_settings.security, "mfa_required": body.mfa_required}
    await record_audit(
        db,
        ctx,
        action="organization.security_updated",
        resource_type="organization",
        resource_id=str(_tenant(ctx)),
        data={"mfa_required": body.mfa_required},
    )
    return body


# ------------------------------------------------------------------ members


@router.get("/current/members", response_model=list[MemberResponse])
async def list_members(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_MEMBERS_READ)],
) -> list[MemberResponse]:
    result = await db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == _tenant(ctx))
        .order_by(Membership.created_at)
    )
    return [_member_out(membership, user) for membership, user in result.all()]


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
        .where(Membership.id == membership_id, Membership.organization_id == _tenant(ctx))
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
    return _member_out(membership, user)


@router.delete("/current/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    membership_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_MEMBERS_MANAGE)],
) -> None:
    result = await db.execute(
        select(Membership).where(
            Membership.id == membership_id, Membership.organization_id == _tenant(ctx)
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


@router.delete("/current/members/{membership_id}/mfa", status_code=status.HTTP_204_NO_CONTENT)
async def reset_member_mfa(
    membership_id: uuid.UUID,
    db: PlatformSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_MEMBERS_MANAGE)],
    settings: AppSettings,
    cipher: OptionalCipher,
) -> None:
    """Cihazını kaybeden üyenin iki adımlı doğrulamasını sıfırlar (yalnızca sahip).

    Bilinçli olarak RLS-bypass oturumu kullanır: kullanıcının başka
    organizasyonlarda üyeliği olup olmadığı kontrolü kiracı dışını görmelidir.
    Tüm sorgular açıkça organizasyon kimliğiyle filtrelenir."""
    service = AccountSecurityService(db, settings, cipher, MailService(db, cipher))
    await service.admin_reset_mfa(ctx, membership_id=membership_id)


# ------------------------------------------------------------------ invitations


@router.post(
    "/current/invitations",
    status_code=status.HTTP_201_CREATED,
    response_model=InvitationResponse,
)
async def create_invitation(
    body: InvitationCreateRequest,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_INVITATIONS_MANAGE)],
    _verified: VerifiedEmailContext,
    settings: AppSettings,
    cipher: OptionalCipher,
) -> InvitationResponse:
    """Davet oluşturur ve e-postayla gönderir. Davet bağlantısı yalnızca davetlinin
    e-posta kutusuna iletilir; API yanıtında yer almaz."""
    invitation = await _identity(db, settings, cipher).create_invitation(
        ctx, email=body.email, role_key=body.role
    )
    return _invitation_out(invitation, "pending")


@router.get("/current/invitations", response_model=list[InvitationResponse])
async def list_invitations(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_INVITATIONS_MANAGE)],
) -> list[InvitationResponse]:
    invitations = list(
        (
            await db.execute(
                select(Invitation)
                .where(Invitation.organization_id == _tenant(ctx))
                .order_by(Invitation.created_at.desc())
                .limit(200)
            )
        ).scalars()
    )
    email_status: dict[str, str] = {}
    if invitations:
        messages = await db.execute(
            select(EmailMessage.related_id, EmailMessage.status)
            .where(
                EmailMessage.organization_id == _tenant(ctx),
                EmailMessage.related_type == "invitation",
                EmailMessage.related_id.in_([str(i.id) for i in invitations]),
            )
            .order_by(EmailMessage.created_at)
        )
        for related_id, message_status in messages.all():
            if related_id is not None:
                email_status[related_id] = message_status  # latest wins
    return [_invitation_out(i, email_status.get(str(i.id))) for i in invitations]


@router.post("/current/invitations/{invitation_id}/resend", response_model=InvitationResponse)
async def resend_invitation(
    invitation_id: uuid.UUID,
    request: Request,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_INVITATIONS_MANAGE)],
    _verified: VerifiedEmailContext,
    settings: AppSettings,
    cipher: OptionalCipher,
) -> InvitationResponse:
    """Yeni bağlantıyla yeniden gönderir; önceki bağlantı geçersiz olur."""
    await enforce_rate_limit(
        request,
        scope="invitation-resend",
        identity=str(invitation_id),
        limit=settings.account_email_rate_limit_per_hour,
        window_seconds=3600,
    )
    invitation = await _identity(db, settings, cipher).resend_invitation(ctx, invitation_id)
    return _invitation_out(invitation, "pending")


@router.delete("/current/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_INVITATIONS_MANAGE)],
    settings: AppSettings,
    cipher: OptionalCipher,
) -> None:
    await _identity(db, settings, cipher).revoke_invitation(ctx, invitation_id)
