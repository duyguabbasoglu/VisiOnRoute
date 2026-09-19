"""Synthetic demo data onboarding (VISIONROUTE_ENVIRONMENT=demo only).

Lets the owner/admin of a fresh organization on the public demo populate the
real dashboard with synthetic data in one click. Seeding runs server-side
through the ingestion pipeline; no API key is issued to the browser.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from visionroute.api.deps import CurrentContext, TenantSession, get_app_settings
from visionroute.api.errors import ForbiddenError
from visionroute.application.context import RequestContext
from visionroute.application.demo.seed import DemoSeedService, SeedSummary
from visionroute.config.settings import Environment, Settings
from visionroute.domain.permissions import RoleKey
from visionroute.domain.synthetic_telemetry import DATA_ORIGIN, ENVIRONMENT

router = APIRouter(prefix="/demo-data", tags=["demo-data"])

_SEED_ROLES = frozenset({RoleKey.OWNER, RoleKey.ADMIN})

UnavailableReason = Literal["environment", "role", "email_unverified"]

_DENIALS: dict[UnavailableReason, tuple[str, str]] = {
    "environment": (
        "DEMO_DATA_UNAVAILABLE",
        "Sentetik demo verisi yalnızca demo ortamında oluşturulabilir.",
    ),
    "role": (
        "DEMO_DATA_FORBIDDEN",
        "Sentetik demo verisini yalnızca organizasyon sahibi veya yöneticisi oluşturabilir.",
    ),
    "email_unverified": (
        "EMAIL_NOT_VERIFIED",
        "Sentetik demo verisi oluşturmak için önce e-posta adresinizi doğrulayın.",
    ),
}


class DemoDataSummary(BaseModel):
    vehicles: int
    drivers: int
    trips: int
    telemetry_points: int
    safety_events: int
    road_risks: int


class DemoDataStatus(BaseModel):
    available: bool
    seeded: bool
    reason: UnavailableReason | None = None
    message: str | None = None


class DemoSeedResponse(BaseModel):
    created: bool
    data_origin: str
    environment: str
    summary: DemoDataSummary
    message: str


def _unavailable_reason(ctx: RequestContext, settings: Settings) -> UnavailableReason | None:
    if settings.environment is not Environment.DEMO:
        return "environment"
    if ctx.organization_id is None or ctx.role not in _SEED_ROLES:
        return "role"
    # Always required here, independent of the global verification policy.
    if not ctx.email_verified:
        return "email_unverified"
    return None


AppSettings = Annotated[Settings, Depends(get_app_settings)]


@router.get("", response_model=DemoDataStatus)
async def demo_data_status(
    ctx: CurrentContext, settings: AppSettings, db: TenantSession
) -> DemoDataStatus:
    """Sentetik demo verisi oluşturma seçeneğinin kullanılabilirliği."""
    reason = _unavailable_reason(ctx, settings)
    seeded = (
        ctx.organization_id is not None
        and settings.environment is Environment.DEMO
        and await DemoSeedService(db).is_seeded(ctx.organization_id)
    )
    return DemoDataStatus(
        available=reason is None and not seeded,
        seeded=seeded,
        reason=reason,
        message=_DENIALS[reason][1] if reason else None,
    )


@router.post("/seed", response_model=DemoSeedResponse)
async def seed_demo_data(
    ctx: CurrentContext, settings: AppSettings, db: TenantSession
) -> DemoSeedResponse:
    """Organizasyona sentetik demo filosu ve telemetrisi ekler (idempotent)."""
    reason = _unavailable_reason(ctx, settings)
    if reason is not None or ctx.organization_id is None:
        code, message = _DENIALS[reason or "role"]
        raise ForbiddenError(message, code=code)
    result = await DemoSeedService(db).seed(ctx, ctx.organization_id)
    return DemoSeedResponse(
        created=result.created,
        data_origin=DATA_ORIGIN,
        environment=ENVIRONMENT,
        summary=_summary_out(result.summary),
        message=(
            "Sentetik demo verisi oluşturuldu. Tüm kayıtlar sentetiktir ve gerçek kanıt değildir."
            if result.created
            else "Bu organizasyon için sentetik demo verisi zaten oluşturulmuş."
        ),
    )


def _summary_out(summary: SeedSummary) -> DemoDataSummary:
    return DemoDataSummary(
        vehicles=summary.vehicles,
        drivers=summary.drivers,
        trips=summary.trips,
        telemetry_points=summary.telemetry_points,
        safety_events=summary.safety_events,
        road_risks=summary.road_risks,
    )
