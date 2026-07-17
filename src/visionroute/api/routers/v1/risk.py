"""Road risks, geofences, and driver risk scores."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from visionroute.api.deps import TenantSession, require_permission
from visionroute.api.errors import ForbiddenError, NotFoundError
from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.safety.driver_score_service import DriverScoreService
from visionroute.application.safety.road_risk import RoadRiskService
from visionroute.domain.driver_score import SCORE_MODEL_VERSION
from visionroute.domain.permissions import Permission
from visionroute.infrastructure.db.models.fleet import Driver
from visionroute.infrastructure.db.models.roadrisk import Geofence, RoadRisk

router = APIRouter(tags=["risk"])


def _tenant(ctx: RequestContext) -> uuid.UUID:
    if ctx.organization_id is None:  # pragma: no cover
        raise ForbiddenError
    return ctx.organization_id


# ------------------------------------------------------------------ road risk


class RoadRiskOut(BaseModel):
    id: str
    risk_type: str
    center_latitude: float
    center_longitude: float
    radius_m: float
    observed_count: int
    inferred_severity: str
    confidence: float
    source: str
    source_reliability: float | None
    starts_at: datetime
    expires_at: datetime | None
    last_observed_at: datetime | None
    review_status: str


@router.get("/road-risks", response_model=list[RoadRiskOut])
async def list_road_risks(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.RISKS_READ)],
) -> list[RoadRiskOut]:
    service = RoadRiskService(db)
    return [_road_risk_out(r) for r in await service.list_risks(_tenant(ctx))]


@router.post("/road-risks/rebuild", response_model=dict[str, int])
async def rebuild_road_risks(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.RISKS_MANAGE)],
) -> dict[str, int]:
    """Son olay kümelerinden yol risklerini yeniden hesaplar."""
    service = RoadRiskService(db)
    written = await service.rebuild_for_tenant(_tenant(ctx))
    await record_audit(
        db,
        ctx,
        action="road_risk.rebuilt",
        resource_type="road_risk",
        data={"written": written},
    )
    return {"road_risks": written}


# ------------------------------------------------------------------ geofences


class GeofenceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    kind: str = Field(default="high_risk", pattern="^(high_risk|depot|restricted|custom)$")
    center_latitude: float = Field(ge=-90, le=90)
    center_longitude: float = Field(ge=-180, le=180)
    radius_m: float = Field(gt=0, le=100000)
    notes: str | None = Field(default=None, max_length=2000)


class GeofenceOut(BaseModel):
    id: str
    name: str
    kind: str
    center_latitude: float
    center_longitude: float
    radius_m: float
    active: bool


@router.post("/geofences", status_code=status.HTTP_201_CREATED, response_model=GeofenceOut)
async def create_geofence(
    body: GeofenceCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.GEOFENCES_MANAGE)],
) -> GeofenceOut:
    geofence = Geofence(
        organization_id=_tenant(ctx),
        name=body.name,
        kind=body.kind,
        center_latitude=body.center_latitude,
        center_longitude=body.center_longitude,
        radius_m=body.radius_m,
        notes=body.notes,
    )
    db.add(geofence)
    await db.flush()
    await record_audit(
        db,
        ctx,
        action="geofence.created",
        resource_type="geofence",
        resource_id=str(geofence.id),
    )
    return _geofence_out(geofence)


@router.get("/geofences", response_model=list[GeofenceOut])
async def list_geofences(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.RISKS_READ)],
) -> list[GeofenceOut]:
    result = await db.execute(
        select(Geofence)
        .where(Geofence.organization_id == _tenant(ctx))
        .order_by(Geofence.created_at.desc())
    )
    return [_geofence_out(g) for g in result.scalars()]


# ------------------------------------------------------------------ driver score


class DriverScoreOut(BaseModel):
    driver_id: str
    score: float | None
    risk_index: float | None
    exposure_km: float
    event_count: int
    weighted_events: float
    model_version: int
    has_sufficient_exposure: bool
    # Turkish note shown when there is not enough driving to score fairly.
    note: str | None = None


@router.get("/drivers/{driver_id}/risk-score", response_model=DriverScoreOut)
async def driver_risk_score(
    driver_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.ANALYTICS_READ)],
    window_days: int = 90,
) -> DriverScoreOut:
    tenant_id = _tenant(ctx)
    driver = await db.get(Driver, driver_id)
    if driver is None or driver.organization_id != tenant_id:
        raise NotFoundError("Sürücü bulunamadı.")

    score = await DriverScoreService(db).score_driver(tenant_id, driver_id, window_days=window_days)
    if score is None or not score.has_sufficient_exposure:
        exposure = score.exposure_km if score else 0.0
        return DriverScoreOut(
            driver_id=str(driver_id),
            score=None,
            risk_index=None,
            exposure_km=exposure,
            event_count=0,
            weighted_events=0.0,
            model_version=SCORE_MODEL_VERSION,
            has_sufficient_exposure=False,
            note=("Adil bir skor için yeterli sürüş verisi yok. En az 50 km gereklidir."),
        )
    return DriverScoreOut(
        driver_id=str(driver_id),
        score=score.score,
        risk_index=score.risk_index,
        exposure_km=score.exposure_km,
        event_count=score.event_count,
        weighted_events=score.weighted_events,
        model_version=score.model_version,
        has_sufficient_exposure=True,
    )


def _road_risk_out(r: RoadRisk) -> RoadRiskOut:
    return RoadRiskOut(
        id=str(r.id),
        risk_type=r.risk_type,
        center_latitude=r.center_latitude,
        center_longitude=r.center_longitude,
        radius_m=r.radius_m,
        observed_count=r.observed_count,
        inferred_severity=r.inferred_severity,
        confidence=r.confidence,
        source=r.source,
        source_reliability=r.source_reliability,
        starts_at=r.starts_at,
        expires_at=r.expires_at,
        last_observed_at=r.last_observed_at,
        review_status=r.review_status,
    )


def _geofence_out(g: Geofence) -> GeofenceOut:
    return GeofenceOut(
        id=str(g.id),
        name=g.name,
        kind=g.kind,
        center_latitude=g.center_latitude,
        center_longitude=g.center_longitude,
        radius_m=g.radius_m,
        active=g.active,
    )
