"""Coaching actions assigned after reviewing safety events."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from visionroute.infrastructure.db.base import Base, IdMixin, TimestampMixin


class CoachingAction(IdMixin, TimestampMixin, Base):
    __tablename__ = "coaching_actions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    safety_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("safety_events.id", ondelete="SET NULL")
    )
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("drivers.id", ondelete="SET NULL")
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", server_default="open"
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(String(30))
    outcome_notes: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        CheckConstraint(
            "status IN ('open','in_progress','completed','canceled')", name="status_valid"
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN "
            "('coached','no_action_needed','escalated','driver_unavailable')",
            name="outcome_valid",
        ),
        Index("ix_coaching_actions_org_status", "organization_id", "status"),
        Index("ix_coaching_actions_org_assignee", "organization_id", "assignee_user_id"),
        Index("ix_coaching_actions_org_driver", "organization_id", "driver_id"),
        # At most one active coaching action per safety event (idempotent
        # assignment even under concurrent review requests).
        Index(
            "uq_coaching_actions_active_event",
            "organization_id",
            "safety_event_id",
            unique=True,
            postgresql_where=text(
                "safety_event_id IS NOT NULL AND status IN ('open','in_progress')"
            ),
        ),
    )
