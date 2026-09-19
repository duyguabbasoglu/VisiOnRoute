"""FastAPI dependencies: sessions, authentication, authorization.

Two session dependencies exist on purpose (ADR-0010):

- ``PlatformSession`` — RLS bypass, only for auth flows and platform admin.
- ``TenantSession``  — tenant-bound; RLS restricts rows to the caller's
  organization even if application-level filtering has a bug.
"""

from __future__ import annotations

import ipaddress
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from visionroute.api.errors import ApiError, ForbiddenError, UnauthorizedError
from visionroute.application.context import RequestContext
from visionroute.config.settings import Settings
from visionroute.domain.permissions import Permission, RoleKey
from visionroute.infrastructure.db.models.identity import Membership, OrganizationSettings, User
from visionroute.infrastructure.db.tenancy import set_rls_bypass, set_tenant
from visionroute.infrastructure.security.crypto import FieldCipher
from visionroute.infrastructure.security.tokens import AccessTokenClaims, JwtService, TokenError


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_jwt_service(request: Request) -> JwtService:
    service: JwtService | None = getattr(request.app.state, "jwt_service", None)
    if service is None:
        raise UnauthorizedError(
            "Kimlik servisi yapılandırılmamış (JWT anahtarları eksik).",
            code="AUTH_NOT_CONFIGURED",
            status_code=503,
        )
    return service


def get_optional_field_cipher(request: Request) -> FieldCipher | None:
    cipher: FieldCipher | None = getattr(request.app.state, "field_cipher", None)
    return cipher


def get_field_cipher(request: Request) -> FieldCipher:
    cipher: FieldCipher | None = getattr(request.app.state, "field_cipher", None)
    if cipher is None:
        raise ApiError(
            "Alan şifreleme anahtarı yapılandırılmamış; bu işlem şu anda yapılamıyor.",
            code="ENCRYPTION_NOT_CONFIGURED",
            status_code=503,
        )
    return cipher


def _session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.db_session_factory
    return factory


async def _open_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with _session_factory(request)() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


def _client_ip(request: Request) -> str | None:
    """Return the peer address only if it is a real IP (INET column safety)."""
    if request.client is None:
        return None
    try:
        return str(ipaddress.ip_address(request.client.host))
    except ValueError:
        return None


_SESSION_REVOKED_MESSAGE = "Oturumunuz artık geçerli değil. Lütfen yeniden giriş yapın."
# Account endpoints stay reachable so a user can enroll in MFA when required.
_MFA_ENROLLMENT_EXEMPT_PREFIX = "/api/v1/auth/"


@dataclass(frozen=True, slots=True)
class _AccessState:
    role: RoleKey | None
    is_platform_admin: bool
    email_verified: bool
    mfa_enabled: bool
    mfa_required: bool


async def _authoritative_access(request: Request, claims: AccessTokenClaims) -> _AccessState:
    """Re-validate the token subject against the database on every request.

    Access tokens live up to 15 minutes; trusting their claims alone would let
    a removed member, a demoted role or a disabled account keep its previous
    privileges until expiry. The database role is authoritative.
    """
    async with _session_factory(request)() as session:
        await set_rls_bypass(session)
        user = await session.get(User, claims.user_id)
        if user is None or user.status != "active":
            raise UnauthorizedError(_SESSION_REVOKED_MESSAGE, code="SESSION_REVOKED")
        # Password or MFA resets revoke every access token issued before them.
        if user.sessions_revoked_at is not None and claims.issued_at < user.sessions_revoked_at:
            raise UnauthorizedError(_SESSION_REVOKED_MESSAGE, code="SESSION_REVOKED")
        role: RoleKey | None = None
        mfa_required = False
        if claims.organization_id is not None:
            row = (
                await session.execute(
                    select(Membership.role_key, OrganizationSettings.security)
                    .outerjoin(
                        OrganizationSettings,
                        OrganizationSettings.organization_id == Membership.organization_id,
                    )
                    .where(
                        Membership.user_id == claims.user_id,
                        Membership.organization_id == claims.organization_id,
                        Membership.status == "active",
                    )
                )
            ).one_or_none()
            if row is None:
                raise UnauthorizedError(_SESSION_REVOKED_MESSAGE, code="SESSION_REVOKED")
            role = RoleKey(row[0])
            mfa_required = bool((row[1] or {}).get("mfa_required", False))
        return _AccessState(
            role=role,
            is_platform_admin=claims.is_platform_admin and user.platform_role == "super_admin",
            email_verified=user.email_verified_at is not None,
            mfa_enabled=user.mfa_enabled_at is not None,
            mfa_required=mfa_required,
        )


