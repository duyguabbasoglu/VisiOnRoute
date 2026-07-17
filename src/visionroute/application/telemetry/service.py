"""Telemetry processing: turn accepted ingest events into telemetry points and
maintain the trip lifecycle. Invoked by the worker under an RLS-bypass session
(it operates across the accepted-event backlog for one tenant at a time).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.safety.engine import PointContext as SafetyPointContext
from visionroute.domain.ids import uuid7
from visionroute.domain.ingestion import EventEnvelope, TelemetryPayload
from visionroute.domain.safety import TelemetrySample as SafetySample
from visionroute.domain.telemetry_rules import (
    TRIP_IDLE_GAP,
    data_quality,
    haversine_km,
    implausible_jump_kph,
)
from visionroute.infrastructure.db.models.fleet import Vehicle
from visionroute.infrastructure.db.models.ingestion import IngestEvent
from visionroute.infrastructure.db.models.telemetry import TelemetryPoint, Trip


@dataclass(frozen=True)
class ProcessedPoint:
    telemetry_point_id: uuid.UUID
    trip_id: uuid.UUID
    quality: float
    gps_anomaly: bool
    context: SafetyPointContext
    sample: SafetySample


class TelemetryService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def process_ingest_event(self, event: IngestEvent) -> ProcessedPoint | None:
        """Process one accepted ingest event. Returns None for non-telemetry
        events (which are stored but produce no telemetry point)."""
        if event.event_type != "telemetry.position":
            event.status = "processed"
            event.processed_at = datetime.now(UTC)
            return None

        envelope = EventEnvelope.model_validate(event.envelope)
        payload = TelemetryPayload.model_validate(envelope.payload)

        vehicle = await self._resolve_vehicle(event.organization_id, envelope.vehicle_external_id)
        if vehicle is None:
            # Should not happen (ingestion validated it), but fail safe.
            event.status = "quarantined"
            event.rejection_reason = "unknown_vehicle"
            return None

        trip = await self._active_trip(event.organization_id, vehicle.id, envelope.occurred_at)

        gps_anomaly = False
        distance = 0.0
        if (
            trip.last_latitude is not None
            and trip.last_longitude is not None
            and trip.last_point_at is not None
        ):
            distance = haversine_km(
                trip.last_latitude, trip.last_longitude, payload.latitude, payload.longitude
            )
            seconds = (envelope.occurred_at - trip.last_point_at).total_seconds()
            if implausible_jump_kph(distance, seconds) is not None:
                gps_anomaly = True
                distance = 0.0  # do not accumulate an implausible jump

        quality = data_quality(
            gps_hdop=payload.gps_hdop,
            satellites=payload.satellites,
            has_speed=payload.speed_kph is not None,
        )
        if gps_anomaly:
            quality = min(quality, 0.3)

        point_id = uuid7()
        point = TelemetryPoint(
            id=point_id,
            occurred_at=envelope.occurred_at,
            organization_id=event.organization_id,
            trip_id=trip.id,
            vehicle_id=vehicle.id,
            driver_id=trip.driver_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            speed_kph=payload.speed_kph,
            heading_deg=payload.heading_deg,
            acceleration_ms2=payload.acceleration_ms2,
            lateral_acceleration_ms2=payload.lateral_acceleration_ms2,
            quality=quality,
        )
        self._db.add(point)

        # Update denormalized trip head.
        trip.distance_km += distance
        trip.point_count += 1
        trip.last_point_at = envelope.occurred_at
        trip.last_latitude = payload.latitude
        trip.last_longitude = payload.longitude
        if payload.speed_kph is not None:
            trip.max_speed_kph = max(trip.max_speed_kph or 0.0, payload.speed_kph)

        event.status = "processed"
        event.processed_at = datetime.now(UTC)
        return ProcessedPoint(
            telemetry_point_id=point_id,
            trip_id=trip.id,
            quality=quality,
            gps_anomaly=gps_anomaly,
            context=SafetyPointContext(
                organization_id=event.organization_id,
                vehicle_id=vehicle.id,
                driver_id=trip.driver_id,
                trip_id=trip.id,
                occurred_at=envelope.occurred_at,
                latitude=payload.latitude,
                longitude=payload.longitude,
            ),
            sample=SafetySample(
                speed_kph=payload.speed_kph,
                acceleration_ms2=payload.acceleration_ms2,
                lateral_acceleration_ms2=payload.lateral_acceleration_ms2,
                quality=quality,
            ),
        )

    async def _resolve_vehicle(self, tenant_id: uuid.UUID, external_id: str) -> Vehicle | None:
        result = await self._db.execute(
            select(Vehicle).where(
                Vehicle.organization_id == tenant_id, Vehicle.external_id == external_id
            )
        )
        return result.scalar_one_or_none()

    async def _active_trip(
        self, tenant_id: uuid.UUID, vehicle_id: uuid.UUID, occurred_at: datetime
    ) -> Trip:
        """Return the vehicle's open trip, or start a new one. An idle gap
        greater than TRIP_IDLE_GAP closes the previous trip and opens a new one."""
        result = await self._db.execute(
            select(Trip)
            .where(
                Trip.organization_id == tenant_id,
                Trip.vehicle_id == vehicle_id,
                Trip.status == "active",
            )
            .order_by(Trip.started_at.desc())
            .limit(1)
        )
        trip = result.scalar_one_or_none()

        if trip is not None and trip.last_point_at is not None:
            gap = occurred_at - trip.last_point_at
            if gap > TRIP_IDLE_GAP:
                trip.status = "completed"
                trip.ended_at = trip.last_point_at
                trip = None

        if trip is None:
            driver_id = await self._current_driver(tenant_id, vehicle_id)
            trip = Trip(
                organization_id=tenant_id,
                vehicle_id=vehicle_id,
                driver_id=driver_id,
                status="active",
                started_at=occurred_at,
            )
            self._db.add(trip)
            await self._db.flush()
        return trip

    async def _current_driver(
        self, tenant_id: uuid.UUID, vehicle_id: uuid.UUID
    ) -> uuid.UUID | None:
        from visionroute.infrastructure.db.models.fleet import DriverAssignment

        result = await self._db.execute(
            select(DriverAssignment.driver_id)
            .where(
                DriverAssignment.organization_id == tenant_id,
                DriverAssignment.vehicle_id == vehicle_id,
                DriverAssignment.ended_at.is_(None),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
