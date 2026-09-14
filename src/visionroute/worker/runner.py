"""Outbox worker (ADR-0002).

Consumes ``outbox_events`` with FOR UPDATE SKIP LOCKED so multiple worker
processes run safely in parallel. Each event is dispatched to a handler inside
its own SAVEPOINT: a handler failure (including a database error) rolls back
only that event's changes, so one poison event cannot block the batch.
Failures back off exponentially and land in ``dead_letter`` after max attempts.

Network I/O (webhook deliveries) runs in a separate transaction after the
claim transaction commits, so slow receivers never hold outbox row locks.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from visionroute.application.mail.delivery import MailDeliveryService
from visionroute.application.notifications.service import (
    DEV_URL_POLICY,
    PROD_URL_POLICY,
    NotificationService,
)
from visionroute.application.privacy.processor import PrivacyProcessor
from visionroute.application.safety.engine import SafetyEngine
from visionroute.application.telemetry.service import TelemetryService
from visionroute.config.settings import Settings
from visionroute.infrastructure.db.engine import build_engine, build_session_factory
from visionroute.infrastructure.db.models.ingestion import IngestEvent
from visionroute.infrastructure.db.models.system import OutboxEvent
from visionroute.infrastructure.db.tenancy import set_rls_bypass
from visionroute.infrastructure.mail import build_mail_sender
from visionroute.infrastructure.realtime import notify_live
from visionroute.infrastructure.security.crypto import build_field_cipher
from visionroute.infrastructure.storage import build_object_storage
from visionroute.observability.logging import get_logger

logger = get_logger("visionroute.worker")

_MAX_ATTEMPTS = 8
_BATCH = 50


class Worker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine = build_engine(settings)
        self._factory: async_sessionmaker[AsyncSession] = build_session_factory(self._engine)
        self._cipher = build_field_cipher(settings)
        self._mail_delivery = MailDeliveryService(
            self._factory, build_mail_sender(settings), self._cipher, settings
        )
        self._privacy = PrivacyProcessor(
            self._factory, build_object_storage(settings), self._cipher
        )
        self._stopping = False

    async def run_forever(self, *, poll_interval: float = 1.0) -> None:
        logger.info("worker_started")
        try:
            while not self._stopping:
                processed = await self.run_once()
                if processed == 0:
                    await asyncio.sleep(poll_interval)
        finally:
            await self._engine.dispose()
            logger.info("worker_stopped")

    async def run_once(self) -> int:
        """Claim and process up to one batch. Returns how many were handled."""
        handled = await self._process_outbox_batch()
        handled += await self._deliver_webhooks()
        handled += (await self._mail_delivery.deliver_due()).handled
        handled += await self._privacy.process_due()
        return handled

    async def _process_outbox_batch(self) -> int:
        handled = 0
        async with self._factory() as session:
            await set_rls_bypass(session)
            events = await self._claim(session)
            for event in events:
                try:
                    async with session.begin_nested():
                        await self._dispatch(session, event)
                        await self._notify_live(session, event)
                except Exception as exc:
                    # The savepoint rollback expired the event; reload it
                    # before recording the failure.
                    await session.refresh(event)
                    self._mark_retry(event, exc)
                    logger.warning(
                        "outbox_event_failed",
                        event_type=event.event_type,
                        attempts=event.attempts,
                        error_type=type(exc).__name__,
                    )
                    continue
                event.status = "done"
                event.processed_at = datetime.now(UTC)
                handled += 1
            await session.commit()
        return handled

    async def _deliver_webhooks(self) -> int:
        policy = (
            PROD_URL_POLICY if self._settings.environment.is_production_like else DEV_URL_POLICY
        )
        async with self._factory() as session:
            await set_rls_bypass(session)
            delivered, _failed = await NotificationService(session, self._cipher).deliver_pending(
                url_policy=policy
            )
            await session.commit()
        return delivered

    async def _claim(self, session: AsyncSession) -> list[OutboxEvent]:
        now = datetime.now(UTC)
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status.in_(("pending", "processing")),
                OutboxEvent.next_attempt_at <= now,
            )
            .order_by(OutboxEvent.occurred_at)
            .limit(_BATCH)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        events = list(result.scalars())
        for event in events:
            event.status = "processing"
        return events

    async def _dispatch(self, session: AsyncSession, event: OutboxEvent) -> None:
        if event.event_type == "ingest.event_accepted":
            await self._handle_ingest_accepted(session, event)
        elif event.event_type == "safety.event_created":
            await self._handle_safety_event_created(session, event)
        # Unknown types are acknowledged as done (no-op) so they don't clog
        # the queue.

    async def _notify_live(self, session: AsyncSession, event: OutboxEvent) -> None:
        """Signal live-operation streams; delivered by PostgreSQL on commit."""
        if event.event_type == "safety.event_created":
            organization_id = event.payload.get("organization_id")
            if organization_id is not None:
                await notify_live(session, uuid.UUID(str(organization_id)), "safety_event")
        elif event.event_type == "ingest.event_accepted":
            ingest_event_id = event.payload.get("ingest_event_id")
            ingest_event = (
                await session.get(IngestEvent, ingest_event_id) if ingest_event_id else None
            )
            if ingest_event is not None and ingest_event.status == "processed":
                await notify_live(session, ingest_event.organization_id, "positions")

    async def _handle_safety_event_created(self, session: AsyncSession, event: OutboxEvent) -> None:
        payload = event.payload
        organization_id = payload.get("organization_id")
        safety_event_id = payload.get("safety_event_id")
        if organization_id is None or safety_event_id is None:
            return
        await NotificationService(session).on_safety_event(
            organization_id=uuid.UUID(str(organization_id)),
            safety_event_id=uuid.UUID(str(safety_event_id)),
            event_type=str(payload.get("event_type", "")),
            severity=str(payload.get("severity", "low")),
        )

    async def _handle_ingest_accepted(self, session: AsyncSession, event: OutboxEvent) -> None:
        ingest_event_id = event.payload.get("ingest_event_id")
        if ingest_event_id is None:
            return
        ingest_event = await session.get(IngestEvent, ingest_event_id)
        if ingest_event is None or ingest_event.status != "accepted":
            return
        ingest_event.status = "processing"
        processed = await TelemetryService(session).process_ingest_event(ingest_event)
        if processed is None:
            return

        # Run the deterministic safety engine over the new telemetry point.
        engine = SafetyEngine(session)
        thresholds = await engine.load_thresholds(processed.context.organization_id)
        await engine.evaluate(processed.context, processed.sample, thresholds)

    def _mark_retry(self, event: OutboxEvent, exc: Exception) -> None:
        event.attempts += 1
        event.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        if event.attempts >= _MAX_ATTEMPTS:
            event.status = "dead_letter"
        else:
            event.status = "pending"
            backoff = min(2**event.attempts, 300)
            event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=backoff)

    def stop(self) -> None:
        self._stopping = True
