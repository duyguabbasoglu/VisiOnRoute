"""Liveness/readiness endpoints. Must never leak configuration values."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

router = APIRouter(prefix="/health", tags=["health"])


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, bool]


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=HealthStatus)
async def ready(request: Request, response: Response) -> HealthStatus:
    checks: dict[str, bool] = {}

    engine: AsyncEngine | None = getattr(request.app.state, "db_engine", None)
    if engine is None:
        checks["database"] = False
    else:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception:
            checks["database"] = False

    healthy = all(checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthStatus(status="ok" if healthy else "degraded", checks=checks)
