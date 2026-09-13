"""Transactional e-mail outbox."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from visionroute.infrastructure.db.base import Base, IdMixin, TimestampMixin


class EmailMessage(IdMixin, TimestampMixin, Base):
    """A queued e-mail. ``context`` holds only non-secret template values;
    one-time links live encrypted in ``secret_context_enc`` and are wiped
    after delivery. Tenant rows are RLS-protected; platform-level messages
    (password reset) have no organization."""

    __tablename__ = "email_messages"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    template: Mapped[str] = mapped_column(String(60), nullable=False)
    locale: Mapped[str] = mapped_column(
        String(10), nullable=False, default="tr", server_default="tr"
    )
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    context: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    secret_context_enc: Mapped[str | None] = mapped_column(Text)
    related_type: Mapped[str | None] = mapped_column(String(40))
    related_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=8, server_default="8"
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','sending','sent','dead_letter','canceled')", name="status_valid"
        ),
        Index("ix_email_messages_due", "status", "next_attempt_at"),
        Index("ix_email_messages_org_created", "organization_id", "created_at"),
        Index("ix_email_messages_related", "related_type", "related_id"),
    )
