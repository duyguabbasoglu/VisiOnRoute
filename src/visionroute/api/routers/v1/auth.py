"""Authentication, account recovery, e-mail verification and two-factor
authentication endpoints (Türkçe müşteri mesajları).

One-time tokens (invitation, reset, verification) are accepted only in
request bodies, never in URL paths or query strings, so they cannot end up in
access logs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.api.deps import (
    AnonymousContext,
    CurrentContext,
    PlatformSession,
    get_app_settings,
    get_jwt_service,
    get_optional_field_cipher,
)
from visionroute.api.errors import UnauthorizedError
from visionroute.api.ratelimit import client_identity, enforce_rate_limit
from visionroute.application.context import RequestContext
from visionroute.application.identity.account_security import AccountSecurityService
from visionroute.application.identity.service import AuthenticatedUser, IdentityService
from visionroute.application.mail.service import MailService
from visionroute.config.settings import Settings
from visionroute.domain.permissions import ROLE_LABELS_TR, RoleKey
from visionroute.infrastructure.db.models.identity import (
    Membership,
    Organization,
    OrganizationSettings,
    User,
)
from visionroute.infrastructure.security.crypto import FieldCipher
from visionroute.infrastructure.security.tokens import JwtService

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "vr_refresh"
_REFRESH_COOKIE_PATH = "/api/v1/auth"

AppSettings = Annotated[Settings, Depends(get_app_settings)]
OptionalCipher = Annotated[FieldCipher | None, Depends(get_optional_field_cipher)]
Jwt = Annotated[JwtService, Depends(get_jwt_service)]


# ------------------------------------------------------------------ schemas


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)


class AcceptInvitationRequest(TokenRequest):
    full_name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=200)


class InvitationPreviewResponse(BaseModel):
    organization_name: str
    email: str
    role: str
    role_label: str
    expires_at: datetime
    account_exists: bool


class SessionUser(BaseModel):
    id: str
    email: str
    full_name: str
    organization_id: str | None
    organization_name: str | None
    role: str | None
    role_label: str | None
    is_platform_admin: bool
    email_verified: bool
    mfa_enabled: bool
    mfa_required: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 — OAuth2 token type label, not a secret
    expires_in: int
    user: SessionUser


class MfaChallengeResponse(BaseModel):
    mfa_required: Literal[True] = True
    mfa_token: str
    expires_in: int
    message: str = "İki adımlı doğrulama kodunuzu girin."


class MessageResponse(BaseModel):
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(TokenRequest):
    password: str = Field(min_length=1, max_length=200)


class PasswordConfirmation(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class MfaVerifyRequest(BaseModel):
    mfa_token: str = Field(min_length=16, max_length=128)
    code: str | None = Field(default=None, min_length=6, max_length=32)
    recovery_code: str | None = Field(default=None, min_length=8, max_length=32)


class MfaSensitiveRequest(PasswordConfirmation):
    code: str = Field(min_length=6, max_length=32)


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]
    message: str = (
        "Kurtarma kodlarınızı güvenli bir yerde saklayın. Her kod yalnızca bir kez "
        "kullanılabilir ve bu kodlar tekrar gösterilmez."
    )


# ------------------------------------------------------------------ helpers


def _identity(db: AsyncSession, settings: Settings, cipher: FieldCipher | None) -> IdentityService:
    return IdentityService(
        db,
        settings.refresh_token_ttl_seconds,
        mail=MailService(db, cipher),
        invitation_ttl_days=settings.invitation_ttl_days,
    )


def _account(
    db: AsyncSession, settings: Settings, cipher: FieldCipher | None
) -> AccountSecurityService:
    return AccountSecurityService(db, settings, cipher, MailService(db, cipher))


def _user_id(ctx: RequestContext) -> uuid.UUID:
    if ctx.user_id is None:  # pragma: no cover - access tokens always carry a subject
        raise UnauthorizedError
    return ctx.user_id


async def _session_user(db: AsyncSession, user: User, membership: Membership | None) -> SessionUser:
    organization_name: str | None = None
    mfa_required = False
    if membership is not None:
        organization = await db.get(Organization, membership.organization_id)
        org_settings = await db.get(OrganizationSettings, membership.organization_id)
        organization_name = organization.name if organization else None
        security = org_settings.security if org_settings else {}
        mfa_required = bool(security.get("mfa_required", False))
    role = membership.role_key if membership else None
    return SessionUser(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        organization_id=str(membership.organization_id) if membership else None,
        organization_name=organization_name,
        role=role,
        role_label=ROLE_LABELS_TR.get(RoleKey(role)) if role else None,
        is_platform_admin=user.platform_role == "super_admin",
        email_verified=user.email_verified_at is not None,
        mfa_enabled=user.mfa_enabled_at is not None,
        mfa_required=mfa_required,
    )


async def _issue(
    response: Response,
    db: AsyncSession,
    settings: Settings,
    jwt_service: JwtService,
    auth: AuthenticatedUser,
) -> AuthResponse:
    membership = auth.membership
    access_token = jwt_service.issue_access_token(
        user_id=auth.user.id,
        organization_id=membership.organization_id if membership else None,
        role=membership.role_key if membership else None,
        is_platform_admin=auth.user.platform_role == "super_admin",
    )
    response.set_cookie(
        _REFRESH_COOKIE,
        auth.refresh_token_cleartext,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=_REFRESH_COOKIE_PATH,
        domain=settings.cookie_domain,
    )
    return AuthResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_seconds,
        user=await _session_user(db, auth.user, membership),
    )


async def _limit_ip(request: Request, scope: str, limit: int, window_seconds: int) -> None:
    await enforce_rate_limit(
        request,
        scope=scope,
        identity=client_identity(request),
        limit=limit,
        window_seconds=window_seconds,
    )


# ------------------------------------------------------------------ registration & login


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=AuthResponse)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: AppSettings,
    cipher: OptionalCipher,
    jwt_service: Jwt,
) -> AuthResponse:
    """Yeni organizasyon kaydı: organizasyonu ve sahibini birlikte oluşturur."""
    await _limit_ip(request, "register:ip", settings.register_rate_limit_per_hour, 3600)
    identity = _identity(db, settings, cipher)
    _organization, user, membership = await identity.register_organization(
        ctx,
        organization_name=body.organization_name,
        slug=body.slug,
        owner_email=body.email,
        owner_full_name=body.full_name,
        owner_password=body.password,
    )
    await _account(db, settings, cipher).send_email_verification(ctx, user)
    auth = await identity.start_session(ctx, user, membership)
    return await _issue(response, db, settings, jwt_service, auth)


@router.post("/login", response_model=AuthResponse | MfaChallengeResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: AppSettings,
    cipher: OptionalCipher,
    jwt_service: Jwt,
) -> AuthResponse | MfaChallengeResponse:
    """Parola doğrulaması. İki adımlı doğrulama etkinse oturum yerine kısa ömürlü
    bir doğrulama belirteci döner; oturum `/auth/mfa/verify` ile açılır."""
    await _limit_ip(request, "login:ip", settings.login_ip_rate_limit_per_minute, 60)
    await enforce_rate_limit(
        request,
        scope="login:ip-email",
        identity=f"{client_identity(request)}|{body.email}",
        limit=settings.login_rate_limit_per_minute,
        window_seconds=60,
    )
    identity = _identity(db, settings, cipher)
    user, membership = await identity.authenticate(ctx, email=body.email, password=body.password)
    if user.mfa_enabled_at is not None:
        token, ttl = await _account(db, settings, cipher).create_mfa_challenge(ctx, user)
        return MfaChallengeResponse(mfa_token=token, expires_in=ttl)
    auth = await identity.start_session(ctx, user, membership)
    return await _issue(response, db, settings, jwt_service, auth)


@router.post("/mfa/verify", response_model=AuthResponse)
async def verify_mfa(
    body: MfaVerifyRequest,
    request: Request,
    response: Response,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: AppSettings,
    cipher: OptionalCipher,
    jwt_service: Jwt,
) -> AuthResponse:
    """Giriş sırasında doğrulama kodu veya kurtarma kodu ile oturumu tamamlar."""
    await _limit_ip(request, "mfa-verify:ip", settings.token_rate_limit_per_minute, 60)
    user = await _account(db, settings, cipher).verify_mfa_challenge(
        ctx, token=body.mfa_token, code=body.code, recovery_code=body.recovery_code
    )
    identity = _identity(db, settings, cipher)
    auth = await identity.start_session(ctx, user, await identity.get_active_membership(user.id))
    return await _issue(response, db, settings, jwt_service, auth)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: AppSettings,
    cipher: OptionalCipher,
    jwt_service: Jwt,
    vr_refresh: Annotated[str | None, Cookie()] = None,
) -> AuthResponse:
    await _limit_ip(request, "refresh:ip", settings.token_rate_limit_per_minute, 60)
    if not vr_refresh:
        raise UnauthorizedError("Oturum bulunamadı.", code="NO_REFRESH_TOKEN")
    auth = await _identity(db, settings, cipher).rotate_refresh_token(ctx, refresh_token=vr_refresh)
    return await _issue(response, db, settings, jwt_service, auth)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: AppSettings,
    cipher: OptionalCipher,
    vr_refresh: Annotated[str | None, Cookie()] = None,
) -> None:
    if vr_refresh:
        await _identity(db, settings, cipher).logout(ctx, refresh_token=vr_refresh)
    response.delete_cookie(
        _REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH, domain=settings.cookie_domain
    )


@router.get("/me", response_model=SessionUser)
async def me(ctx: CurrentContext, db: PlatformSession) -> SessionUser:
    user = await db.get(User, ctx.user_id)
    if user is None:
        raise UnauthorizedError
    membership = None
    if ctx.organization_id is not None:
        membership = (
            await db.execute(
                select(Membership).where(
                    Membership.user_id == user.id,
                    Membership.organization_id == ctx.organization_id,
                )
            )
        ).scalar_one_or_none()
    return await _session_user(db, user, membership)


# ------------------------------------------------------------------ invitations


@router.post("/invitations/preview", response_model=InvitationPreviewResponse)
async def preview_invitation(
    body: TokenRequest,
    request: Request,
    db: PlatformSession,
    settings: AppSettings,
    cipher: OptionalCipher,
) -> InvitationPreviewResponse:
    """Davet bağlantısının hangi organizasyona ait olduğunu gösterir."""
    await _limit_ip(request, "invitation-preview:ip", settings.token_rate_limit_per_minute, 60)
    preview = await _identity(db, settings, cipher).preview_invitation(token=body.token)
    return InvitationPreviewResponse(
        organization_name=preview.organization_name,
        email=preview.email,
        role=preview.role_key,
        role_label=ROLE_LABELS_TR.get(RoleKey(preview.role_key), preview.role_key),
        expires_at=preview.expires_at,
        account_exists=preview.account_exists,
    )


class AcceptInvitationResponse(BaseModel):
    message: str
    organization_id: str


@router.post(
    "/invitations/accept",
    status_code=status.HTTP_201_CREATED,
    response_model=AcceptInvitationResponse,
)
async def accept_invitation(
    body: AcceptInvitationRequest,
    request: Request,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: AppSettings,
    cipher: OptionalCipher,
) -> AcceptInvitationResponse:
    """Daveti kabul eder; ardından kullanıcı normal giriş akışıyla oturum açar."""
    await _limit_ip(request, "invitation-accept:ip", settings.token_rate_limit_per_minute, 60)
    _user, membership = await _identity(db, settings, cipher).accept_invitation(
        ctx, token=body.token, full_name=body.full_name, password=body.password
    )
    return AcceptInvitationResponse(
        message="Davet kabul edildi. Artık giriş yapabilirsiniz.",
        organization_id=str(membership.organization_id),
    )


# ------------------------------------------------------------------ password reset


_RESET_REQUESTED = (
    "Bu e-posta adresiyle kayıtlı etkin bir hesap varsa parola sıfırlama bağlantısı "
    "gönderildi. Gelen kutunuzu ve istenmeyen e-posta klasörünüzü kontrol edin."
)


@router.post(
    "/password/forgot", status_code=status.HTTP_202_ACCEPTED, response_model=MessageResponse
)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: AppSettings,
    cipher: OptionalCipher,
) -> MessageResponse:
    """Hesabın var olup olmadığını açığa çıkarmadan sıfırlama bağlantısı gönderir."""
    limit = settings.account_email_rate_limit_per_hour
    await _limit_ip(request, "password-forgot:ip", limit * 4, 3600)
    await enforce_rate_limit(
        request,
        scope="password-forgot:email",
        identity=body.email,
        limit=limit,
        window_seconds=3600,
    )
    await _account(db, settings, cipher).request_password_reset(ctx, email=body.email)
    return MessageResponse(message=_RESET_REQUESTED)


@router.post("/password/reset", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    response: Response,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: AppSettings,
    cipher: OptionalCipher,
) -> MessageResponse:
    await _limit_ip(request, "password-reset:ip", settings.token_rate_limit_per_minute, 60)
    await _account(db, settings, cipher).reset_password(
        ctx, token=body.token, new_password=body.password
    )
    response.delete_cookie(
        _REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH, domain=settings.cookie_domain
    )
    return MessageResponse(
        message="Parolanız güncellendi. Güvenliğiniz için tüm oturumlar kapatıldı; "
        "yeni parolanızla giriş yapın."
    )


# ------------------------------------------------------------------ e-mail verification


@router.post("/email/verify", response_model=MessageResponse)
async def verify_email(
    body: TokenRequest,
    request: Request,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: AppSettings,
    cipher: OptionalCipher,
) -> MessageResponse:
    await _limit_ip(request, "email-verify:ip", settings.token_rate_limit_per_minute, 60)
    await _account(db, settings, cipher).verify_email(ctx, token=body.token)
    return MessageResponse(message="E-posta adresiniz doğrulandı.")


@router.post(
    "/email/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MessageResponse,
)
async def resend_verification(
    request: Request,
    db: PlatformSession,
    ctx: CurrentContext,
    settings: AppSettings,
    cipher: OptionalCipher,
) -> MessageResponse:
    await enforce_rate_limit(
        request,
        scope="email-resend:user",
        identity=str(ctx.user_id),
        limit=settings.account_email_rate_limit_per_hour,
        window_seconds=3600,
    )
    sent = await _account(db, settings, cipher).resend_email_verification(
        ctx,
        user_id=_user_id(ctx),
    )
    if not sent:
        return MessageResponse(message="E-posta adresiniz zaten doğrulanmış.")
    return MessageResponse(message="Doğrulama bağlantısı e-posta adresinize gönderildi.")


# ------------------------------------------------------------------ two-factor authentication


@router.post("/mfa/setup", response_model=MfaSetupResponse)
async def mfa_setup(
    body: PasswordConfirmation,
    request: Request,
    db: PlatformSession,
    ctx: CurrentContext,
    settings: AppSettings,
    cipher: OptionalCipher,
) -> MfaSetupResponse:
    """Kimlik doğrulama uygulaması için gizli anahtar üretir (henüz etkin değil)."""
    await _limit_ip(request, "mfa-setup:ip", settings.token_rate_limit_per_minute, 60)
    secret, uri = await _account(db, settings, cipher).begin_mfa_setup(
        ctx,
        user_id=_user_id(ctx),
        password=body.password,
    )
    return MfaSetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/mfa/confirm", response_model=RecoveryCodesResponse)
async def mfa_confirm(
    body: MfaCodeRequest,
    request: Request,
    db: PlatformSession,
    ctx: CurrentContext,
    settings: AppSettings,
    cipher: OptionalCipher,
) -> RecoveryCodesResponse:
    await _limit_ip(request, "mfa-confirm:ip", settings.token_rate_limit_per_minute, 60)
    codes = await _account(db, settings, cipher).confirm_mfa(
        ctx,
        user_id=_user_id(ctx),
        code=body.code,
    )
    return RecoveryCodesResponse(recovery_codes=codes)


@router.post("/mfa/disable", response_model=MessageResponse)
async def mfa_disable(
    body: MfaSensitiveRequest,
    request: Request,
    db: PlatformSession,
    ctx: CurrentContext,
    settings: AppSettings,
    cipher: OptionalCipher,
) -> MessageResponse:
    await _limit_ip(request, "mfa-disable:ip", settings.token_rate_limit_per_minute, 60)
    await _account(db, settings, cipher).disable_mfa(
        ctx,
        user_id=_user_id(ctx),
        password=body.password,
        code=body.code,
    )
    return MessageResponse(message="İki adımlı doğrulama kapatıldı.")


@router.post("/mfa/recovery-codes", response_model=RecoveryCodesResponse)
async def mfa_regenerate_recovery_codes(
    body: MfaSensitiveRequest,
    request: Request,
    db: PlatformSession,
    ctx: CurrentContext,
    settings: AppSettings,
    cipher: OptionalCipher,
) -> RecoveryCodesResponse:
    await _limit_ip(request, "mfa-recovery:ip", settings.token_rate_limit_per_minute, 60)
    codes = await _account(db, settings, cipher).regenerate_recovery_codes(
        ctx,
        user_id=_user_id(ctx),
        password=body.password,
        code=body.code,
    )
    return RecoveryCodesResponse(recovery_codes=codes)
