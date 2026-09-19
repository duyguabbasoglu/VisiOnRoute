"""Synthetic demo tenant seed. SYNTHETIC/DEMO ONLY.

Fills an organization with a small, clearly fictional fleet and pushes
simulator telemetry through the real pipeline: ``IngestionService`` stores and
deduplicates the envelopes, then the same processing step the outbox worker
runs turns them into telemetry points, trips and rule-engine safety events,
and road risks are rebuilt from the resulting clusters. Nothing is written
straight into dashboard tables, so every screen reads the data through its
normal API.

The caller (API layer) is responsible for the environment and permission
gates; this service only guarantees tenant scoping and idempotency.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.fleet.service import FleetService
from visionroute.application.ingestion.service import IngestionService
from visionroute.application.safety.road_risk import RoadRiskService
from visionroute.application.telemetry.pipeline import process_accepted_ingest_event
from visionroute.domain.synthetic_telemetry import (
    DATA_ORIGIN,
    ENVIRONMENT,
    ROUTE_NORTH,
    ROUTE_SOUTH,
    ROUTE_WEST,
    Incident,
    LatLon,
    TripPlan,
    build_trip_events,
)
from visionroute.infrastructure.db.models.fleet import Driver, Vehicle
from visionroute.infrastructure.db.models.ingestion import DataSource, IngestEvent
from visionroute.infrastructure.db.models.roadrisk import RoadRisk
from visionroute.infrastructure.db.models.safety import SafetyEvent
from visionroute.infrastructure.db.models.telemetry import TelemetryPoint, Trip

# The demo data source doubles as the "already seeded" marker.
DEMO_SOURCE_KEY = "visionroute-demo"
_PROVENANCE: dict[str, object] = {"data_origin": DATA_ORIGIN, "environment": ENVIRONMENT}

# Finished trips report every 30 s for ~35 min (~35 km each), so every
# assigned driver passes the driver-score minimum exposure (50 km). The live
# trip reports every 5 s and ends seconds before the seed.
_FINISHED_TRIP = (70, 30.0)
_LIVE_TRIP = (40, 5.0)


@dataclass(frozen=True)
class _DemoVehicle:
    external_id: str
    plate: str
    label: str
    route: tuple[LatLon, ...]
    cruise_kph: float
    # One tuple of incidents per trip: two finished trips, then the live one.
    trips: tuple[tuple[Incident, ...], ...]


# Fictional identifiers only: "DMO" plates and pseudonymous drivers.
_VEHICLES = (
    _DemoVehicle(
        "DMO-ARAC-01",
        "06 DMO 101",
        "Demo Kamyonet 1",
        ROUTE_NORTH,
        65.0,
        (
            (Incident("harsh_braking", 1200, 5.2), Incident("harsh_acceleration", 400, 4.2)),
            (Incident("harsh_braking", 1200, 6.1),),
            (Incident("harsh_braking", 1200, 7.4),),
        ),
    ),
    _DemoVehicle(
        "DMO-ARAC-02",
        "06 DMO 102",
        "Demo Servis Aracı 2",
        ROUTE_WEST,
        75.0,
        (
            (Incident("speeding", 1500, 132.0),),
            (Incident("harsh_braking", 2200, 4.6),),
            (Incident("speeding", 1500, 138.0),),
        ),
    ),
    _DemoVehicle(
        "DMO-ARAC-03",
        "06 DMO 103",
        "Demo Kamyon 3",
        ROUTE_SOUTH,
        65.0,
        (
            (Incident("harsh_cornering", 900, 4.6),),
            (Incident("harsh_cornering", 900, 5.3),),
            (Incident("harsh_cornering", 900, 6.4), Incident("harsh_braking", 1800, 8.0)),
        ),
    ),
)
# The last driver stays unassigned (a realistic reserve driver).
_DRIVERS = (
    ("DMO-SUR-01", "Demo Sürücü A"),
    ("DMO-SUR-02", "Demo Sürücü B"),
    ("DMO-SUR-03", "Demo Sürücü C"),
    ("DMO-SUR-04", "Demo Sürücü D"),
)


@dataclass(frozen=True)
class SeedSummary:
    vehicles: int
    drivers: int
    trips: int
    telemetry_points: int
    safety_events: int
    road_risks: int


@dataclass(frozen=True)
class SeedResult:
    created: bool
    summary: SeedSummary


class DemoSeedService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def is_seeded(self, tenant_id: uuid.UUID) -> bool:
        result = await self._db.execute(
            select(DataSource.id).where(
                DataSource.organization_id == tenant_id,
                DataSource.source_key == DEMO_SOURCE_KEY,
            )
        )
        return result.scalar_one_or_none() is not None

    async def seed(
        self, ctx: RequestContext, tenant_id: uuid.UUID, *, now: datetime | None = None
    ) -> SeedResult:
        """Seed once per tenant. Concurrent calls serialize on an advisory lock;
        every call after the first returns ``created=False`` without writing."""
        await self._db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"demo-seed:{tenant_id}"},
        )
        if await self.is_seeded(tenant_id):
            return SeedResult(created=False, summary=await self.summary(tenant_id))

        now = now or datetime.now(UTC)
        source = await self._create_fleet(ctx, tenant_id, now)

        # Deterministic per tenant, so a seed is reproducible in tests and logs.
        rng = random.Random(tenant_id.int)  # noqa: S311 — synthetic data, not security
        events = [
            event
            for plan in _trip_plans(now)
            for event in build_trip_events(plan, DEMO_SOURCE_KEY, rng, event_prefix="demo")
        ]
        await IngestionService(self._db).ingest_batch(tenant_id, source, events, now=now)
        await self._process_ingested(tenant_id, source.id)
        await RoadRiskService(self._db).rebuild_for_tenant(tenant_id, now=now)

        summary = await self.summary(tenant_id)
        await record_audit(
            self._db,
            ctx,
            action="demo_data.seeded",
            resource_type="organization",
            resource_id=str(tenant_id),
            data={**_PROVENANCE, "telemetry_points": summary.telemetry_points},
        )
        return SeedResult(created=True, summary=summary)

    async def summary(self, tenant_id: uuid.UUID) -> SeedSummary:
        async def count(model: type[object]) -> int:
            column = model.organization_id  # type: ignore[attr-defined]
            result = await self._db.execute(
                select(func.count()).select_from(model).where(column == tenant_id)
            )
            return int(result.scalar_one())

        return SeedSummary(
            vehicles=await count(Vehicle),
            drivers=await count(Driver),
            trips=await count(Trip),
            telemetry_points=await count(TelemetryPoint),
            safety_events=await count(SafetyEvent),
            road_risks=await count(RoadRisk),
        )

    async def _create_fleet(
        self, ctx: RequestContext, tenant_id: uuid.UUID, now: datetime
    ) -> DataSource:
        fleet_service = FleetService(self._db)
        fleet = await fleet_service.create_fleet(
            ctx, tenant_id, name="Demo Filosu (sentetik)", region="Ankara (kurgusal)"
        )
        vehicles: list[Vehicle] = []
        for spec in _VEHICLES:
            vehicle = await fleet_service.create_vehicle(
                ctx,
                tenant_id,
                external_id=spec.external_id,
                plate=spec.plate,
                label=spec.label,
                make=None,
                model=None,
                year=None,
                fleet_id=fleet.id,
            )
            vehicle.attributes = dict(_PROVENANCE)
            vehicles.append(vehicle)
        drivers = [
            await fleet_service.create_driver(
                ctx, tenant_id, external_id=external_id, full_name=name, phone=None
            )
            for external_id, name in _DRIVERS
        ]
        for driver, vehicle in zip(drivers, vehicles, strict=False):
            await fleet_service.assign_driver(
                ctx,
                tenant_id,
                driver_id=driver.id,
                vehicle_id=vehicle.id,
                started_at=now - timedelta(days=1),
            )

        source = DataSource(
            organization_id=tenant_id,
            name="Sentetik demo simülatörü",
            kind="simulator",
            source_key=DEMO_SOURCE_KEY,
            license="Sentetik veri — gerçek kanıt değildir",
            attribution="VisiOnRoute demo simülatörü (data_origin=synthetic, environment=demo)",
        )
        self._db.add(source)
        await self._db.flush()
        return source

    async def _process_ingested(self, tenant_id: uuid.UUID, source_id: uuid.UUID) -> None:
        """Run the worker's processing step now, in time order, so the
        dashboard is populated when the request returns. The outbox events the
        ingestion wrote stay queued; the worker finds them already processed
        and only emits the live-map notifications."""
        result = await self._db.execute(
            select(IngestEvent)
            .where(
                IngestEvent.organization_id == tenant_id,
                IngestEvent.data_source_id == source_id,
                IngestEvent.status == "accepted",
            )
            .order_by(IngestEvent.occurred_at, IngestEvent.external_event_id)
        )
        for ingest_event in result.scalars().all():
            await process_accepted_ingest_event(self._db, ingest_event)


def _trip_plans(now: datetime) -> list[TripPlan]:
    live_samples, live_seconds = _LIVE_TRIP
    plans: list[TripPlan] = []
    for index, spec in enumerate(_VEHICLES):
        # Two finished trips earlier today, then a live trip that ends seconds
        # ago (so the live map shows the vehicle as current).
        live_end = now - timedelta(seconds=5 + 20 * index)
        schedule = [
            (now - timedelta(hours=5, minutes=7 * index), *_FINISHED_TRIP),
            (now - timedelta(hours=2, minutes=30 + 5 * index), *_FINISHED_TRIP),
            (
                live_end - timedelta(seconds=live_seconds * (live_samples - 1)),
                live_samples,
                live_seconds,
            ),
        ]
        for (start, samples, seconds), incidents in zip(schedule, spec.trips, strict=True):
            plans.append(
                TripPlan(
                    vehicle_external_id=spec.external_id,
                    driver_external_id=_DRIVERS[index][0],
                    route=spec.route,
                    start=start,
                    samples=samples,
                    sample_seconds=seconds,
                    cruise_kph=spec.cruise_kph,
                    incidents=incidents,
                )
            )
    return plans
