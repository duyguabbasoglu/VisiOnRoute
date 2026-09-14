"""Scheduler: periodic maintenance jobs.

- ensure_telemetry_partitions: pre-create next months' partitions so inserts
  never fall into the DEFAULT partition unexpectedly.
- close_stale_trips: mark trips with no telemetry within the idle gap as stale.
- hourly maintenance: retention purge (raw telemetry and evidence media past
  the organization's retention, expired KVKK export archives, old e-mail logs,
  expired one-time tokens), idempotent usage snapshots for yesterday and today,
  and trial expiry.

Several scheduler replicas may run (rolling deploys, accidental scale-out); a
transaction-scoped PostgreSQL advisory lock guarantees only one executes a tick.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from visionroute.application.privacy.processor import PrivacyProcessor
from visionroute.application.saas.usage import UsageMeteringService
from visionroute.config.settings import Settings
from visionroute.domain.telemetry_rules import TRIP_IDLE_GAP
from visionroute.infrastructure.db.engine import build_engine, build_session_factory
from visionroute.infrastructure.db.models.telemetry import Trip
from visionroute.infrastructure.db.tenancy import set_rls_bypass
from visionroute.infrastructure.security.crypto import build_field_cipher
from visionroute.infrastructure.storage import build_object_storage
from visionroute.observability.logging import get_logger
from visionroute.observability.metrics import (
    RETENTION_PURGED,
    SCHEDULER_TICKS,
    TRIALS_EXPIRED,
    USAGE_SNAPSHOT_RECORDS,
)

logger = get_logger("visionroute.scheduler")

# Arbitrary, stable 64-bit key for pg_try_advisory_xact_lock ("VRSCHED").
SCHEDULER_LOCK_KEY = 0x5652534348454400
_PARTITION_MONTHS_AHEAD = 3
_MAINTENANCE_INTERVAL = timedelta(hours=1)


class Scheduler:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine = build_engine(settings)
        self._factory: async_sessionmaker[AsyncSession] = build_session_factory(self._engine)
        self._privacy = PrivacyProcessor(
            self._factory, build_object_storage(settings), build_field_cipher(settings)
        )
        self._usage = UsageMeteringService(self._factory)
        self._last_maintenance: datetime | None = None
        self._stopping = False

    async def run_forever(self, *, interval: float = 300.0) -> None:
        logger.info("scheduler_started")
        try:
            while not self._stopping:
                try:
                    await self.run_once()
                except Exception:
                    # A failed tick must not kill the loop; the next tick retries.
                    SCHEDULER_TICKS.labels("failed").inc()
                    logger.exception("scheduler_tick_failed")
                await asyncio.sleep(interval)
        finally:
            await self._engine.dispose()
            logger.info("scheduler_stopped")

    async def run_once(self) -> bool:
        """Run one tick. Returns False when another replica holds the lock."""
        async with self._factory() as session:
            await set_rls_bypass(session)
            acquired = (
                await session.execute(
                    text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": SCHEDULER_LOCK_KEY}
                )
            ).scalar_one()
            if not acquired:
                SCHEDULER_TICKS.labels("skipped").inc()
                logger.info("scheduler_tick_skipped", reason="lock_held")
                return False
            created = await self._ensure_partitions(session)
            stale = await self._close_stale_trips(session)
            now = datetime.now(UTC)
            if (
                self._last_maintenance is None
                or now - self._last_maintenance >= _MAINTENANCE_INTERVAL
            ):
                # Runs in its own transactions while this tick still holds the lock.
                await self._hourly_maintenance(now)
                self._last_maintenance = now
            await session.commit()
            SCHEDULER_TICKS.labels("ran").inc()
            logger.info("scheduler_tick", partitions_created=created, trips_marked_stale=stale)
            return True

    async def _hourly_maintenance(self, now: datetime) -> None:
        purged = await self._privacy.purge_expired(now=now)
        for category, count in purged.items():
            if count:
                RETENTION_PURGED.labels(category).inc(count)
        written = await self._usage.snapshot_day(now.date() - timedelta(days=1), now=now)
        written += await self._usage.snapshot_day(now.date(), now=now)
        USAGE_SNAPSHOT_RECORDS.inc(written)
        expired = await self._usage.expire_trials(now=now)
        TRIALS_EXPIRED.inc(expired)
        logger.info("scheduler_maintenance", usage_records=written, trials_expired=expired)

    async def _ensure_partitions(self, session: AsyncSession) -> int:
        """Create the next months of telemetry partitions if missing."""
        today = datetime.now(UTC).date()
        created = 0
        for offset in range(_PARTITION_MONTHS_AHEAD):
            start = _add_months(today.replace(day=1), offset)
            end = _add_months(start, 1)
            name = f"telemetry_points_{start:%Y%m}"
            exists = (
                await session.execute(text("SELECT to_regclass(:name)"), {"name": name})
            ).scalar_one()
            if exists is not None:
                continue
            # Identifier/literals are quoted by PostgreSQL's format(), never
            # by string interpolation.
            ddl = (
                await session.execute(
                    text(
                        "SELECT format('CREATE TABLE %I PARTITION OF telemetry_points "
                        "FOR VALUES FROM (%L) TO (%L)', :name, :start, :end)"
                    ),
                    {"name": name, "start": start.isoformat(), "end": end.isoformat()},
                )
            ).scalar_one()
            await session.execute(text(ddl))
            created += 1
        return created

    async def _close_stale_trips(self, session: AsyncSession) -> int:
        cutoff = datetime.now(UTC) - TRIP_IDLE_GAP
        result = await session.execute(
            update(Trip)
            .where(Trip.status == "active", Trip.last_point_at < cutoff)
            .values(status="stale")
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    def stop(self) -> None:
        self._stopping = True


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    return day.replace(year=day.year + month_index // 12, month=month_index % 12 + 1)
