"""Fleet domain tables (Milestone 3): fleets, vehicles, drivers, devices, cameras."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from visionroute.infrastructure.db.base import Base, IdMixin, TimestampMixin


class Fleet(IdMixin, TimestampMixin, Base):
    __tablename__ = "fleets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    region: Mapped[str | None] = mapped_column(String(120))

    __table_args__ = (
        Index("ix_fleets_organization_id", "organization_id"),
        UniqueConstraint("organization_id", "name", name="uq_fleets_org_name"),
    )


class VehicleGroup(IdMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_groups"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (
        Index("ix_vehicle_groups_organization_id", "organization_id"),
        UniqueConstraint("organization_id", "name", name="uq_vehicle_groups_org_name"),
    )


class Vehicle(IdMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    fleet_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fleets.id", ondelete="SET NULL")
    )
    vehicle_group_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicle_groups.id", ondelete="SET NULL")
    )
    # External id is how ingestion maps provider payloads to this vehicle.
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    plate: Mapped[str | None] = mapped_column(String(20))
    label: Mapped[str | None] = mapped_column(String(200))
    make: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80))
    year: Mapped[int | None] = mapped_column()
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    attributes: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    __table_args__ = (
        Index("ix_vehicles_organization_id", "organization_id"),
        Index("ix_vehicles_fleet_id", "fleet_id"),
        UniqueConstraint("organization_id", "external_id", name="uq_vehicles_org_external"),
        CheckConstraint("status IN ('active','inactive','maintenance')", name="status_valid"),
        CheckConstraint("year IS NULL OR (year BETWEEN 1950 AND 2100)", name="year_range"),
    )


class Driver(IdMixin, TimestampMixin, Base):
    __tablename__ = "drivers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Optional link to a self-service user account.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    license_number_enc: Mapped[str | None] = mapped_column(String(400))
    phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    # Set by KVKK erasure: identifiers are pseudonymized, the row is kept so
    # historical safety statistics stay consistent.
    erased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_drivers_organization_id", "organization_id"),
        UniqueConstraint("organization_id", "external_id", name="uq_drivers_org_external"),
        CheckConstraint("status IN ('active','inactive','erased')", name="status_valid"),
    )


class DriverAssignment(IdMixin, TimestampMixin, Base):
    """Time-bounded driver↔vehicle assignment. An open assignment has
    ``ended_at IS NULL``; a partial unique index enforces one open assignment
    per vehicle."""

    __tablename__ = "driver_assignments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    driver_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_driver_assignments_organization_id", "organization_id"),
        Index("ix_driver_assignments_vehicle_id", "vehicle_id"),
        Index("ix_driver_assignments_driver_id", "driver_id"),
        # At most one open (ended_at IS NULL) assignment per vehicle.
        Index(
            "uq_driver_assignments_open_vehicle",
            "vehicle_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )


class Device(IdMixin, TimestampMixin, Base):
    __tablename__ = "devices"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL")
    )
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="telematics")
    label: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_devices_organization_id", "organization_id"),
        Index("ix_devices_vehicle_id", "vehicle_id"),
        UniqueConstraint("organization_id", "external_id", name="uq_devices_org_external"),
        CheckConstraint("kind IN ('telematics','dashcam','sensor','gateway')", name="kind_valid"),
        CheckConstraint("status IN ('active','inactive','offline')", name="status_valid"),
    )


class Camera(IdMixin, TimestampMixin, Base):
    __tablename__ = "cameras"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL")
    )
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[str] = mapped_column(String(20), nullable=False, default="road")
    # RTSP/connection secrets are never stored here in cleartext; a reference
    # to Secrets Manager / encrypted metadata is stored instead (M4).
    connection_ref: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_cameras_organization_id", "organization_id"),
        UniqueConstraint("organization_id", "external_id", name="uq_cameras_org_external"),
        CheckConstraint("position IN ('road','driver','cabin','rear')", name="position_valid"),
        CheckConstraint(
            "status IN ('active','inactive','obstructed','offline')", name="status_valid"
        ),
    )
