"""Safety events: list, filter, detail with explanation and evidence."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from visionroute.api.deps import TenantSession, require_permission
from visionroute.api.errors import ForbiddenError, NotFoundError
from visionroute.application.context import RequestContext
from visionroute.domain.permissions import Permission
from visionroute.domain.safety import (
    EVENT_LABELS_TR,
    SEVERITY_LABELS_TR,
    SafetyEventType,
    Severity,
)
from visionroute.infrastructure.db.models.safety import EventEvidence, SafetyEvent

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


class SafetyEventDetail(SafetyEventOut):
    explanation: Explanation
    ruleset_version: int
    severity_framework_version: int
    evidence: list[EvidenceOut]


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
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SafetyEventList:
    tenant_id = _tenant(ctx)
    conditions = [SafetyEvent.organization_id == tenant_id]
    if vehicle_id is not None:
        conditions.append(SafetyEvent.vehicle_id == vehicle_id)
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

    evidence_rows = await db.execute(
        select(EventEvidence)
        .where(EventEvidence.safety_event_id == event_id)
        .order_by(EventEvidence.created_at)
    )
    evidence = [
        EvidenceOut(
            id=str(ev.id),
            kind=ev.kind,
            telemetry_window=ev.telemetry_window,
            captured_at=ev.captured_at,
        )
        for ev in evidence_rows.scalars()
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
    return SafetyEventDetail(
        **base.model_dump(),
        explanation=explanation,
        ruleset_version=event.ruleset_version,
        severity_framework_version=event.severity_framework_version,
        evidence=evidence,
    )


class ReviewRequest(BaseModel):
    decision: str = Field(pattern="^(confirmed|rejected|uncertain)$")
    notes: str | None = Field(default=None, max_length=4000)
    root_cause: str | None = Field(default=None, max_length=60)
    resolution: str | None = Field(default=None, max_length=40)


@router.post("/{event_id}/review", response_model=SafetyEventOut)
async def review_safety_event(
    event_id: uuid.UUID,
    body: ReviewRequest,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.EVENTS_REVIEW)],
) -> SafetyEventOut:
    """Olayı onayla / reddet / belirsiz olarak işaretle; not ve çözüm ekle."""
    from visionroute.application.safety.review import EventReviewService

    service = EventReviewService(db)
    event = await service.review(
        ctx,
        _tenant(ctx),
        event_id,
        decision=body.decision,
        notes=body.notes,
        root_cause=body.root_cause,
        resolution=body.resolution,
    )
    return _to_out(event)
