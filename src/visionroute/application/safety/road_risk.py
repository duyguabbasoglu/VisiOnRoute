"""Road-risk clustering: group repeated harsh events by location into
road-risk items (spec 2.4). Deterministic greedy spatial clustering.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.domain.safety import Severity
from visionroute.domain.telemetry_rules import haversine_km
from visionroute.infrastructure.db.models.roadrisk import RoadRisk
from visionroute.infrastructure.db.models.safety import SafetyEvent

# Events within this radius are treated as the same road-risk location.
_CLUSTER_RADIUS_KM = 0.15
# Minimum distinct events to raise a road risk.
_MIN_CLUSTER_SIZE = 3
# Only cluster events from the recent window.
_LOOKBACK_DAYS = 30

_SEVERITY_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


class RoadRiskService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def rebuild_for_tenant(self, tenant_id: uuid.UUID, *, now: datetime | None = None) -> int:
        """Recompute road risks from recent harsh-braking/cornering clusters.
        Returns the number of road-risk items written. Idempotent per run:
        replaces the tenant's event-cluster road risks."""
        now = now or datetime.now(UTC)
        since = now - timedelta(days=_LOOKBACK_DAYS)

        rows = await self._db.execute(
            select(
                SafetyEvent.latitude,
                SafetyEvent.longitude,
                SafetyEvent.severity,
                SafetyEvent.occurred_at,
            ).where(
                SafetyEvent.organization_id == tenant_id,
                SafetyEvent.event_type.in_(("harsh_braking", "harsh_cornering")),
                SafetyEvent.review_status != "rejected",
                SafetyEvent.occurred_at >= since,
                SafetyEvent.latitude.is_not(None),
            )
        )
        points = [
            (float(lat), float(lon), sev, occurred)
            for lat, lon, sev, occurred in rows.all()
            if lat is not None and lon is not None
        ]

        clusters = self._cluster(points)

        # Replace existing event-cluster road risks for this tenant.
        await self._db.execute(
            delete(RoadRisk).where(
                RoadRisk.organization_id == tenant_id,
                RoadRisk.source == "event_cluster",
            )
        )

        written = 0
        for cluster in clusters:
            if len(cluster) < _MIN_CLUSTER_SIZE:
                continue
            lat = sum(p[0] for p in cluster) / len(cluster)
            lon = sum(p[1] for p in cluster) / len(cluster)
            severity = self._peak_severity([p[2] for p in cluster])
            last_seen = max(p[3] for p in cluster)
            confidence = min(1.0, 0.4 + 0.1 * len(cluster))
            self._db.add(
                RoadRisk(
                    organization_id=tenant_id,
                    risk_type="repeated_harsh_events",
                    center_latitude=round(lat, 6),
                    center_longitude=round(lon, 6),
                    radius_m=_CLUSTER_RADIUS_KM * 1000,
                    observed_count=len(cluster),
                    inferred_severity=severity.value,
                    confidence=round(confidence, 3),
                    source="event_cluster",
                    source_reliability=0.7,
                    starts_at=min(p[3] for p in cluster),
                    last_observed_at=last_seen,
                    expires_at=now + timedelta(days=_LOOKBACK_DAYS),
                    details={"cluster_size": len(cluster)},
                )
            )
            written += 1
        return written

    def _cluster(
        self, points: list[tuple[float, float, str, datetime]]
    ) -> list[list[tuple[float, float, str, datetime]]]:
        clusters: list[list[tuple[float, float, str, datetime]]] = []
        for point in points:
            placed = False
            for cluster in clusters:
                cx = cluster[0][0]
                cy = cluster[0][1]
                if haversine_km(point[0], point[1], cx, cy) <= _CLUSTER_RADIUS_KM:
                    cluster.append(point)
                    placed = True
                    break
            if not placed:
                clusters.append([point])
        return clusters

    def _peak_severity(self, severities: list[str]) -> Severity:
        peak = Severity.LOW
        for s in severities:
            try:
                sev = Severity(s)
            except ValueError:
                continue
            if _SEVERITY_ORDER.index(sev) > _SEVERITY_ORDER.index(peak):
                peak = sev
        return peak

    async def list_risks(self, tenant_id: uuid.UUID) -> list[RoadRisk]:
        result = await self._db.execute(
            select(RoadRisk)
            .where(RoadRisk.organization_id == tenant_id)
            .order_by(RoadRisk.observed_count.desc())
        )
        return list(result.scalars())

    async def count(self, tenant_id: uuid.UUID) -> int:
        return int(
            (
                await self._db.execute(
                    select(func.count()).where(RoadRisk.organization_id == tenant_id)
                )
            ).scalar_one()
        )
