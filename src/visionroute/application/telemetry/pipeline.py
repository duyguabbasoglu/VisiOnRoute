"""One step of the telemetry pipeline, shared by the outbox worker and the
demo seed: an accepted ingest event becomes a telemetry point on a trip, and
the deterministic safety engine evaluates it."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.safety.engine import SafetyEngine
from visionroute.application.telemetry.service import ProcessedPoint, TelemetryService
from visionroute.infrastructure.db.models.ingestion import IngestEvent


async def process_accepted_ingest_event(
    session: AsyncSession, ingest_event: IngestEvent
) -> ProcessedPoint | None:
    """Process an ``accepted`` ingest event; other statuses are left alone so a
    replayed outbox event never processes the same point twice."""
    if ingest_event.status != "accepted":
        return None
    ingest_event.status = "processing"
    processed = await TelemetryService(session).process_ingest_event(ingest_event)
    if processed is None:
        return None
    engine = SafetyEngine(session)
    thresholds = await engine.load_thresholds(processed.context.organization_id)
    await engine.evaluate(processed.context, processed.sample, thresholds)
    return processed
