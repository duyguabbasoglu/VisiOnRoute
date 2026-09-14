"""KVKK: data-subject requests (export / erasure) and retention settings."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.api.deps import (
    CurrentContext,
    TenantSession,
    get_app_settings,
    require_permission,
    require_tenant_id,
)
from visionroute.api.errors import UnauthorizedError
from visionroute.api.ratelimit import enforce_rate_limit
from visionroute.application.context import RequestContext
from visionroute.application.privacy.service import PrivacyService, RetentionView
from visionroute.config.settings import Settings
from visionroute.domain.permissions import Permission
from visionroute.domain.privacy import (
    KIND_LABELS_TR,
    MIN_RETENTION_DAYS,
    RETENTION_CATEGORIES,
    STATUS_LABELS_TR,
    SUBJECT_LABELS_TR,
    PrivacyRequestKind,
    PrivacySubjectType,
)
from visionroute.infrastructure.db.models.privacy import PrivacyRequest

router = APIRouter(prefix="/privacy", tags=["privacy"])

AppSettings = Annotated[Settings, Depends(get_app_settings)]
RetentionManager = Annotated[RequestContext, require_permission(Permission.ORG_RETENTION_MANAGE)]


class PrivacyRequestCreate(BaseModel):
    kind: PrivacyRequestKind
    subject_type: PrivacySubjectType
    subject_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=500)


class PrivacyRequestOut(BaseModel):
    id: str
    kind: str
    kind_label: str
    subject_type: str
    subject_label: str
    subject_id: str
    subject_name: str | None
    status: str
    status_label: str
    reason: str | None
    created_at: datetime
    completed_at: datetime | None
    download_available: bool
    artifact_expires_at: datetime | None
    result: dict[str, object]
    error_code: str | None


class DownloadOut(BaseModel):
    url: str
    expires_in: int


class RetentionCategory(BaseModel):
    key: str
    label: str
    override_days: int | None
    effective_days: int


class RetentionOut(BaseModel):
    plan_days: int
    min_days: int
    categories: list[RetentionCategory]


class RetentionUpdate(BaseModel):
    telemetry_days: int | None = None
    evidence_media_days: int | None = None


def _service(request: Request, db: AsyncSession, settings: Settings) -> PrivacyService:
    return PrivacyService(db, request.app.state.object_storage, settings)


def _out(item: PrivacyRequest, names: dict[uuid.UUID, str]) -> PrivacyRequestOut:
    now = datetime.now().astimezone()
    return PrivacyRequestOut(
        id=str(item.id),
        kind=item.kind,
        kind_label=KIND_LABELS_TR.get(item.kind, item.kind),
        subject_type=item.subject_type,
        subject_label=SUBJECT_LABELS_TR.get(item.subject_type, item.subject_type),
        subject_id=str(item.subject_id),
        subject_name=names.get(item.subject_id),
        status=item.status,
        status_label=STATUS_LABELS_TR.get(item.status, item.status),
        reason=item.reason,
        created_at=item.created_at,
        completed_at=item.completed_at,
        download_available=bool(
            item.artifact_key and item.artifact_expires_at and item.artifact_expires_at > now
        ),
        artifact_expires_at=item.artifact_expires_at,
        result=item.result,
        error_code=item.error_code,
    )


def _retention_out(view: RetentionView) -> RetentionOut:
    effective = {
        "telemetry_days": view.effective.telemetry_days,
        "evidence_media_days": view.effective.evidence_media_days,
    }
    return RetentionOut(
        plan_days=view.plan_days,
        min_days=MIN_RETENTION_DAYS,
        categories=[
            RetentionCategory(
                key=key,
                label=label,
                override_days=view.overrides.get(key),
                effective_days=effective[key],
            )
            for key, label in RETENTION_CATEGORIES.items()
        ],
    )


# ------------------------------------------------------------ administrators


@router.get("/requests", response_model=list[PrivacyRequestOut])
async def list_privacy_requests(
    request: Request, db: TenantSession, ctx: RetentionManager, settings: AppSettings
) -> list[PrivacyRequestOut]:
    service = _service(request, db, settings)
    items = await service.list_requests(require_tenant_id(ctx))
    names = await service.subject_names(items)
    return [_out(item, names) for item in items]


@router.post("/requests", status_code=status.HTTP_201_CREATED, response_model=PrivacyRequestOut)
async def create_privacy_request(
    body: PrivacyRequestCreate,
    request: Request,
    db: TenantSession,
    ctx: RetentionManager,
    settings: AppSettings,
) -> PrivacyRequestOut:
    """KVKK kapsamında sürücü veya kullanıcı için dışa aktarma ya da silme talebi oluşturur."""
    # Each request becomes a worker job (archives, erasure); bound the load.
    await enforce_rate_limit(
        request,
        scope="privacy-request:org",
        identity=str(require_tenant_id(ctx)),
        limit=50,
        window_seconds=3600,
    )
    service = _service(request, db, settings)
    item = await service.create_request(
        ctx,
        require_tenant_id(ctx),
        kind=body.kind,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        reason=body.reason,
    )
    return _out(item, await service.subject_names([item]))


@router.post("/requests/{request_id}/cancel", response_model=PrivacyRequestOut)
async def cancel_privacy_request(
    request_id: uuid.UUID,
    request: Request,
    db: TenantSession,
    ctx: RetentionManager,
    settings: AppSettings,
) -> PrivacyRequestOut:
    service = _service(request, db, settings)
    item = await service.cancel(ctx, require_tenant_id(ctx), request_id)
    return _out(item, await service.subject_names([item]))


@router.get("/requests/{request_id}/download", response_model=DownloadOut)
async def download_privacy_export(
    request_id: uuid.UUID,
    request: Request,
    db: TenantSession,
    ctx: RetentionManager,
    settings: AppSettings,
) -> DownloadOut:
    url, ttl = await _service(request, db, settings).export_download_url(
        ctx, require_tenant_id(ctx), request_id
    )
    return DownloadOut(url=url, expires_in=ttl)


@router.get("/retention", response_model=RetentionOut)
async def get_retention(
    request: Request,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ORG_READ)],
    settings: AppSettings,
) -> RetentionOut:
    view = await _service(request, db, settings).get_retention(require_tenant_id(ctx))
    return _retention_out(view)


@router.put("/retention", response_model=RetentionOut)
async def update_retention(
    body: RetentionUpdate,
    request: Request,
    db: TenantSession,
    ctx: RetentionManager,
    settings: AppSettings,
) -> RetentionOut:
    """Saklama sürelerini plan sınırı içinde kısaltır; boş değer plan varsayılanına döner."""
    view = await _service(request, db, settings).update_retention(
        ctx, require_tenant_id(ctx), body.model_dump()
    )
    return _retention_out(view)


# ------------------------------------------------------------ self service


@router.get("/me/requests", response_model=list[PrivacyRequestOut])
async def list_my_privacy_requests(
    request: Request, db: TenantSession, ctx: CurrentContext, settings: AppSettings
) -> list[PrivacyRequestOut]:
    service = _service(request, db, settings)
    items = await service.list_requests(require_tenant_id(ctx), subject_user_id=_user_id(ctx))
    return [_out(item, {}) for item in items]


@router.post("/me/export", status_code=status.HTTP_201_CREATED, response_model=PrivacyRequestOut)
async def request_my_export(
    request: Request, db: TenantSession, ctx: CurrentContext, settings: AppSettings
) -> PrivacyRequestOut:
    """Kullanıcının bu organizasyondaki kişisel verilerinin dışa aktarımını başlatır."""
    await enforce_rate_limit(
        request,
        scope="privacy-export:user",
        identity=str(_user_id(ctx)),
        limit=3,
        window_seconds=86_400,
    )
    item = await _service(request, db, settings).create_request(
        ctx,
        require_tenant_id(ctx),
        kind=PrivacyRequestKind.EXPORT,
        subject_type=PrivacySubjectType.USER,
        subject_id=_user_id(ctx),
        reason=None,
    )
    return _out(item, {})


@router.get("/me/requests/{request_id}/download", response_model=DownloadOut)
async def download_my_export(
    request_id: uuid.UUID,
    request: Request,
    db: TenantSession,
    ctx: CurrentContext,
    settings: AppSettings,
) -> DownloadOut:
    url, ttl = await _service(request, db, settings).export_download_url(
        ctx, require_tenant_id(ctx), request_id, subject_user_id=_user_id(ctx)
    )
    return DownloadOut(url=url, expires_in=ttl)


def _user_id(ctx: RequestContext) -> uuid.UUID:
    if ctx.user_id is None:
        raise UnauthorizedError
    return ctx.user_id
