"""Evidence media endpoints (user-facing and machine-to-machine).

Signed URLs are returned only in response bodies to authorized callers and
are never logged or stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.api.deps import TenantSession, get_app_settings, require_permission
from visionroute.api.errors import ForbiddenError
from visionroute.api.ingest_deps import EvidenceAuth, IngestSession, ingest_context
from visionroute.application.context import RequestContext
from visionroute.application.evidence.service import EvidenceService, UploadSlot
from visionroute.config.settings import Settings
from visionroute.domain.permissions import Permission
from visionroute.infrastructure.db.models.safety import EventEvidence

router = APIRouter(tags=["evidence"])

AppSettings = Annotated[Settings, Depends(get_app_settings)]


class UploadRequest(BaseModel):
    content_type: str = Field(max_length=100)
    size_bytes: int = Field(gt=0)
    filename: str | None = Field(default=None, max_length=200)


class IngestUploadRequest(UploadRequest):
    safety_event_id: uuid.UUID


class UploadTarget(BaseModel):
    url: str
    method: str
    fields: dict[str, str]
    headers: dict[str, str]
    expires_at: datetime
    max_bytes: int


class UploadSlotOut(BaseModel):
    evidence_id: str
    upload: UploadTarget


class EvidenceMediaOut(BaseModel):
    id: str
    kind: str
    status: str
    content_type: str | None
    size_bytes: int | None
    redaction_status: str


class AccessUrlOut(BaseModel):
    url: str
    expires_in: int


def _service(request: Request, db: AsyncSession, settings: Settings) -> EvidenceService:
    return EvidenceService(db, request.app.state.object_storage, settings)


def _tenant(ctx: RequestContext) -> uuid.UUID:
    if ctx.organization_id is None:  # pragma: no cover
        raise ForbiddenError
    return ctx.organization_id


def _slot_out(slot: UploadSlot) -> UploadSlotOut:
    return UploadSlotOut(
        evidence_id=str(slot.evidence.id),
        upload=UploadTarget(
            url=slot.upload.url,
            method=slot.upload.method,
            fields=slot.upload.fields,
            headers=slot.upload.headers,
            expires_at=slot.upload.expires_at,
            max_bytes=slot.max_bytes,
        ),
    )


def _media_out(evidence: EventEvidence) -> EvidenceMediaOut:
    return EvidenceMediaOut(
        id=str(evidence.id),
        kind=evidence.kind,
        status=evidence.status,
        content_type=evidence.content_type,
        size_bytes=evidence.size_bytes,
        redaction_status=evidence.redaction_status,
    )


def _require_media_manager(ctx: RequestContext) -> None:
    if not (
        ctx.has_permission(Permission.EVENTS_REVIEW)
        and ctx.has_permission(Permission.EVIDENCE_RAW_MEDIA)
    ):
        raise ForbiddenError


# ------------------------------------------------------------------ users


@router.post(
    "/safety-events/{event_id}/evidence/uploads",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadSlotOut,
)
async def create_evidence_upload(
    event_id: uuid.UUID,
    body: UploadRequest,
    request: Request,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.EVIDENCE_RAW_MEDIA)],
    settings: AppSettings,
) -> UploadSlotOut:
    """Olaya görüntü/video kanıtı eklemek için kısa ömürlü yükleme bağlantısı üretir."""
    _require_media_manager(ctx)
    slot = await _service(request, db, settings).create_upload(
        ctx,
        _tenant(ctx),
        event_id,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        filename=body.filename,
    )
    return _slot_out(slot)


@router.post(
    "/safety-events/{event_id}/evidence/{evidence_id}/complete", response_model=EvidenceMediaOut
)
async def complete_evidence_upload(
    event_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.EVIDENCE_RAW_MEDIA)],
    settings: AppSettings,
) -> EvidenceMediaOut:
    _require_media_manager(ctx)
    evidence = await _service(request, db, settings).complete_upload(ctx, _tenant(ctx), evidence_id)
    return _media_out(evidence)


@router.get("/safety-events/{event_id}/evidence/{evidence_id}/access", response_model=AccessUrlOut)
async def evidence_access_url(
    event_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.EVIDENCE_RAW_MEDIA)],
    settings: AppSettings,
) -> AccessUrlOut:
    """Ham kanıt medyası için kısa ömürlü indirme bağlantısı (erişim denetime kaydedilir)."""
    url, ttl = await _service(request, db, settings).access_url(
        ctx, _tenant(ctx), event_id, evidence_id
    )
    return AccessUrlOut(url=url, expires_in=ttl)


@router.delete(
    "/safety-events/{event_id}/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_evidence(
    event_id: uuid.UUID,
    evidence_id: uuid.UUID,
    request: Request,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.EVIDENCE_RAW_MEDIA)],
    settings: AppSettings,
) -> None:
    _require_media_manager(ctx)
    await _service(request, db, settings).delete(ctx, _tenant(ctx), event_id, evidence_id)


# ------------------------------------------------------------------ integrations (API key)


@router.post(
    "/ingest/evidence/uploads", status_code=status.HTTP_201_CREATED, response_model=UploadSlotOut
)
async def ingest_evidence_upload(
    body: IngestUploadRequest,
    request: Request,
    db: IngestSession,
    principal: EvidenceAuth,
    settings: AppSettings,
) -> UploadSlotOut:
    """Kamera/entegrasyon: güvenlik olayına (webhook ile bildirilen kimlik) medya ekler."""
    slot = await _service(request, db, settings).create_upload(
        ingest_context(principal, request),
        principal.organization_id,
        body.safety_event_id,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        filename=body.filename,
        api_client_id=principal.api_client_id,
    )
    return _slot_out(slot)


@router.post("/ingest/evidence/{evidence_id}/complete", response_model=EvidenceMediaOut)
async def ingest_evidence_complete(
    evidence_id: uuid.UUID,
    request: Request,
    db: IngestSession,
    principal: EvidenceAuth,
    settings: AppSettings,
) -> EvidenceMediaOut:
    evidence = await _service(request, db, settings).complete_upload(
        ingest_context(principal, request), principal.organization_id, evidence_id
    )
    return _media_out(evidence)