async def get_current_context(
    request: Request,
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
) -> RequestContext:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise UnauthorizedError
    try:
        claims = jwt_service.verify_access_token(auth_header.removeprefix("Bearer "))
    except TokenError as exc:
        raise UnauthorizedError from exc
    state = await _authoritative_access(request, claims)
    if (
        state.mfa_required
        and not state.mfa_enabled
        and not request.url.path.startswith(_MFA_ENROLLMENT_EXEMPT_PREFIX)
    ):
        raise ForbiddenError(
            "Organizasyonunuz iki adımlı doğrulamayı zorunlu kılıyor. Devam etmek için "
            "Hesap Güvenliği sayfasından etkinleştirin.",
            code="MFA_ENROLLMENT_REQUIRED",
        )
    return RequestContext(
        user_id=claims.user_id,
        organization_id=claims.organization_id,
        role=state.role,
        is_platform_admin=state.is_platform_admin,
        actor_label=str(claims.user_id),
        request_id=getattr(request.state, "request_id", None),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        email_verified=state.email_verified,
        mfa_enabled=state.mfa_enabled,
    )


async def revalidate_access(request: Request) -> bool:
    """Re-check the bearer token and account state for a long-lived stream.

    Returns False once the token expired or the user/membership was revoked,
    so streaming endpoints can terminate instead of serving stale privileges.
    """
    jwt_service: JwtService | None = getattr(request.app.state, "jwt_service", None)
    auth_header = request.headers.get("Authorization", "")
    if jwt_service is None or not auth_header.startswith("Bearer "):
        return False
    try:
        claims = jwt_service.verify_access_token(auth_header.removeprefix("Bearer "))
        await _authoritative_access(request, claims)
    except (TokenError, UnauthorizedError):
        return False
    return True


def get_anonymous_context(request: Request) -> RequestContext:
    return RequestContext(
        user_id=None,
        organization_id=None,
        role=None,
        is_platform_admin=False,
        actor_label="anonymous",
        request_id=getattr(request.state, "request_id", None),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )


CurrentContext = Annotated[RequestContext, Depends(get_current_context)]
AnonymousContext = Annotated[RequestContext, Depends(get_anonymous_context)]


async def get_platform_session(request: Request) -> AsyncIterator[AsyncSession]:
    """RLS-bypassing session. Restrict usage to auth and platform-admin paths."""
    async for session in _open_session(request):
        await set_rls_bypass(session)
        yield session


async def get_tenant_session(request: Request, ctx: CurrentContext) -> AsyncIterator[AsyncSession]:
    if ctx.organization_id is None:
        raise ForbiddenError("Bu uç nokta bir organizasyon bağlamı gerektirir.")
    async for session in _open_session(request):
        await set_tenant(session, ctx.organization_id)
        yield session


# scope="function": the session commits (and releases its connection) before
# the response is sent. With FastAPI's default request scope the commit runs
# after the response, so a client could act on a 201 whose row is not yet
# visible to its next request.
PlatformSession = Annotated[AsyncSession, Depends(get_platform_session, scope="function")]
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session, scope="function")]


def require_permission(permission: Permission) -> Any:
    """Dependency factory: 403 unless the caller holds ``permission``."""

    def dependency(ctx: CurrentContext) -> RequestContext:
        if not ctx.has_permission(permission):
            raise ForbiddenError
        return ctx

    return Depends(dependency)


def require_verified_email(
    ctx: CurrentContext, settings: Annotated[Settings, Depends(get_app_settings)]
) -> RequestContext:
    """Sensitive actions (inviting users, issuing API keys, creating webhooks,
    privacy exports) require a verified mailbox when the policy is enabled."""
    if settings.require_verified_email and not ctx.email_verified and not ctx.is_platform_admin:
        raise ForbiddenError(
            "Bu işlem için önce e-posta adresinizi doğrulamanız gerekiyor.",
            code="EMAIL_NOT_VERIFIED",
        )
    return ctx


VerifiedEmailContext = Annotated[RequestContext, Depends(require_verified_email)]


def require_platform_admin(ctx: CurrentContext) -> RequestContext:
    if not ctx.is_platform_admin:
        raise ForbiddenError
    return ctx


def require_tenant_id(ctx: RequestContext) -> uuid.UUID:
    if ctx.organization_id is None:
        raise ForbiddenError("Bu uç nokta bir organizasyon bağlamı gerektirir.")
    return ctx.organization_id
