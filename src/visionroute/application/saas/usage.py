"""Daily usage metering and trial expiry.

Snapshots are idempotent upserts keyed by (organization, metric, day), so the
scheduler can recompute today and yesterday every maintenance run. Activity
metrics count rows inside the UTC day; gauge metrics record the value at the
time of the snapshot (the last snapshot of a day wins).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import InstrumentedAttribute

from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.domain.ids import uuid7
from visionroute.domain.usage import USAGE_METRICS, day_window
from visionroute.infrastructure.db.models.fleet import Vehicle
from visionroute.infrastructure.db.models.identity import Membership, Organization
from visionroute.infrastructure.db.models.ingestion import IngestEvent
from visionroute.infrastructure.db.models.saas import Subscription, UsageRecord
from visionroute.infrastructure.db.models.safety import EventEvidence, SafetyEvent
from visionroute.infrastructure.db.models.telemetry import TelemetryPoint
from visionroute.infrastructure.db.tenancy import set_rls_bypass

USAGE_UNIQUE_CONSTRAINT = "uq_usage_records_org_metric_period"


async def current_usage(session: AsyncSession, organization_id: uuid.UUID) -> dict[str, int]:
    """Point-in-time values used for limits and the subscription page."""

    async def scalar(stmt: object) -> int:
        return int((await session.execute(stmt)).scalar_one() or 0)  # type: ignore[call-overload]

    return {
        "vehicles": await scalar(
            select(func.count())
            .select_from(Vehicle)
            .where(Vehicle.organization_id == organization_id)
        ),
        "active_members": await scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.organization_id == organization_id, Membership.status == "active")
        ),
        "evidence_storage_bytes": await scalar(
            select(func.coalesce(func.sum(EventEvidence.size_bytes), 0)).where(
                EventEvidence.organization_id == organization_id,
                EventEvidence.status == "available",
            )
        ),
    }


async def _activity(session: AsyncSession, organization_id: uuid.UUID, day: date) -> dict[str, int]:
    window = day_window(day)

    async def count(
        org_column: InstrumentedAttribute[uuid.UUID], time_column: InstrumentedAttribute[datetime]
    ) -> int:
        stmt = select(func.count()).where(
            org_column == organization_id,
            time_column >= window.start,
            time_column < window.end,
        )
        return int((await session.execute(stmt)).scalar_one() or 0)

    return {
        "ingest_events": await count(IngestEvent.organization_id, IngestEvent.received_at),
        "telemetry_points": await count(TelemetryPoint.organization_id, TelemetryPoint.occurred_at),
        "safety_events": await count(SafetyEvent.organization_id, SafetyEvent.occurred_at),
    }


async def usage_series(
    session: AsyncSession, organization_id: uuid.UUID, *, days: int, today: date
) -> dict[str, list[tuple[date, float]]]:
    since = today - timedelta(days=days - 1)
    rows = await session.execute(
        select(UsageRecord.metric, UsageRecord.period_start, UsageRecord.value)
        .where(
            UsageRecord.organization_id == organization_id,
            UsageRecord.period_start >= since,
            UsageRecord.period_start <= today,
        )
        .order_by(UsageRecord.period_start)
    )
    series: dict[str, list[tuple[date, float]]] = {metric: [] for metric in USAGE_METRICS}
    for metric, period_start, value in rows:
        if metric in series:
            series[metric].append((period_start, float(value)))
    return series


class UsageMeteringService:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def snapshot_day(
        self,
        day: date,
        *,
        now: datetime | None = None,
        organization_ids: list[uuid.UUID] | None = None,
    ) -> int:
        now = now or datetime.now(UTC)
        async with self._factory() as session:
            await set_rls_bypass(session)
            stmt = select(Organization.id)
            if organization_ids is not None:
                stmt = stmt.where(Organization.id.in_(organization_ids))
            org_ids = list((await session.execute(stmt)).scalars())

        written = 0
        for org_id in org_ids:
            async with self._factory() as session:
                await set_rls_bypass(session)
                values = {
                    **await current_usage(session, org_id),
                    **await _activity(session, org_id, day),
                }
                for metric, value in values.items():
                    insert = pg_insert(UsageRecord).values(
                        id=uuid7(),
                        organization_id=org_id,
                        metric=metric,
                        value=float(value),
                        period_start=day,
                        recorded_at=now,
                    )
                    await session.execute(
                        insert.on_conflict_do_update(
                            constraint=USAGE_UNIQUE_CONSTRAINT,
                            set_={"value": insert.excluded.value, "recorded_at": now},
                        )
                    )
                    written += 1
                await session.commit()
        return written

    async def expire_trials(self, *, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        async with self._factory() as session:
            await set_rls_bypass(session)
            rows = await session.execute(
                select(Subscription)
                .where(Subscription.status == "trial", Subscription.trial_ends_at <= now)
                .with_for_update(skip_locked=True)
            )
            expired = 0
            for subscription in rows.scalars():
                subscription.status = "past_due"
                expired += 1
                await record_audit(
                    session,
                    RequestContext(
                        user_id=None,
                        organization_id=subscription.organization_id,
                        role=None,
                        is_platform_admin=False,
                        actor_label="system:billing",
                    ),
                    action="subscription.trial_expired",
                    resource_type="subscription",
                    resource_id=str(subscription.id),
                    data={"plan_key": subscription.plan_key},
                )
            await session.commit()
        return expired
