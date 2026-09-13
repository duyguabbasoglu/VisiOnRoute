"""Notification rules, in-app notifications, webhook endpoints/deliveries (M9)."""

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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from visionroute.infrastructure.db.base import Base, IdMixin, TimestampMixin


class NotificationRule(IdMixin, TimestampMixin, Base):
    __tablename__ = "notification_rules"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="severity_threshold")
    # For severity_threshold rules: minimum severity that triggers.
    min_severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="high", server_default="high"
    )
    channels: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default='["in_app"]')
    active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    __table_args__ = (
        Index("ix_notification_rules_org", "organization_id"),
        CheckConstraint(
            "kind IN ('severity_threshold','device_offline','geofence')", name="kind_valid"
        ),
        CheckConstraint(
            "min_severity IN ('low','medium','high','critical')", name="min_severity_valid"
        ),
    )


class Notification(IdMixin, Base):
    __tablename__ = "notifications"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("notification_rules.id", ondelete="SET NULL")
    )
    safety_event_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="info", server_default="info"
    )
    title_tr: Mapped[str] = mapped_column(String(300), nullable=False)
    body_tr: Mapped[str] = mapped_column(Text, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_notifications_org_created", "organization_id", "created_at"),
        CheckConstraint("level IN ('info','warning','critical')", name="level_valid"),
    )


class WebhookEndpoint(IdMixin, TimestampMixin, Base):
    """Outbound webhook target. The signing secret enables HMAC signatures on
    deliveries and is stored field-encrypted (see security/crypto.py)."""

    __tablename__ = "webhook_endpoints"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))
    # HMAC signing secret, field-encrypted (enc1:<key_id>:<token>); decrypted
    # only in memory at signing time and never returned after creation/rotation.
    secret_enc: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_webhook_endpoints_org", "organization_id"),)


class WebhookDelivery(IdMixin, Base):
    __tablename__ = "webhook_deliveries"

    organization_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    response_status: Mapped[int | None] = mapped_column(Integer)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_webhook_deliveries_pending", "status", "next_attempt_at"),
        Index("ix_webhook_deliveries_org", "organization_id"),
        CheckConstraint(
            "status IN ('pending','delivered','failed','dead_letter')", name="status_valid"
        ),
    )
