"""Live operations & trips: current vehicle positions, trip list/detail, trail."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from visionroute.api.deps import TenantSession, require_permission
from visionroute.api.errors import ForbiddenError, NotFoundError
from visionroute.application.context import RequestContext
from visionroute.domain.permissions import Permission
from visionroute.domain.telemetry_rules import STALE_FEED_AFTER
from visionroute.infrastructure.db.models.telemetry import TelemetryPoint, Trip

router = APIRouter(tags=["operations"])


def _tenant(ctx: RequestContext) -> uuid.UUID:
    if ctx.organization_id is None:  # pragma: no cover
        raise ForbiddenError
    return ctx.organization_id


class LiveVehicle(BaseModel):
    trip_id: str
    vehicle_id: str
    driver_id: str | None
    latitude: float | None
    longitude: float | None
    last_point_at: datetime | None
    max_speed_kph: float | None
    is_stale: bool


class TripOut(BaseModel):
    id: str
    vehicle_id: str
    driver_id: str | None
    status: str
    started_at: datetime
    ended_at: datetime | None
    last_point_at: datetime | None
    distance_km: float
    point_count: int
    max_speed_kph: float | None


class TrailPoint(BaseModel):
    occurred_at: datetime
    latitude: float
    longitude: float
    speed_kph: float | None
    quality: float


@router.get("/operations/live", response_model=list[LiveVehicle])
async def live_positions(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.TRIPS_READ)],
) -> list[LiveVehicle]:
    """Aktif seferlerin son bilinen konumları (canlı harita)."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(Trip)
        .where(Trip.organization_id == _tenant(ctx), Trip.status == "active")
        .order_by(Trip.last_point_at.desc().nullslast())
    )
    live: list[LiveVehicle] = []
    for trip in result.scalars():
        is_stale = trip.last_point_at is None or (now - trip.last_point_at) > STALE_FEED_AFTER
        live.append(
            LiveVehicle(
                trip_id=str(trip.id),
                vehicle_id=str(trip.vehicle_id),
                driver_id=str(trip.driver_id) if trip.driver_id else None,
                latitude=trip.last_latitude,
                longitude=trip.last_longitude,
                last_point_at=trip.last_point_at,
                max_speed_kph=trip.max_speed_kph,
                is_stale=is_stale,
            )
        )
    return live


@router.get("/trips", response_model=list[TripOut])
async def list_trips(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.TRIPS_READ)],
    vehicle_id: uuid.UUID | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TripOut]:
    stmt = select(Trip).where(Trip.organization_id == _tenant(ctx))
    if vehicle_id is not None:
        stmt = stmt.where(Trip.vehicle_id == vehicle_id)
    if status_filter is not None:
        stmt = stmt.where(Trip.status == status_filter)
    stmt = stmt.order_by(Trip.started_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return [_trip_out(t) for t in result.scalars()]


@router.get("/trips/{trip_id}", response_model=TripOut)
async def get_trip(
    trip_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.TRIPS_READ)],
) -> TripOut:
    trip = await db.get(Trip, trip_id)
    if trip is None or trip.organization_id != _tenant(ctx):
        raise NotFoundError("Sefer bulunamadı.")
    return _trip_out(trip)


@router.get("/trips/{trip_id}/trail", response_model=list[TrailPoint])
async def trip_trail(
    trip_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.TELEMETRY_READ)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 2000,
) -> list[TrailPoint]:
    trip = await db.get(Trip, trip_id)
    if trip is None or trip.organization_id != _tenant(ctx):
        raise NotFoundError("Sefer bulunamadı.")
    result = await db.execute(
        select(TelemetryPoint)
        .where(
            TelemetryPoint.organization_id == _tenant(ctx),
            TelemetryPoint.trip_id == trip_id,
        )
        .order_by(TelemetryPoint.occurred_at)
        .limit(limit)
    )
    return [
        TrailPoint(
            occurred_at=p.occurred_at,
            latitude=p.latitude,
            longitude=p.longitude,
            speed_kph=p.speed_kph,
            quality=p.quality,
        )
        for p in result.scalars()
    ]


def _trip_out(t: Trip) -> TripOut:
    return TripOut(
        id=str(t.id),
        vehicle_id=str(t.vehicle_id),
        driver_id=str(t.driver_id) if t.driver_id else None,
        status=t.status,
        started_at=t.started_at,
        ended_at=t.ended_at,
        last_point_at=t.last_point_at,
        distance_km=round(t.distance_km, 3),
        point_count=t.point_count,
        max_speed_kph=t.max_speed_kph,
    )
