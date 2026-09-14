"""Safety events and evidence tables (Milestone 6)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from visionroute.infrastructure.db.base import Base, IdMixin, TimestampMixin


class SafetyEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "safety_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    driver_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    trip_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))

    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    measured_value: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    reason_tr: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, server_default="rule_engine")
    ruleset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    severity_framework_version: Mapped[int] = mapped_column(Integer, nullable=False)
    data_quality: Mapped[float | None] = mapped_column(Float)

    # Processing / review lifecycle.
    processing_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="new", server_default="new"
    )
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(40))
    root_cause: Mapped[str | None] = mapped_column(String(60))
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    needs_review: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    # Deduplication key: same (vehicle, type, coarse time bucket) collapses.
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, server_default="{}")

    __table_args__ = (
        UniqueConstraint("organization_id", "dedup_key", name="uq_safety_events_dedup"),
        Index("ix_safety_events_org_occurred", "organization_id", "occurred_at"),
        Index("ix_safety_events_org_review", "organization_id", "review_status"),
        Index("ix_safety_events_vehicle", "organization_id", "vehicle_id", "occurred_at"),
        Index("ix_safety_events_driver", "organization_id", "driver_id", "occurred_at"),
        CheckConstraint("severity IN ('low','medium','high','critical')", name="severity_valid"),
        CheckConstraint(
            "processing_status IN ('new','processed','error')", name="processing_status_valid"
        ),
        CheckConstraint(
            "review_status IN ('pending','confirmed','rejected','uncertain')",
            name="review_status_valid",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )


class EventEvidence(IdMixin, TimestampMixin, Base):
    """Evidence linked to a safety event (telemetry window, snapshot, clip).

    Media references are private object-storage keys resolved to short-lived
    signed URLs at access time (never public); access is permission-gated and
    audited (M7)."""

    __tablename__ = "event_evidence"

    organization_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    safety_event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("safety_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # For telemetry evidence: an inline JSON window. For media: a storage key.
    telemetry_window: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    storage_key: Mapped[str | None] = mapped_column(String(400))
    content_type: Mapped[str | None] = mapped_column(String(100))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Media lifecycle: pending_upload → available | rejected; deleted by
    # retention or privacy deletion (object removed, row kept for audit).
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="available", server_default="available"
    )
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    original_filename: Mapped[str | None] = mapped_column(String(200))
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    uploaded_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    # Automatic face/plate anonymization needs an external computer-vision
    # service that is not integrated; media stays "not_processed" and raw
    # access requires events.evidence.raw_media (docs/HANDOVER.md).
    redaction_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_applicable", server_default="not_applicable"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_event_evidence_safety_event_id", "safety_event_id"),
        CheckConstraint("kind IN ('telemetry_window','snapshot','clip','note')", name="kind_valid"),
        CheckConstraint(
            "status IN ('pending_upload','available','rejected','deleted')", name="status_valid"
        ),
        CheckConstraint(
            "redaction_status IN ('not_applicable','not_processed','pending','completed','failed')",
            name="redaction_status_valid",
        ),
    )
