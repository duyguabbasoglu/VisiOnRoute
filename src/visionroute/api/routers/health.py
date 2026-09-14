"""Liveness/readiness endpoints. Must never leak configuration values."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

import visionroute.infrastructure.db as db_package
from visionroute.observability.logging import get_logger

router = APIRouter(prefix="/health", tags=["health"])
logger = get_logger(__name__)

# Failing any of these makes the instance unready (503). Other checks are
# reported for diagnosis only: the rate limiter fails open by design.
_CRITICAL_CHECKS = frozenset({"database", "migrations"})


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, bool]


@lru_cache(maxsize=1)
def _code_migration_head() -> str | None:
    return ScriptDirectory(str(Path(db_package.__file__).parent / "migrations")).get_current_head()


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=HealthStatus)
async def ready(request: Request, response: Response) -> HealthStatus:
    checks: dict[str, bool] = {"database": False, "migrations": False}

    engine: AsyncEngine | None = getattr(request.app.state, "db_engine", None)
    if engine is not None:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                checks["database"] = True
                # An instance running code newer than the schema must not
                # receive traffic (deploy ordering: migrate, then roll out).
                revision = (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one_or_none()
                checks["migrations"] = revision is not None and revision == _code_migration_head()
        except Exception as exc:
            logger.warning("readiness_check_failed", error_type=type(exc).__name__)

    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is not None and hasattr(limiter, "healthy"):
        checks["rate_limiter"] = bool(await limiter.healthy())

    healthy = all(checks[name] for name in _CRITICAL_CHECKS)
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthStatus(status="ok" if healthy else "degraded", checks=checks)
