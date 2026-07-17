"""Version 1 API router registry."""

from __future__ import annotations

from fastapi import APIRouter

from visionroute.api.routers.v1.auth import router as auth_router
from visionroute.api.routers.v1.fleet import router as fleet_router
from visionroute.api.routers.v1.ingest import router as ingest_router
from visionroute.api.routers.v1.integrations import router as integrations_router
from visionroute.api.routers.v1.operations import router as operations_router
from visionroute.api.routers.v1.organizations import router as organizations_router
from visionroute.api.routers.v1.safety_events import router as safety_events_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(organizations_router)
router.include_router(fleet_router)
router.include_router(integrations_router)
router.include_router(ingest_router)
router.include_router(operations_router)
router.include_router(safety_events_router)
