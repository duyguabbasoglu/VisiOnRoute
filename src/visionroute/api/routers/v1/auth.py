"""Authentication endpoints (Türkçe müşteri mesajları)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from visionroute.api.deps import (
    AnonymousContext,
    CurrentContext,
    PlatformSession,
    get_app_settings,
    get_jwt_service,
)
from visionroute.api.errors import UnauthorizedError
from visionroute.api.ratelimit import client_identity, enforce_rate_limit
from visionroute.application.identity.service import AuthenticatedUser, IdentityService
from visionroute.config.settings import Settings
from visionroute.domain.permissions import ROLE_LABELS_TR, RoleKey
from visionroute.infrastructure.security.tokens import JwtService

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "vr_refresh"


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=200)


class SessionUser(BaseModel):
    id: str
    email: str
    full_name: str
    organization_id: str | None
    organization_name: str | None
    role: str | None
    role_label: str | None
    is_platform_admin: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 — OAuth2 token type label, not a secret
    expires_in: int
    user: SessionUser


def _issue(
    response: Response,
    settings: Settings,
    jwt_service: JwtService,
    auth: AuthenticatedUser,
) -> AuthResponse:
    role = auth.membership.role_key if auth.membership else None
    organization_id = auth.membership.organization_id if auth.membership else None
    access_token = jwt_service.issue_access_token(
        user_id=auth.user.id,
        organization_id=organization_id,
        role=role,
        is_platform_admin=auth.user.platform_role == "super_admin",
    )
    response.set_cookie(
        _REFRESH_COOKIE,
        auth.refresh_token_cleartext,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
    )
    return AuthResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_seconds,
        user=SessionUser(
            id=str(auth.user.id),
            email=auth.user.email,
            full_name=auth.user.full_name,
            organization_id=str(organization_id) if organization_id else None,
            organization_name=None,
            role=role,
            role_label=ROLE_LABELS_TR.get(RoleKey(role)) if role else None,
            is_platform_admin=auth.user.platform_role == "super_admin",
        ),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=AuthResponse)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: Annotated[Settings, Depends(get_app_settings)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
) -> AuthResponse:
    """Yeni organizasyon kaydı: organizasyonu ve sahibini birlikte oluşturur."""
    await enforce_rate_limit(
        request,
        scope="register:ip",
        identity=client_identity(request),
        limit=settings.register_rate_limit_per_hour,
        window_seconds=3600,
    )
    service = IdentityService(db, settings.refresh_token_ttl_seconds)
    await service.register_organization(
        ctx,
        organization_name=body.organization_name,
        slug=body.slug,
        owner_email=body.email,
        owner_full_name=body.full_name,
        owner_password=body.password,
    )
    auth = await service.login(ctx, email=body.email, password=body.password)
    return _issue(response, settings, jwt_service, auth)


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: Annotated[Settings, Depends(get_app_settings)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
) -> AuthResponse:
    ip = client_identity(request)
    await enforce_rate_limit(
        request,
        scope="login:ip",
        identity=ip,
        limit=settings.login_ip_rate_limit_per_minute,
        window_seconds=60,
    )
    await enforce_rate_limit(
        request,
        scope="login:ip-email",
        identity=f"{ip}|{body.email}",
        limit=settings.login_rate_limit_per_minute,
        window_seconds=60,
    )
    service = IdentityService(db, settings.refresh_token_ttl_seconds)
    auth = await service.login(ctx, email=body.email, password=body.password)
    return _issue(response, settings, jwt_service, auth)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: Annotated[Settings, Depends(get_app_settings)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
    vr_refresh: Annotated[str | None, Cookie()] = None,
) -> AuthResponse:
    await enforce_rate_limit(
        request,
        scope="refresh:ip",
        identity=client_identity(request),
        limit=settings.token_rate_limit_per_minute,
        window_seconds=60,
    )
    if not vr_refresh:
        raise UnauthorizedError("Oturum bulunamadı.", code="NO_REFRESH_TOKEN")
    service = IdentityService(db, settings.refresh_token_ttl_seconds)
    auth = await service.rotate_refresh_token(ctx, refresh_token=vr_refresh)
    return _issue(response, settings, jwt_service, auth)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: PlatformSession,
    ctx: AnonymousContext,
    settings: Annotated[Settings, Depends(get_app_settings)],
    vr_refresh: Annotated[str | None, Cookie()] = None,
) -> None:
    if vr_refresh:
        service = IdentityService(db, settings.refresh_token_ttl_seconds)
        await service.logout(ctx, refresh_token=vr_refresh)
    response.delete_cookie(_REFRESH_COOKIE, path="/api/v1/auth")


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
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AcceptInvitationResponse:
    """Daveti kabul eder; ardından kullanıcı normal giriş akışıyla oturum açar."""
    await enforce_rate_limit(
        request,
        scope="invitation-accept:ip",
        identity=client_identity(request),
        limit=settings.token_rate_limit_per_minute,
        window_seconds=60,
    )
    service = IdentityService(db, settings.refresh_token_ttl_seconds)
    _user, membership = await service.accept_invitation(
        ctx, token=body.token, full_name=body.full_name, password=body.password
    )
    return AcceptInvitationResponse(
        message="Davet kabul edildi. Artık giriş yapabilirsiniz.",
        organization_id=str(membership.organization_id),
    )


@router.get("/me", response_model=SessionUser)
async def me(ctx: CurrentContext, db: PlatformSession) -> SessionUser:
    from visionroute.infrastructure.db.models.identity import Organization, User

    user = await db.get(User, ctx.user_id)
    if user is None:
        raise UnauthorizedError
    organization_name = None
    if ctx.organization_id is not None:
        organization = await db.get(Organization, ctx.organization_id)
        organization_name = organization.name if organization else None
    return SessionUser(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        organization_id=str(ctx.organization_id) if ctx.organization_id else None,
        organization_name=organization_name,
        role=ctx.role.value if ctx.role else None,
        role_label=ROLE_LABELS_TR.get(ctx.role) if ctx.role else None,
        is_platform_admin=ctx.is_platform_admin,
    )
