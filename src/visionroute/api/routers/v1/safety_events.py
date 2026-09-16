"""Safety events: list, filter, detail with explanation and evidence."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from visionroute.api.deps import TenantSession, get_optional_field_cipher, require_permission
from visionroute.api.errors import ForbiddenError, NotFoundError
from visionroute.application.context import RequestContext
from visionroute.domain.coaching import RESOLUTION_LABELS_TR, CoachingStatus, Resolution
from visionroute.domain.coaching import STATUS_LABELS_TR as COACHING_STATUS_LABELS_TR
from visionroute.domain.permissions import Permission
from visionroute.domain.safety import (
    EVENT_LABELS_TR,
    SEVERITY_LABELS_TR,
    SafetyEventType,
    Severity,
)
from visionroute.infrastructure.db.models.coaching import CoachingAction
from visionroute.infrastructure.db.models.safety import EventEvidence, SafetyEvent
from visionroute.infrastructure.security.crypto import FieldCipher

router = APIRouter(prefix="/safety-events", tags=["safety-events"])


def _tenant(ctx: RequestContext) -> uuid.UUID:
    if ctx.organization_id is None:  # pragma: no cover
        raise ForbiddenError
    return ctx.organization_id


class Explanation(BaseModel):
    ne_oldu: str
    ne_zaman: datetime
    nerede: dict[str, float] | None
    hangi_veri: str
    hangi_kural: str
    esik: float | None
    olculen_deger: float | None
    guven_seviyesi: float
    veri_kalitesi: float | None
    inceleme_gerekli: bool


class SafetyEventOut(BaseModel):
    id: str
    event_type: str
    event_label: str
    severity: str
    severity_label: str
    confidence: float
    occurred_at: datetime
    vehicle_id: str
    driver_id: str | None
    trip_id: str | None
    latitude: float | None
    longitude: float | None
    reason_tr: str
    review_status: str
    occurrence_count: int
    needs_review: bool


class EvidenceOut(BaseModel):
    id: str
    kind: str
    telemetry_window: dict[str, object] | None
    captured_at: datetime | None
    # Media evidence (snapshot/clip); the file itself needs a signed URL from
    # /evidence/{id}/access and events.evidence.raw_media.
    status: str
    content_type: str | None = None
    size_bytes: int | None = None
    redaction_status: str


class CoachingLink(BaseModel):
    id: str
    status: str
    status_label: str
    due_at: datetime | None


class SafetyEventDetail(SafetyEventOut):
    explanation: Explanation
    ruleset_version: int
    severity_framework_version: int
    evidence: list[EvidenceOut]
    evidence_restricted: bool = False
    resolution: str | None = None
    resolution_label: str | None = None
    root_cause: str | None = None
    reviewer_notes: str | None = None
    reviewed_at: datetime | None = None
    # Latest coaching action for the event (None without COACHING_READ).
    coaching_action: CoachingLink | None = None


class SafetyEventList(BaseModel):
    items: list[SafetyEventOut]
    total: int
    limit: int
    offset: int


def _to_out(e: SafetyEvent) -> SafetyEventOut:
    return SafetyEventOut(
        id=str(e.id),
        event_type=e.event_type,
        event_label=_label(e.event_type),
        severity=e.severity,
        severity_label=SEVERITY_LABELS_TR.get(Severity(e.severity), e.severity),
        confidence=round(e.confidence, 3),
        occurred_at=e.occurred_at,
        vehicle_id=str(e.vehicle_id),
        driver_id=str(e.driver_id) if e.driver_id else None,
        trip_id=str(e.trip_id) if e.trip_id else None,
        latitude=e.latitude,
        longitude=e.longitude,
        reason_tr=e.reason_tr,
        review_status=e.review_status,
        occurrence_count=e.occurrence_count,
        needs_review=e.needs_review,
    )


def _label(event_type: str) -> str:
    try:
        return EVENT_LABELS_TR[SafetyEventType(event_type)]
    except ValueError:
        return event_type


@router.get("", response_model=SafetyEventList)
async def list_safety_events(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.EVENTS_READ)],
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    severity: str | None = None,
    review_status: str | None = None,
    event_type: str | None = None,
    trip_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SafetyEventList:
    tenant_id = _tenant(ctx)
    conditions = [SafetyEvent.organization_id == tenant_id]
    if vehicle_id is not None:
        conditions.append(SafetyEvent.vehicle_id == vehicle_id)
    if trip_id is not None:
        conditions.append(SafetyEvent.trip_id == trip_id)
    if driver_id is not None:
        conditions.append(SafetyEvent.driver_id == driver_id)
    if severity is not None:
        conditions.append(SafetyEvent.severity == severity)
    if review_status is not None:
        conditions.append(SafetyEvent.review_status == review_status)
    if event_type is not None:
        conditions.append(SafetyEvent.event_type == event_type)

    total = int((await db.execute(select(func.count()).where(*conditions))).scalar_one())
    result = await db.execute(
        select(SafetyEvent)
        .where(*conditions)
        .order_by(SafetyEvent.occurred_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return SafetyEventList(
        items=[_to_out(e) for e in result.scalars()],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{event_id}", response_model=SafetyEventDetail)
async def get_safety_event(
    event_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.EVENTS_READ)],
) -> SafetyEventDetail:
    tenant_id = _tenant(ctx)
    event = await db.get(SafetyEvent, event_id)
    if event is None or event.organization_id != tenant_id:
        raise NotFoundError("Güvenlik olayı bulunamadı.")

    # Evidence is personal data with its own permission; EVENTS_READ alone
    # (e.g. analysts) sees the explanation but not the evidence payload.
    evidence_restricted = not ctx.has_permission(Permission.EVIDENCE_READ)
    evidence: list[EvidenceOut] = []
    if not evidence_restricted:
        evidence_rows = await db.execute(
            select(EventEvidence)
            .where(
                EventEvidence.safety_event_id == event_id,
                EventEvidence.organization_id == tenant_id,
            )
            .order_by(EventEvidence.created_at)
        )
        evidence = [
            EvidenceOut(
                id=str(ev.id),
                kind=ev.kind,
                telemetry_window=ev.telemetry_window,
                captured_at=ev.captured_at,
                status=ev.status,
                content_type=ev.content_type,
                size_bytes=ev.size_bytes,
                redaction_status=ev.redaction_status,
            )
            for ev in evidence_rows.scalars()
            # Abandoned upload slots are noise, not evidence.
            if ev.status != "pending_upload"
        ]

    base = _to_out(event)
    explanation = Explanation(
        ne_oldu=base.event_label,
        ne_zaman=event.occurred_at,
        nerede=(
            {"latitude": event.latitude, "longitude": event.longitude}
            if event.latitude is not None and event.longitude is not None
            else None
        ),
        hangi_veri="Telemetri (kural motoru)",
        hangi_kural=f"{event.event_type} v{event.ruleset_version}",
        esik=event.threshold,
        olculen_deger=event.measured_value,
        guven_seviyesi=round(event.confidence, 3),
        veri_kalitesi=event.data_quality,
        inceleme_gerekli=event.needs_review,
    )
    coaching_link: CoachingLink | None = None
    if ctx.has_permission(Permission.COACHING_READ):
        latest = (
            await db.execute(
                select(CoachingAction)
                .where(
                    CoachingAction.organization_id == tenant_id,
                    CoachingAction.safety_event_id == event_id,
                )
                .order_by(CoachingAction.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is not None:
            coaching_link = CoachingLink(
                id=str(latest.id),
                status=latest.status,
                status_label=COACHING_STATUS_LABELS_TR[CoachingStatus(latest.status)],
                due_at=latest.due_at,
            )
    resolution_label = None
    if event.resolution:
        try:
            resolution_label = RESOLUTION_LABELS_TR[Resolution(event.resolution)]
        except ValueError:
            resolution_label = event.resolution
    return SafetyEventDetail(
        **base.model_dump(),
        explanation=explanation,
        ruleset_version=event.ruleset_version,
        severity_framework_version=event.severity_framework_version,
        evidence=evidence,
        evidence_restricted=evidence_restricted,
        resolution=event.resolution,
        resolution_label=resolution_label,
        root_cause=event.root_cause,
        reviewer_notes=event.reviewer_notes,
        reviewed_at=event.reviewed_at,
        coaching_action=coaching_link,
    )


class ReviewRequest(BaseModel):
    decision: str = Field(pattern="^(confirmed|rejected|uncertain)$")
    notes: str | None = Field(default=None, max_length=4000)
    root_cause: str | None = Field(default=None, max_length=60)
    resolution: Resolution | None = None
    # Only used with resolution=kocluk_atandi.
    coaching_assignee_user_id: uuid.UUID | None = None
    coaching_due_at: datetime | None = None


class ReviewResponse(SafetyEventOut):
    coaching_action_id: str | None = None


@router.post("/{event_id}/review", response_model=ReviewResponse)
async def review_safety_event(
    event_id: uuid.UUID,
    body: ReviewRequest,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.EVENTS_REVIEW)],
    cipher: Annotated[FieldCipher | None, Depends(get_optional_field_cipher)],
) -> ReviewResponse:
    """Olayı onayla / reddet / belirsiz olarak işaretle; not ve çözüm ekle.
    `kocluk_atandi` çözümü onaylanan olay için koçluk görevi oluşturur (tekrarlanan
    isteklerde mevcut görev kullanılır)."""
    from visionroute.application.coaching.service import CoachingService
    from visionroute.application.mail.service import MailService
    from visionroute.application.safety.review import CoachingAssignment, EventReviewService

    service = EventReviewService(db, CoachingService(db, MailService(db, cipher)))
    outcome = await service.review(
        ctx,
        _tenant(ctx),
        event_id,
        decision=body.decision,
        notes=body.notes,
        root_cause=body.root_cause,
        resolution=body.resolution,
        coaching=CoachingAssignment(
            assignee_user_id=body.coaching_assignee_user_id, due_at=body.coaching_due_at
        ),
    )
    return ReviewResponse(
        **_to_out(outcome.event).model_dump(),
        coaching_action_id=str(outcome.coaching_action.id) if outcome.coaching_action else None,
    )
