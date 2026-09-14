"""KVKK data-subject requests (export / erasure)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from visionroute.infrastructure.db.base import Base, IdMixin, TimestampMixin


class PrivacyRequest(IdMixin, TimestampMixin, Base):
    __tablename__ = "privacy_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Not a foreign key: the request record must outlive the subject's data.
    subject_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Next eligible processing time; doubles as the lease while processing.
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("now()")
    )
    artifact_key: Mapped[str | None] = mapped_column(String(400))
    artifact_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    artifact_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Counts only (e.g. {"trips": 12}); never personal data.
    result: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa_text("'{}'::jsonb")
    )
    error_code: Mapped[str | None] = mapped_column(String(60))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("kind IN ('export','erasure')", name="kind_valid"),
        CheckConstraint("subject_type IN ('driver','user')", name="subject_type_valid"),
        CheckConstraint(
            "status IN ('pending','processing','completed','failed','canceled')",
            name="status_valid",
        ),
        Index("ix_privacy_requests_org_created", "organization_id", "created_at"),
        Index("ix_privacy_requests_due", "status", "next_attempt_at"),
        # One active request per (organization, kind, subject).
        Index(
            "uq_privacy_requests_active_subject",
            "organization_id",
            "kind",
            "subject_type",
            "subject_id",
            unique=True,
            postgresql_where=sa_text("status IN ('pending','processing')"),
        ),
    )
