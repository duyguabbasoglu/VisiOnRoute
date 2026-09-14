"""Prometheus scrape endpoint.

Disabled (404) unless ``VISIONROUTE_METRICS_TOKEN`` is configured; scrapers
authenticate with ``Authorization: Bearer <token>``. Queue gauges are sampled
from the database at scrape time with the RLS bypass and contain only counts.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from visionroute.api.errors import NotFoundError, UnauthorizedError
from visionroute.config.settings import Settings
from visionroute.infrastructure.db.models.ingestion import IngestEvent
from visionroute.infrastructure.db.models.mail import EmailMessage
from visionroute.infrastructure.db.models.notifications import WebhookDelivery
from visionroute.infrastructure.db.models.privacy import PrivacyRequest
from visionroute.infrastructure.db.models.system import OutboxEvent
from visionroute.infrastructure.db.tenancy import set_rls_bypass
from visionroute.observability.metrics import (
    LIVE_HUB_CONNECTED,
    LIVE_STREAM_SUBSCRIBERS,
    QUEUE_DEPTH,
    QUEUE_OLDEST_PENDING,
    render_latest,
)

router = APIRouter(include_in_schema=False)

# queue -> (model, status column, pending states, failed states, age column)
_QUEUES = {
    "outbox": (OutboxEvent, ("pending", "processing"), ("dead_letter",), OutboxEvent.occurred_at),
    "email": (EmailMessage, ("pending", "sending"), ("dead_letter",), EmailMessage.created_at),
    "webhook": (WebhookDelivery, ("pending",), ("dead_letter",), WebhookDelivery.created_at),
    "privacy": (PrivacyRequest, ("pending", "processing"), ("failed",), PrivacyRequest.created_at),
}


async def _sample_queues(session: AsyncSession, now: datetime) -> None:
    for queue, (model, pending, failed, age_column) in _QUEUES.items():
        status_column = model.status  # type: ignore[attr-defined]
        pending_count, oldest = (
            await session.execute(
                select(func.count(), func.min(age_column)).where(status_column.in_(pending))
            )
        ).one()
        failed_count = (
            await session.execute(select(func.count()).where(status_column.in_(failed)))
        ).scalar_one()
        QUEUE_DEPTH.labels(queue, "pending").set(int(pending_count))
        QUEUE_DEPTH.labels(queue, "failed").set(int(failed_count))
        QUEUE_OLDEST_PENDING.labels(queue).set(
            max(0.0, (now - oldest).total_seconds()) if oldest is not None else 0.0
        )
    quarantined = (
        await session.execute(select(func.count()).where(IngestEvent.status == "quarantined"))
    ).scalar_one()
    QUEUE_DEPTH.labels("ingest", "quarantined").set(int(quarantined))


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    if settings.metrics_token is None:
        raise NotFoundError
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ")
    expected = settings.metrics_token.get_secret_value()
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise UnauthorizedError

    factory: async_sessionmaker[AsyncSession] = request.app.state.db_session_factory
    async with factory() as session:
        await set_rls_bypass(session)
        await _sample_queues(session, datetime.now(UTC))

    hub = getattr(request.app.state, "live_hub", None)
    if hub is not None:
        LIVE_STREAM_SUBSCRIBERS.set(hub.subscriber_count())
        LIVE_HUB_CONNECTED.set(1 if hub.connected.is_set() else 0)
    body, content_type = render_latest()
    return Response(content=body, media_type=content_type, headers={"Cache-Control": "no-store"})
