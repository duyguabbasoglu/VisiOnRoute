"""Road-risk and geofence tables (Milestone 7)."""

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
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from visionroute.infrastructure.db.base import Base, IdMixin, TimestampMixin


class RoadRisk(IdMixin, TimestampMixin, Base):
    """A road-segment risk item. Observed evidence, inferred risk, confidence,
    source freshness/reliability, and review status are kept distinct
    (spec 2.4)."""

    __tablename__ = "road_risks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    risk_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Cluster centroid (WGS84). Radius approximates the affected segment.
    center_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    center_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_m: Mapped[float] = mapped_column(Float, nullable=False, server_default="150")

    observed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    inferred_severity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, server_default="event_cluster")
    source_reliability: Mapped[float | None] = mapped_column(Float)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, server_default="{}")

    __table_args__ = (
        Index("ix_road_risks_org", "organization_id"),
        Index("ix_road_risks_org_type", "organization_id", "risk_type"),
        CheckConstraint(
            "inferred_severity IN ('low','medium','high','critical')",
            name="inferred_severity_valid",
        ),
        CheckConstraint(
            "review_status IN ('pending','confirmed','rejected')", name="review_status_valid"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )


class Geofence(IdMixin, TimestampMixin, Base):
    """Circular geofence for high-risk-zone rules and notifications."""

    __tablename__ = "geofences"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="high_risk", server_default="high_risk"
    )
    center_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    center_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_m: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    __table_args__ = (
        Index("ix_geofences_org", "organization_id"),
        CheckConstraint("kind IN ('high_risk','depot','restricted','custom')", name="kind_valid"),
        CheckConstraint("radius_m > 0 AND radius_m <= 100000", name="radius_range"),
    )
