"""Outbox worker (ADR-0002).

Consumes ``outbox_events`` with FOR UPDATE SKIP LOCKED so multiple worker
processes run safely in parallel. Each event is dispatched to a handler;
failures back off exponentially and land in ``dead_letter`` after max attempts.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from visionroute.application.safety.engine import SafetyEngine
from visionroute.application.telemetry.service import TelemetryService
from visionroute.config.settings import Settings
from visionroute.infrastructure.db.engine import build_engine, build_session_factory
from visionroute.infrastructure.db.models.ingestion import IngestEvent
from visionroute.infrastructure.db.models.system import OutboxEvent
from visionroute.infrastructure.db.tenancy import set_rls_bypass
from visionroute.observability.logging import get_logger

logger = get_logger("visionroute.worker")

_MAX_ATTEMPTS = 8
_BATCH = 50


class Worker:
    def __init__(self, settings: Settings) -> None:
        self._engine = build_engine(settings)
        self._factory: async_sessionmaker[AsyncSession] = build_session_factory(self._engine)
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
        async with self._factory() as session:
            await set_rls_bypass(session)
            events = await self._claim(session)
            handled = 0
            for event in events:
                try:
                    await self._dispatch(session, event)
                    event.status = "done"
                    event.processed_at = datetime.now(UTC)
                    handled += 1
                except Exception as exc:
                    await self._mark_retry(event, exc)
                    logger.warning(
                        "outbox_event_failed",
                        event_type=event.event_type,
                        attempts=event.attempts,
                        error=str(exc),
                    )
            await session.commit()
            return handled

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
        # Other event types (notifications, analytics) are handled in later
        # milestones; unknown types are acknowledged as done (no-op) so they
        # do not clog the queue.

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

    async def _mark_retry(self, event: OutboxEvent, exc: Exception) -> None:
        event.attempts += 1
        event.last_error = str(exc)[:2000]
        if event.attempts >= _MAX_ATTEMPTS:
            event.status = "dead_letter"
        else:
            event.status = "pending"
            backoff = min(2**event.attempts, 300)
            event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=backoff)

    def stop(self) -> None:
        self._stopping = True
