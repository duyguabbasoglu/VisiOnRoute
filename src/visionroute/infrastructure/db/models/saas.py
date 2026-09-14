"""SaaS tables: plans, subscriptions, usage records (M10)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from visionroute.infrastructure.db.base import Base, IdMixin, TimestampMixin


class Plan(Base):
    """Subscription plan. ``-1`` means unlimited."""

    __tablename__ = "plans"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    name_tr: Mapped[str] = mapped_column(String(100), nullable=False)
    vehicle_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    user_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    features: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, server_default="{}")
    monthly_price_try: Mapped[float | None] = mapped_column(Float)


class Subscription(IdMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    plan_key: Mapped[str] = mapped_column(String(40), ForeignKey("plans.key"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="trial", server_default="trial"
    )
    billing_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual_invoice", server_default="manual_invoice"
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('trial','active','past_due','canceled')", name="status_valid"),
        CheckConstraint("billing_mode IN ('manual_invoice','stripe')", name="billing_mode_valid"),
    )


class UsageRecord(IdMixin, Base):
    __tablename__ = "usage_records"

    organization_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    metric: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # UTC day the value describes; snapshots upsert on (organization, metric, day).
    period_start: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        Index("ix_usage_records_org_metric", "organization_id", "metric", "recorded_at"),
        UniqueConstraint(
            "organization_id", "metric", "period_start", name="uq_usage_records_org_metric_period"
        ),
    )
