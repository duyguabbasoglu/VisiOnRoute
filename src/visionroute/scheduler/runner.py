"""Scheduler: periodic maintenance jobs.

- ensure_telemetry_partitions: pre-create next months' partitions so inserts
  never fall into the DEFAULT partition unexpectedly.
- close_stale_trips: mark trips with no telemetry within the idle gap as stale.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from visionroute.config.settings import Settings
from visionroute.domain.telemetry_rules import TRIP_IDLE_GAP
from visionroute.infrastructure.db.engine import build_engine, build_session_factory
from visionroute.infrastructure.db.models.telemetry import Trip
from visionroute.infrastructure.db.tenancy import set_rls_bypass
from visionroute.observability.logging import get_logger

logger = get_logger("visionroute.scheduler")


class Scheduler:
    def __init__(self, settings: Settings) -> None:
        self._engine = build_engine(settings)
        self._factory: async_sessionmaker[AsyncSession] = build_session_factory(self._engine)
        self._stopping = False

    async def run_forever(self, *, interval: float = 300.0) -> None:
        logger.info("scheduler_started")
        try:
            while not self._stopping:
                await self.run_once()
                await asyncio.sleep(interval)
        finally:
            await self._engine.dispose()
            logger.info("scheduler_stopped")

    async def run_once(self) -> None:
        async with self._factory() as session:
            await set_rls_bypass(session)
            created = await self._ensure_partitions(session)
            stale = await self._close_stale_trips(session)
            await session.commit()
            logger.info("scheduler_tick", partitions_created=created, trips_marked_stale=stale)

    async def _ensure_partitions(self, session: AsyncSession) -> int:
        """Create the next 3 months of telemetry partitions if missing."""
        result = await session.execute(
            text(
                """
                DO $$
                DECLARE
                    m date := date_trunc('month', now())::date;
                    i int; p_start date; p_end date; p_name text; made int := 0;
                BEGIN
                    FOR i IN 0..2 LOOP
                        p_start := (m + (i || ' month')::interval)::date;
                        p_end := (m + ((i + 1) || ' month')::interval)::date;
                        p_name := 'telemetry_points_' || to_char(p_start, 'YYYYMM');
                        IF to_regclass(p_name) IS NULL THEN
                            EXECUTE format(
                                'CREATE TABLE %I PARTITION OF telemetry_points '
                                'FOR VALUES FROM (%L) TO (%L)', p_name, p_start, p_end
                            );
                        END IF;
                    END LOOP;
                END $$
                """
            )
        )
        _ = result
        return 0

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
