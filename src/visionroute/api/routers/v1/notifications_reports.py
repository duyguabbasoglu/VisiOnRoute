"""Notifications, webhook endpoints, reports, and analytics (M9)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from visionroute.api.deps import (
    TenantSession,
    get_app_settings,
    require_permission,
)
from visionroute.api.errors import ForbiddenError, NotFoundError
from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.notifications.service import (
    DEV_URL_POLICY,
    PROD_URL_POLICY,
)
from visionroute.application.reports.service import ReportService
from visionroute.config.settings import Settings
from visionroute.domain.permissions import Permission
from visionroute.infrastructure.db.models.notifications import (
    Notification,
    NotificationRule,
    WebhookDelivery,
    WebhookEndpoint,
)
from visionroute.infrastructure.db.models.safety import SafetyEvent
from visionroute.infrastructure.db.models.telemetry import Trip
from visionroute.infrastructure.security.urlguard import UnsafeUrlError, validate_url

router = APIRouter(tags=["notifications-reports"])


def _tenant(ctx: RequestContext) -> uuid.UUID:
    if ctx.organization_id is None:  # pragma: no cover
        raise ForbiddenError
    return ctx.organization_id


# ------------------------------------------------------------- notifications


class NotificationOut(BaseModel):
    id: str
    level: str
    title_tr: str
    body_tr: str
    safety_event_id: str | None
    read_at: datetime | None
    created_at: datetime


class RuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    min_severity: str = Field(default="high", pattern="^(low|medium|high|critical)$")
    channels: list[str] = Field(default_factory=lambda: ["in_app"])


class RuleOut(BaseModel):
    id: str
    name: str
    kind: str
    min_severity: str
    channels: list[str]
    active: bool


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.EVENTS_READ)],
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[NotificationOut]:
    stmt = select(Notification).where(Notification.organization_id == _tenant(ctx))
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    result = await db.execute(stmt.order_by(Notification.created_at.desc()).limit(limit))
    return [
        NotificationOut(
            id=str(n.id),
            level=n.level,
            title_tr=n.title_tr,
            body_tr=n.body_tr,
            safety_event_id=str(n.safety_event_id) if n.safety_event_id else None,
            read_at=n.read_at,
            created_at=n.created_at,
        )
        for n in result.scalars()
    ]


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.EVENTS_READ)],
) -> None:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.organization_id != _tenant(ctx):
        raise NotFoundError("Bildirim bulunamadı.")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)


@router.post("/notification-rules", status_code=status.HTTP_201_CREATED, response_model=RuleOut)
async def create_rule(
    body: RuleCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.NOTIFICATIONS_MANAGE)],
) -> RuleOut:
    invalid = set(body.channels) - {"in_app", "webhook"}
    if invalid:
        from visionroute.application.errors import ValidationFailedError

        raise ValidationFailedError([f"Desteklenmeyen kanal: {', '.join(sorted(invalid))}"])
    rule = NotificationRule(
        organization_id=_tenant(ctx),
        name=body.name,
        min_severity=body.min_severity,
        channels=body.channels,
    )
    db.add(rule)
    await db.flush()
    await record_audit(
        db,
        ctx,
        action="notification_rule.created",
        resource_type="notification_rule",
        resource_id=str(rule.id),
        data={"min_severity": body.min_severity, "channels": body.channels},
    )
    return _rule_out(rule)


@router.get("/notification-rules", response_model=list[RuleOut])
async def list_rules(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.NOTIFICATIONS_MANAGE)],
) -> list[RuleOut]:
    result = await db.execute(
        select(NotificationRule).where(NotificationRule.organization_id == _tenant(ctx))
    )
    return [_rule_out(r) for r in result.scalars()]


# ------------------------------------------------------------- webhooks


class WebhookCreate(BaseModel):
    url: str = Field(max_length=500)
    description: str | None = Field(default=None, max_length=300)


class WebhookOut(BaseModel):
    id: str
    url: str
    description: str | None
    active: bool
    last_success_at: datetime | None
    last_failure_at: datetime | None
    # Shown once at creation so the receiver can verify signatures.
    secret: str | None = None


@router.post("/webhooks", status_code=status.HTTP_201_CREATED, response_model=WebhookOut)
async def create_webhook(
    body: WebhookCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.NOTIFICATIONS_MANAGE)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> WebhookOut:
    policy = PROD_URL_POLICY if settings.environment.is_production_like else DEV_URL_POLICY
    try:
        validate_url(body.url, policy=policy)
    except UnsafeUrlError as exc:
        from visionroute.application.errors import ValidationFailedError

        raise ValidationFailedError([str(exc)]) from exc

    endpoint = WebhookEndpoint(
        organization_id=_tenant(ctx),
        url=body.url,
        description=body.description,
        secret=f"whsec_{secrets.token_urlsafe(24)}",
    )
    db.add(endpoint)
    await db.flush()
    await record_audit(
        db,
        ctx,
        action="webhook.created",
        resource_type="webhook_endpoint",
        resource_id=str(endpoint.id),
        data={"url": body.url},
    )
    return WebhookOut(
        id=str(endpoint.id),
        url=endpoint.url,
        description=endpoint.description,
        active=endpoint.active,
        last_success_at=None,
        last_failure_at=None,
        secret=endpoint.secret,
    )


@router.get("/webhooks", response_model=list[WebhookOut])
async def list_webhooks(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.NOTIFICATIONS_MANAGE)],
) -> list[WebhookOut]:
    result = await db.execute(
        select(WebhookEndpoint).where(WebhookEndpoint.organization_id == _tenant(ctx))
    )
    return [
        WebhookOut(
            id=str(w.id),
            url=w.url,
            description=w.description,
            active=w.active,
            last_success_at=w.last_success_at,
            last_failure_at=w.last_failure_at,
        )
        for w in result.scalars()
    ]


@router.post("/webhooks/{webhook_id}/test", status_code=status.HTTP_202_ACCEPTED)
async def send_test_webhook(
    webhook_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.NOTIFICATIONS_MANAGE)],
) -> dict[str, str]:
    """Test teslimatı kuyruğa alır; worker imzalayıp gönderir."""
    endpoint = await db.get(WebhookEndpoint, webhook_id)
    if endpoint is None or endpoint.organization_id != _tenant(ctx):
        raise NotFoundError("Webhook bulunamadı.")
    db.add(
        WebhookDelivery(
            organization_id=_tenant(ctx),
            endpoint_id=endpoint.id,
            event_type="webhook.test",
            payload={"message": "VISiOnRoute test bildirimi", "sent_by": ctx.actor_label},
        )
    )
    return {"message": "Test teslimatı kuyruğa alındı."}


# ------------------------------------------------------------- reports


@router.get("/reports/safety-events.csv")
async def safety_events_csv(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.REPORTS_READ)],
) -> Response:
    content = await ReportService(db).safety_events_csv(_tenant(ctx))
    await record_audit(
        db, ctx, action="report.generated", resource_type="report", data={"kind": "csv"}
    )
    return Response(
        content=content.encode("utf-8-sig"),  # BOM: Excel'in Türkçe karakterleri tanıması için
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="guvenlik-olaylari.csv"'},
    )


@router.get("/reports/executive.pdf")
async def executive_pdf(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.REPORTS_READ)],
) -> Response:
    content = await ReportService(db).executive_pdf(_tenant(ctx))
    await record_audit(
        db, ctx, action="report.generated", resource_type="report", data={"kind": "pdf"}
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="yonetici-raporu.pdf"'},
    )


# ------------------------------------------------------------- analytics


class AnalyticsSummary(BaseModel):
    window_days: int
    total_events: int
    events_by_severity: dict[str, int]
    total_distance_km: float
    events_per_100km: float | None
    confirmation_rate: float | None
    data_note_tr: str


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def analytics_summary(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ANALYTICS_READ)],
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> AnalyticsSummary:
    tenant_id = _tenant(ctx)
    since = datetime.now(UTC) - timedelta(days=window_days)

    severity_rows = await db.execute(
        select(SafetyEvent.severity, func.count())
        .where(SafetyEvent.organization_id == tenant_id, SafetyEvent.occurred_at >= since)
        .group_by(SafetyEvent.severity)
    )
    by_severity = {row[0]: int(row[1]) for row in severity_rows.all()}
    total_events = sum(by_severity.values())

    reviewed = await db.execute(
        select(SafetyEvent.review_status, func.count())
        .where(SafetyEvent.organization_id == tenant_id, SafetyEvent.occurred_at >= since)
        .group_by(SafetyEvent.review_status)
    )
    review_counts = {row[0]: int(row[1]) for row in reviewed.all()}
    decided = sum(v for k, v in review_counts.items() if k != "pending")
    confirmation_rate = round(review_counts.get("confirmed", 0) / decided, 3) if decided else None

    distance = await db.execute(
        select(func.coalesce(func.sum(Trip.distance_km), 0.0)).where(
            Trip.organization_id == tenant_id, Trip.started_at >= since
        )
    )
    total_km = float(distance.scalar_one())
    per_100km = round(total_events / (total_km / 100.0), 3) if total_km > 0 else None

    return AnalyticsSummary(
        window_days=window_days,
        total_events=total_events,
        events_by_severity=by_severity,
        total_distance_km=round(total_km, 1),
        events_per_100km=per_100km,
        confirmation_rate=confirmation_rate,
        data_note_tr=(
            f"Pencere: son {window_days} gün. Payda: {round(total_km, 1)} km sürüş. "
            "Mesafe verisi olmayan dönemlerde 100 km başına oran hesaplanmaz."
        ),
    )


def _rule_out(r: NotificationRule) -> RuleOut:
    return RuleOut(
        id=str(r.id),
        name=r.name,
        kind=r.kind,
        min_severity=r.min_severity,
        channels=list(r.channels),
        active=r.active,
    )
