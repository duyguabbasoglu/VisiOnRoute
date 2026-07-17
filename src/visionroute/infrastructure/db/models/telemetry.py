"""Trips and telemetry tables (Milestone 5).

``telemetry_points`` is range-partitioned by ``occurred_at`` (monthly) — the
partitioned parent and partitions are created in the migration via raw DDL,
because SQLAlchemy's DDL does not model declarative partitioning. The ORM
class below maps the parent for reads/writes; the composite primary key
includes ``occurred_at`` as required by PostgreSQL partitioning.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from visionroute.infrastructure.db.base import Base, IdMixin, TimestampMixin


class Trip(IdMixin, TimestampMixin, Base):
    __tablename__ = "trips"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("drivers.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_point_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    distance_km: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    point_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_speed_kph: Mapped[float | None] = mapped_column(Float)
    # Latest known position, for the live map (denormalized for fast reads).
    last_latitude: Mapped[float | None] = mapped_column(Float)
    last_longitude: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        Index("ix_trips_organization_id", "organization_id"),
        Index("ix_trips_vehicle_status", "vehicle_id", "status"),
        Index("ix_trips_org_status", "organization_id", "status"),
        CheckConstraint("status IN ('active','completed','stale')", name="status_valid"),
    )


class TripSegment(IdMixin, Base):
    """Coarse per-trip rollup (e.g. per few minutes) for playback/analytics."""

    __tablename__ = "trip_segments"

    organization_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    avg_speed_kph: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (Index("ix_trip_segments_trip_id", "trip_id"),)


class TelemetryPoint(Base):
    """Range-partitioned by occurred_at. PK includes the partition key."""

    __tablename__ = "telemetry_points"

    # PK must include the partition key (occurred_at); id makes it unique.
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    driver_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    speed_kph: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    acceleration_ms2: Mapped[float | None] = mapped_column(Float)
    lateral_acceleration_ms2: Mapped[float | None] = mapped_column(Float)
    # Data-quality score in [0,1]; low values penalize downstream scoring.
    quality: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")

    # The physical table (partitioned parent + partitions) is created by raw
    # DDL in the migration; this flag marks it as excluded from autogenerate.
    __table_args__ = ({"info": {"partitioned": True}},)


class TelemetryAggregate(IdMixin, Base):
    """Pre-aggregated per-vehicle-per-hour rollup for analytics dashboards."""

    __tablename__ = "telemetry_aggregates"

    organization_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    bucket_hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    point_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    distance_km: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    max_speed_kph: Mapped[float | None] = mapped_column(Float)
    avg_speed_kph: Mapped[float | None] = mapped_column(Float)
    data_quality_avg: Mapped[float | None] = mapped_column(Float)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_telemetry_aggregates_bucket",
            "organization_id",
            "vehicle_id",
            "bucket_hour",
            unique=True,
        ),
    )
