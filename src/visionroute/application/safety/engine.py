"""Safety-event engine: evaluate a telemetry point, dedup, persist with evidence.

Called by the worker right after a telemetry point is created. Deduplication
collapses repeated hits of the same (vehicle, type) that occur within ±30
seconds of an existing event into that event (occurrence_count is
incremented). A sliding window is used instead of fixed clock buckets, which
split hits seconds apart whenever they straddled a bucket boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.outbox import publish_event
from visionroute.domain.safety import (
    RULESET_VERSION,
    SEVERITY_FRAMEWORK_VERSION,
    RuleHit,
    TelemetrySample,
    Thresholds,
    evaluate_point,
)
from visionroute.infrastructure.db.models.safety import EventEvidence, SafetyEvent

# Hits of the same type for the same vehicle within this window are one event.
_DEDUP_WINDOW = timedelta(seconds=30)


@dataclass(frozen=True)
class PointContext:
    organization_id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID | None
    trip_id: uuid.UUID | None
    occurred_at: datetime
    latitude: float | None
    longitude: float | None
    # Provenance copied from the telemetry payload (e.g. "synthetic"/"demo"),
    # so events derived from simulator data stay marked as such.
    data_origin: str | None = None
    environment: str | None = None


class SafetyEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def evaluate(
        self, ctx: PointContext, sample: TelemetrySample, thresholds: Thresholds
    ) -> list[uuid.UUID]:
        """Evaluate one point; return ids of created-or-updated safety events."""
        hits = evaluate_point(sample, thresholds)
        event_ids: list[uuid.UUID] = []
        for hit in hits:
            event_id = await self._persist(ctx, hit, sample)
            if event_id is not None:
                event_ids.append(event_id)
        return event_ids

    async def _persist(
        self, ctx: PointContext, hit: RuleHit, sample: TelemetrySample
    ) -> uuid.UUID | None:
        # Serialize writers for the same (vehicle, event type) until the
        # transaction ends, so the window lookup and the insert are atomic
        # even when several workers process the same vehicle concurrently.
        await self._db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"safety-dedup:{ctx.vehicle_id}:{hit.event_type.value}"},
        )
        existing = (
            await self._db.execute(
                select(SafetyEvent)
                .where(
                    SafetyEvent.organization_id == ctx.organization_id,
                    SafetyEvent.vehicle_id == ctx.vehicle_id,
                    SafetyEvent.event_type == hit.event_type.value,
                    SafetyEvent.occurred_at >= ctx.occurred_at - _DEDUP_WINDOW,
                    SafetyEvent.occurred_at <= ctx.occurred_at + _DEDUP_WINDOW,
                )
                .order_by(SafetyEvent.occurred_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.occurrence_count += 1
            return existing.id

        # Exact-instant key: identical replays of the same sample still collapse
        # through the unique constraint instead of failing.
        dedup_key = (
            f"{ctx.vehicle_id}:{hit.event_type.value}:{int(ctx.occurred_at.timestamp() * 1000)}"
        )
        new_id = uuid.uuid4()
        stmt = (
            pg_insert(SafetyEvent)
            .values(
                id=new_id,
                organization_id=ctx.organization_id,
                vehicle_id=ctx.vehicle_id,
                driver_id=ctx.driver_id,
                trip_id=ctx.trip_id,
                event_type=hit.event_type.value,
                severity=hit.severity.value,
                confidence=hit.confidence,
                occurred_at=ctx.occurred_at,
                latitude=ctx.latitude,
                longitude=ctx.longitude,
                measured_value=hit.measured_value,
                threshold=hit.threshold,
                reason_tr=hit.reason_tr,
                ruleset_version=RULESET_VERSION,
                severity_framework_version=SEVERITY_FRAMEWORK_VERSION,
                data_quality=sample.quality,
                needs_review=hit.needs_review,
                dedup_key=dedup_key,
                details=_details(ctx, hit),
            )
            .on_conflict_do_update(
                index_elements=["organization_id", "dedup_key"],
                set_={"occurrence_count": SafetyEvent.occurrence_count + 1},
            )
            .returning(SafetyEvent.id)
        )
        result = await self._db.execute(stmt)
        event_id = result.scalar_one()

        # Only the first occurrence (the freshly inserted row) gets evidence and
        # an outbox notification; duplicates just bump the counter.
        if event_id != new_id:
            return event_id

        self._db.add(
            EventEvidence(
                organization_id=ctx.organization_id,
                safety_event_id=event_id,
                kind="telemetry_window",
                telemetry_window={
                    "speed_kph": sample.speed_kph,
                    "acceleration_ms2": sample.acceleration_ms2,
                    "lateral_acceleration_ms2": sample.lateral_acceleration_ms2,
                    "quality": sample.quality,
                    "measured_value": hit.measured_value,
                    "threshold": hit.threshold,
                },
                captured_at=ctx.occurred_at,
            )
        )
        await publish_event(
            self._db,
            aggregate_type="safety_event",
            aggregate_id=str(event_id),
            event_type="safety.event_created",
            payload={
                "organization_id": str(ctx.organization_id),
                "safety_event_id": str(event_id),
                "event_type": hit.event_type.value,
                "severity": hit.severity.value,
            },
        )
        return event_id

    async def load_thresholds(self, organization_id: uuid.UUID) -> Thresholds:
        from visionroute.infrastructure.db.models.identity import OrganizationSettings

        result = await self._db.execute(
            select(OrganizationSettings.risk_thresholds).where(
                OrganizationSettings.organization_id == organization_id
            )
        )
        overrides = result.scalar_one_or_none()
        return Thresholds.from_overrides(overrides)


def _details(ctx: PointContext, hit: RuleHit) -> dict[str, object]:
    details: dict[str, object] = {"extra": hit.extra} if hit.extra else {}
    if ctx.data_origin is not None:
        details["data_origin"] = ctx.data_origin
    if ctx.environment is not None:
        details["environment"] = ctx.environment
    return details
