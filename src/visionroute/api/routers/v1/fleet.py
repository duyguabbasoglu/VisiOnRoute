"""Fleet management endpoints (vehicles, drivers, devices, cameras, assignments)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field, field_validator

from visionroute.api.deps import TenantSession, require_permission
from visionroute.api.errors import ForbiddenError
from visionroute.application.context import RequestContext
from visionroute.application.fleet.service import FleetService, Page
from visionroute.domain.permissions import Permission
from visionroute.infrastructure.db.models.fleet import (
    Camera,
    Device,
    DriverAssignment,
    Vehicle,
)

router = APIRouter(tags=["fleet"])


def _tenant(ctx: RequestContext) -> uuid.UUID:
    if ctx.organization_id is None:  # pragma: no cover - TenantSession guarantees this
        raise ForbiddenError
    return ctx.organization_id


# ------------------------------------------------------------------ schemas


class Pagination(BaseModel):
    total: int
    limit: int
    offset: int


class VehicleCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    plate: str | None = Field(default=None, max_length=20)
    label: str | None = Field(default=None, max_length=200)
    make: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=80)
    year: int | None = Field(default=None, ge=1950, le=2100)
    fleet_id: uuid.UUID | None = None


class VehicleUpdate(BaseModel):
    plate: str | None = Field(default=None, max_length=20)
    label: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, pattern="^(active|inactive|maintenance)$")
    fleet_id: uuid.UUID | None = None


class VehicleOut(BaseModel):
    id: str
    external_id: str
    plate: str | None
    label: str | None
    make: str | None
    model: str | None
    year: int | None
    status: str
    fleet_id: str | None
    created_at: datetime


class VehicleList(BaseModel):
    items: list[VehicleOut]
    pagination: Pagination


class DriverCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    full_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=32)


class DriverOut(BaseModel):
    id: str
    external_id: str
    full_name: str
    phone: str | None
    status: str
    created_at: datetime


class DriverList(BaseModel):
    items: list[DriverOut]
    pagination: Pagination


class DeviceCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="telematics", pattern="^(telematics|dashcam|sensor|gateway)$")
    label: str | None = Field(default=None, max_length=200)
    vehicle_id: uuid.UUID | None = None


class DeviceOut(BaseModel):
    id: str
    external_id: str
    kind: str
    label: str | None
    status: str
    vehicle_id: str | None
    last_seen_at: datetime | None


class DeviceList(BaseModel):
    items: list[DeviceOut]
    pagination: Pagination


class AssignmentCreate(BaseModel):
    driver_id: uuid.UUID
    vehicle_id: uuid.UUID
    started_at: datetime | None = None


class AssignmentOut(BaseModel):
    id: str
    driver_id: str
    vehicle_id: str
    started_at: datetime
    ended_at: datetime | None


class FleetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    region: str | None = Field(default=None, max_length=120)


class FleetOut(BaseModel):
    id: str
    name: str
    region: str | None


class CameraCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    position: str = Field(default="road", pattern="^(road|driver|cabin|rear)$")
    vehicle_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None


def _reject_null_status(value: str | None) -> str | None:
    # Omit the field to keep the current status; an explicit null is invalid.
    if value is None:
        msg = "Durum boş olamaz."
        raise ValueError(msg)
    return value


class DeviceUpdate(BaseModel):
    """Operator-settable fields; ``offline`` is reserved for the platform."""

    label: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")
    vehicle_id: uuid.UUID | None = None

    _status_not_null = field_validator("status")(_reject_null_status)


class CameraUpdate(BaseModel):
    """Operator-settable fields; ``obstructed``/``offline`` come from the platform."""

    status: str | None = Field(default=None, pattern="^(active|inactive)$")
    vehicle_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None

    _status_not_null = field_validator("status")(_reject_null_status)


class CameraOut(BaseModel):
    id: str
    external_id: str
    position: str
    status: str
    vehicle_id: str | None
    device_id: str | None


# ------------------------------------------------------------------ vehicles


@router.post("/vehicles", status_code=status.HTTP_201_CREATED, response_model=VehicleOut)
async def create_vehicle(
    body: VehicleCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_MANAGE)],
) -> VehicleOut:
    service = FleetService(db)
    vehicle = await service.create_vehicle(
        ctx,
        _tenant(ctx),
        external_id=body.external_id,
        plate=body.plate,
        label=body.label,
        make=body.make,
        model=body.model,
        year=body.year,
        fleet_id=body.fleet_id,
    )
    return _vehicle_out(vehicle)


@router.get("/vehicles", response_model=VehicleList)
async def list_vehicles(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_READ)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    fleet_id: uuid.UUID | None = None,
) -> VehicleList:
    service = FleetService(db)
    items, total = await service.list_vehicles(
        _tenant(ctx), Page(limit=limit, offset=offset), fleet_id=fleet_id
    )
    return VehicleList(
        items=[_vehicle_out(v) for v in items],
        pagination=Pagination(total=total, limit=limit, offset=offset),
    )


@router.get("/vehicles/{vehicle_id}", response_model=VehicleOut)
async def get_vehicle(
    vehicle_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_READ)],
) -> VehicleOut:
    service = FleetService(db)
    return _vehicle_out(await service.get_vehicle(_tenant(ctx), vehicle_id))


@router.patch("/vehicles/{vehicle_id}", response_model=VehicleOut)
async def update_vehicle(
    vehicle_id: uuid.UUID,
    body: VehicleUpdate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_MANAGE)],
) -> VehicleOut:
    service = FleetService(db)
    changes = body.model_dump(exclude_unset=True)
    vehicle = await service.update_vehicle(ctx, _tenant(ctx), vehicle_id, changes=changes)
    return _vehicle_out(vehicle)


# ------------------------------------------------------------------ drivers


@router.post("/drivers", status_code=status.HTTP_201_CREATED, response_model=DriverOut)
async def create_driver(
    body: DriverCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_MANAGE)],
) -> DriverOut:
    service = FleetService(db)
    driver = await service.create_driver(
        ctx,
        _tenant(ctx),
        external_id=body.external_id,
        full_name=body.full_name,
        phone=body.phone,
    )
    return DriverOut(
        id=str(driver.id),
        external_id=driver.external_id,
        full_name=driver.full_name,
        phone=driver.phone,
        status=driver.status,
        created_at=driver.created_at,
    )


@router.get("/drivers", response_model=DriverList)
async def list_drivers(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_READ)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DriverList:
    service = FleetService(db)
    items, total = await service.list_drivers(_tenant(ctx), Page(limit=limit, offset=offset))
    return DriverList(
        items=[
            DriverOut(
                id=str(d.id),
                external_id=d.external_id,
                full_name=d.full_name,
                phone=d.phone,
                status=d.status,
                created_at=d.created_at,
            )
            for d in items
        ],
        pagination=Pagination(total=total, limit=limit, offset=offset),
    )


# ------------------------------------------------------------------ devices


@router.post("/devices", status_code=status.HTTP_201_CREATED, response_model=DeviceOut)
async def create_device(
    body: DeviceCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_MANAGE)],
) -> DeviceOut:
    service = FleetService(db)
    device = await service.create_device(
        ctx,
        _tenant(ctx),
        external_id=body.external_id,
        kind=body.kind,
        label=body.label,
        vehicle_id=body.vehicle_id,
    )
    return _device_out(device)


@router.get("/devices", response_model=DeviceList)
async def list_devices(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_READ)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DeviceList:
    service = FleetService(db)
    items, total = await service.list_devices(_tenant(ctx), Page(limit=limit, offset=offset))
    return DeviceList(
        items=[_device_out(d) for d in items],
        pagination=Pagination(total=total, limit=limit, offset=offset),
    )


@router.patch("/devices/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: uuid.UUID,
    body: DeviceUpdate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_MANAGE)],
) -> DeviceOut:
    service = FleetService(db)
    changes = body.model_dump(exclude_unset=True)
    device = await service.update_device(ctx, _tenant(ctx), device_id, changes=changes)
    return _device_out(device)


# ------------------------------------------------------------------ assignments


@router.post("/assignments", status_code=status.HTTP_201_CREATED, response_model=AssignmentOut)
async def create_assignment(
    body: AssignmentCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_MANAGE)],
) -> AssignmentOut:
    service = FleetService(db)
    assignment = await service.assign_driver(
        ctx,
        _tenant(ctx),
        driver_id=body.driver_id,
        vehicle_id=body.vehicle_id,
        started_at=body.started_at,
    )
    return _assignment_out(assignment)


@router.post("/assignments/{assignment_id}/close", response_model=AssignmentOut)
async def close_assignment(
    assignment_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_MANAGE)],
) -> AssignmentOut:
    service = FleetService(db)
    assignment = await service.end_assignment(ctx, _tenant(ctx), assignment_id)
    return _assignment_out(assignment)


@router.get("/assignments", response_model=list[AssignmentOut])
async def list_assignments(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_READ)],
    vehicle_id: uuid.UUID | None = None,
) -> list[AssignmentOut]:
    service = FleetService(db)
    items = await service.list_assignments(_tenant(ctx), vehicle_id=vehicle_id)
    return [_assignment_out(a) for a in items]


# ------------------------------------------------------------------ fleets/cameras


@router.post("/fleets", status_code=status.HTTP_201_CREATED, response_model=FleetOut)
async def create_fleet(
    body: FleetCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_MANAGE)],
) -> FleetOut:
    service = FleetService(db)
    fleet = await service.create_fleet(ctx, _tenant(ctx), name=body.name, region=body.region)
    return FleetOut(id=str(fleet.id), name=fleet.name, region=fleet.region)


@router.get("/fleets", response_model=list[FleetOut])
async def list_fleets(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_READ)],
) -> list[FleetOut]:
    service = FleetService(db)
    return [
        FleetOut(id=str(f.id), name=f.name, region=f.region)
        for f in await service.list_fleets(_tenant(ctx))
    ]


@router.post("/cameras", status_code=status.HTTP_201_CREATED, response_model=CameraOut)
async def create_camera(
    body: CameraCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_MANAGE)],
) -> CameraOut:
    service = FleetService(db)
    camera = await service.create_camera(
        ctx,
        _tenant(ctx),
        external_id=body.external_id,
        position=body.position,
        vehicle_id=body.vehicle_id,
        device_id=body.device_id,
    )
    return _camera_out(camera)


@router.get("/cameras", response_model=list[CameraOut])
async def list_cameras(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_READ)],
) -> list[CameraOut]:
    service = FleetService(db)
    return [_camera_out(c) for c in await service.list_cameras(_tenant(ctx))]


@router.patch("/cameras/{camera_id}", response_model=CameraOut)
async def update_camera(
    camera_id: uuid.UUID,
    body: CameraUpdate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.FLEET_MANAGE)],
) -> CameraOut:
    service = FleetService(db)
    changes = body.model_dump(exclude_unset=True)
    camera = await service.update_camera(ctx, _tenant(ctx), camera_id, changes=changes)
    return _camera_out(camera)


# ------------------------------------------------------------------ mappers


def _vehicle_out(v: Vehicle) -> VehicleOut:
    return VehicleOut(
        id=str(v.id),
        external_id=v.external_id,
        plate=v.plate,
        label=v.label,
        make=v.make,
        model=v.model,
        year=v.year,
        status=v.status,
        fleet_id=str(v.fleet_id) if v.fleet_id else None,
        created_at=v.created_at,
    )


def _device_out(d: Device) -> DeviceOut:
    return DeviceOut(
        id=str(d.id),
        external_id=d.external_id,
        kind=d.kind,
        label=d.label,
        status=d.status,
        vehicle_id=str(d.vehicle_id) if d.vehicle_id else None,
        last_seen_at=d.last_seen_at,
    )


def _assignment_out(a: DriverAssignment) -> AssignmentOut:
    return AssignmentOut(
        id=str(a.id),
        driver_id=str(a.driver_id),
        vehicle_id=str(a.vehicle_id),
        started_at=a.started_at,
        ended_at=a.ended_at,
    )


def _camera_out(c: Camera) -> CameraOut:
    return CameraOut(
        id=str(c.id),
        external_id=c.external_id,
        position=c.position,
        status=c.status,
        vehicle_id=str(c.vehicle_id) if c.vehicle_id else None,
        device_id=str(c.device_id) if c.device_id else None,
    )
