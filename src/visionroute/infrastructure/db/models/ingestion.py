"""Ingestion tables: data sources, credential metadata, raw event inbox."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from visionroute.infrastructure.db.base import Base, IdMixin, TimestampMixin


class DataSource(IdMixin, TimestampMixin, Base):
    """A configured inbound integration for a tenant."""

    __tablename__ = "data_sources"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="rest")
    # Slug used in the envelope's `source` field to attribute inbound events.
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    # Licensing/provenance for external feeds (DATA_SOURCE_REGISTER.md).
    license: Mapped[str | None] = mapped_column(String(200))
    attribution: Mapped[str | None] = mapped_column(String(300))
    refresh_interval_seconds: Mapped[int | None] = mapped_column(Integer)
    # Health signals.
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        Index("ix_data_sources_organization_id", "organization_id"),
        UniqueConstraint("organization_id", "source_key", name="uq_data_sources_org_key"),
        CheckConstraint(
            "kind IN ('rest','webhook','mqtt','kafka','s3_batch','csv','simulator')",
            name="kind_valid",
        ),
        CheckConstraint("status IN ('active','paused','disabled')", name="status_valid"),
    )


class DataSourceCredentialMetadata(TimestampMixin, Base):
    """Metadata *about* a credential — never the secret itself.

    The secret lives in the ``api_tokens`` table (hashed) or AWS Secrets
    Manager; here we store only a reference and rotation bookkeeping."""

    __tablename__ = "data_source_credentials_metadata"

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    secret_ref: Mapped[str | None] = mapped_column(String(300))
    api_token_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("api_tokens.id", ondelete="SET NULL")
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotation_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestEvent(IdMixin, Base):
    """Raw inbound event inbox. Deduplicated on (organization_id, source, event_id).

    ``status`` drives processing: accepted → processed by worker;
    quarantined → held with a reason; dead_letter → repeatedly failed."""

    __tablename__ = "ingest_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    vehicle_external_id: Mapped[str | None] = mapped_column(String(120))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    envelope: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted", server_default="accepted"
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(60))
    detail: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source",
            "external_event_id",
            name="uq_ingest_events_dedup",
        ),
        Index("ix_ingest_events_status", "status", "received_at"),
        Index("ix_ingest_events_org_received", "organization_id", "received_at"),
        Index("ix_ingest_events_vehicle", "organization_id", "vehicle_external_id"),
        CheckConstraint(
            "status IN ('accepted','processing','processed','quarantined','dead_letter')",
            name="status_valid",
        ),
    )
