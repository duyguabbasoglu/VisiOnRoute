"""Assemble driver-score inputs from the database and compute the score."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.domain.driver_score import DriverScore, ScoredEvent, compute_driver_score
from visionroute.infrastructure.db.models.safety import SafetyEvent
from visionroute.infrastructure.db.models.telemetry import Trip


class DriverScoreService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def score_driver(
        self,
        tenant_id: uuid.UUID,
        driver_id: uuid.UUID,
        *,
        window_days: int = 90,
        now: datetime | None = None,
    ) -> DriverScore | None:
        now = now or datetime.now(UTC)
        since = now - timedelta(days=window_days)

        exposure = await self._db.execute(
            select(func.coalesce(func.sum(Trip.distance_km), 0.0)).where(
                Trip.organization_id == tenant_id,
                Trip.driver_id == driver_id,
                Trip.started_at >= since,
            )
        )
        exposure_km = float(exposure.scalar_one())

        rows = await self._db.execute(
            select(
                SafetyEvent.severity,
                SafetyEvent.confidence,
                SafetyEvent.data_quality,
                SafetyEvent.occurred_at,
                SafetyEvent.review_status,
            ).where(
                SafetyEvent.organization_id == tenant_id,
                SafetyEvent.driver_id == driver_id,
                SafetyEvent.occurred_at >= since,
            )
        )
        events = [
            ScoredEvent(
                severity=severity,
                confidence=float(confidence),
                data_quality=float(dq) if dq is not None else None,
                occurred_at=occurred,
                review_status=review_status,
            )
            for severity, confidence, dq, occurred, review_status in rows.all()
        ]
        return compute_driver_score(events, exposure_km, now=now)
