"""Fleet domain use cases: vehicles, drivers, devices, cameras, assignments.

All methods take a tenant id and only ever touch rows for that tenant; RLS is
the backstop. Uniqueness violations are translated to Turkish conflict errors.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.errors import DomainConflictError, DomainNotFoundError
from visionroute.application.saas.service import SubscriptionService
from visionroute.infrastructure.db.models.fleet import (
    Camera,
    Device,
    Driver,
    DriverAssignment,
    Fleet,
    Vehicle,
)


@dataclass(frozen=True)
class Page:
    limit: int
    offset: int


class FleetService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    # ------------------------------------------------------------- vehicles

    async def create_vehicle(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        *,
        external_id: str,
        plate: str | None,
        label: str | None,
        make: str | None,
        model: str | None,
        year: int | None,
        fleet_id: uuid.UUID | None,
    ) -> Vehicle:
        await SubscriptionService(self._db).enforce_vehicle_limit(tenant_id)
        if fleet_id is not None:
            await self._require(Fleet, tenant_id, fleet_id, "Filo bulunamadı.")
        vehicle = Vehicle(
            organization_id=tenant_id,
            external_id=external_id.strip(),
            plate=plate,
            label=label,
            make=make,
            model=model,
            year=year,
            fleet_id=fleet_id,
        )
        self._db.add(vehicle)
        await self._flush_unique("Bu dış kimliğe (external_id) sahip bir araç zaten var.")
        await record_audit(
            self._db,
            ctx,
            action="vehicle.created",
            resource_type="vehicle",
            resource_id=str(vehicle.id),
            data={"external_id": vehicle.external_id},
        )
        return vehicle

    async def list_vehicles(
        self, tenant_id: uuid.UUID, page: Page, *, fleet_id: uuid.UUID | None = None
    ) -> tuple[list[Vehicle], int]:
        stmt: Select[tuple[Vehicle]] = select(Vehicle).where(Vehicle.organization_id == tenant_id)
        if fleet_id is not None:
            stmt = stmt.where(Vehicle.fleet_id == fleet_id)
        return await self._paginate(stmt.order_by(Vehicle.created_at.desc()), page)

    async def get_vehicle(self, tenant_id: uuid.UUID, vehicle_id: uuid.UUID) -> Vehicle:
        return await self._require(Vehicle, tenant_id, vehicle_id, "Araç bulunamadı.")

    async def update_vehicle(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        *,
        changes: dict[str, object],
    ) -> Vehicle:
        vehicle = await self.get_vehicle(tenant_id, vehicle_id)
        for field, value in changes.items():
            setattr(vehicle, field, value)
        await self._flush_unique("Araç güncellenirken benzersizlik çakışması oluştu.")
        await record_audit(
            self._db,
            ctx,
            action="vehicle.updated",
            resource_type="vehicle",
            resource_id=str(vehicle.id),
            data={"fields": sorted(changes)},
        )
        return vehicle

    # ------------------------------------------------------------- drivers

    async def create_driver(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        *,
        external_id: str,
        full_name: str,
        phone: str | None,
    ) -> Driver:
        driver = Driver(
            organization_id=tenant_id,
            external_id=external_id.strip(),
            full_name=full_name,
            phone=phone,
        )
        self._db.add(driver)
        await self._flush_unique("Bu dış kimliğe (external_id) sahip bir sürücü zaten var.")
        await record_audit(
            self._db,
            ctx,
            action="driver.created",
            resource_type="driver",
            resource_id=str(driver.id),
            data={"external_id": driver.external_id},
        )
        return driver

    async def list_drivers(self, tenant_id: uuid.UUID, page: Page) -> tuple[list[Driver], int]:
        stmt = select(Driver).where(Driver.organization_id == tenant_id).order_by(Driver.full_name)
        return await self._paginate(stmt, page)

    async def get_driver(self, tenant_id: uuid.UUID, driver_id: uuid.UUID) -> Driver:
        return await self._require(Driver, tenant_id, driver_id, "Sürücü bulunamadı.")

    # ------------------------------------------------------------- devices

    async def create_device(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        *,
        external_id: str,
        kind: str,
        label: str | None,
        vehicle_id: uuid.UUID | None,
    ) -> Device:
        if vehicle_id is not None:
            await self._require(Vehicle, tenant_id, vehicle_id, "Araç bulunamadı.")
        device = Device(
            organization_id=tenant_id,
            external_id=external_id.strip(),
            kind=kind,
            label=label,
            vehicle_id=vehicle_id,
        )
        self._db.add(device)
        await self._flush_unique("Bu dış kimliğe (external_id) sahip bir cihaz zaten var.")
        await record_audit(
            self._db,
            ctx,
            action="device.created",
            resource_type="device",
            resource_id=str(device.id),
            data={"external_id": device.external_id, "kind": device.kind},
        )
        return device

    async def list_devices(self, tenant_id: uuid.UUID, page: Page) -> tuple[list[Device], int]:
        stmt = (
            select(Device)
            .where(Device.organization_id == tenant_id)
            .order_by(Device.created_at.desc())
        )
        return await self._paginate(stmt, page)

    # ------------------------------------------------------------- assignments

    async def assign_driver(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        *,
        driver_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        started_at: datetime | None = None,
    ) -> DriverAssignment:
        await self._require(Driver, tenant_id, driver_id, "Sürücü bulunamadı.")
        await self._require(Vehicle, tenant_id, vehicle_id, "Araç bulunamadı.")
        assignment = DriverAssignment(
            organization_id=tenant_id,
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            started_at=started_at or datetime.now(UTC),
        )
        self._db.add(assignment)
        await self._flush_unique(
            "Bu araç için zaten açık bir sürücü ataması var. Önce mevcut atamayı kapatın."
        )
        await record_audit(
            self._db,
            ctx,
            action="driver.assigned",
            resource_type="driver_assignment",
            resource_id=str(assignment.id),
            data={"driver_id": str(driver_id), "vehicle_id": str(vehicle_id)},
        )
        return assignment

    async def end_assignment(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        assignment_id: uuid.UUID,
        *,
        ended_at: datetime | None = None,
    ) -> DriverAssignment:
        assignment = await self._require(
            DriverAssignment, tenant_id, assignment_id, "Atama bulunamadı."
        )
        if assignment.ended_at is not None:
            raise DomainConflictError("Atama zaten kapatılmış.")
        assignment.ended_at = ended_at or datetime.now(UTC)
        await self._db.flush()
        await record_audit(
            self._db,
            ctx,
            action="driver.assignment_ended",
            resource_type="driver_assignment",
            resource_id=str(assignment.id),
        )
        return assignment

    async def list_assignments(
        self, tenant_id: uuid.UUID, *, vehicle_id: uuid.UUID | None = None
    ) -> list[DriverAssignment]:
        stmt = select(DriverAssignment).where(DriverAssignment.organization_id == tenant_id)
        if vehicle_id is not None:
            stmt = stmt.where(DriverAssignment.vehicle_id == vehicle_id)
        result = await self._db.execute(stmt.order_by(DriverAssignment.started_at.desc()))
        return list(result.scalars())

    # ------------------------------------------------------------- fleets/cameras

    async def create_fleet(
        self, ctx: RequestContext, tenant_id: uuid.UUID, *, name: str, region: str | None
    ) -> Fleet:
        fleet = Fleet(organization_id=tenant_id, name=name, region=region)
        self._db.add(fleet)
        await self._flush_unique("Bu isimde bir filo zaten var.")
        await record_audit(
            self._db,
            ctx,
            action="fleet.created",
            resource_type="fleet",
            resource_id=str(fleet.id),
        )
        return fleet

    async def list_fleets(self, tenant_id: uuid.UUID) -> list[Fleet]:
        result = await self._db.execute(
            select(Fleet).where(Fleet.organization_id == tenant_id).order_by(Fleet.name)
        )
        return list(result.scalars())

    async def create_camera(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        *,
        external_id: str,
        position: str,
        vehicle_id: uuid.UUID | None,
        device_id: uuid.UUID | None,
    ) -> Camera:
        if vehicle_id is not None:
            await self._require(Vehicle, tenant_id, vehicle_id, "Araç bulunamadı.")
        if device_id is not None:
            await self._require(Device, tenant_id, device_id, "Cihaz bulunamadı.")
        camera = Camera(
            organization_id=tenant_id,
            external_id=external_id.strip(),
            position=position,
            vehicle_id=vehicle_id,
            device_id=device_id,
        )
        self._db.add(camera)
        await self._flush_unique("Bu dış kimliğe (external_id) sahip bir kamera zaten var.")
        await record_audit(
            self._db,
            ctx,
            action="camera.created",
            resource_type="camera",
            resource_id=str(camera.id),
        )
        return camera

    async def list_cameras(self, tenant_id: uuid.UUID) -> list[Camera]:
        result = await self._db.execute(
            select(Camera)
            .where(Camera.organization_id == tenant_id)
            .order_by(Camera.created_at.desc())
        )
        return list(result.scalars())

    # ------------------------------------------------------------- helpers

    async def _require[T](
        self, model: type[T], tenant_id: uuid.UUID, obj_id: uuid.UUID, message: str
    ) -> T:
        obj = await self._db.get(model, obj_id)
        # RLS already blocks cross-tenant rows, but check explicitly so the
        # error is a clean 404 rather than a leaked None.
        if obj is None or getattr(obj, "organization_id", None) != tenant_id:
            raise DomainNotFoundError(message)
        return obj

    async def _paginate[T](self, stmt: Select[tuple[T]], page: Page) -> tuple[list[T], int]:
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self._db.execute(count_stmt)).scalar_one())
        result = await self._db.execute(stmt.limit(page.limit).offset(page.offset))
        return list(result.scalars()), total

    async def _flush_unique(self, conflict_message: str) -> None:
        try:
            await self._db.flush()
        except IntegrityError as exc:
            await self._db.rollback()
            raise DomainConflictError(conflict_message) from exc
