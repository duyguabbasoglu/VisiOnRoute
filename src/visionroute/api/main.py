"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from visionroute import __version__
from visionroute.api.errors import register_error_handlers
from visionroute.api.middleware import register_middleware
from visionroute.api.routers.health import router as health_router
from visionroute.config.settings import Settings, get_settings
from visionroute.infrastructure.db.engine import build_engine, build_session_factory
from visionroute.infrastructure.security.tokens import JwtService, TokenError
from visionroute.observability.logging import configure_logging, get_logger

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(
        json_output=settings.environment.is_production_like,
        level=logging.DEBUG if settings.debug else logging.INFO,
    )

    problems = settings.validate_for_runtime()
    if problems and settings.environment.is_production_like:
        for problem in problems:
            logger.error("config_problem", detail=problem)
        msg = "Yapılandırma doğrulaması başarısız; başlatma durduruldu."
        raise RuntimeError(msg)
    for problem in problems:
        logger.warning("config_problem", detail=problem)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db_engine = build_engine(settings)
        app.state.db_session_factory = build_session_factory(app.state.db_engine)
        app.state.settings = settings
        try:
            app.state.jwt_service = JwtService(settings)
        except (TokenError, OSError):
            # Auth endpoints will return 503 AUTH_NOT_CONFIGURED until keys exist.
            app.state.jwt_service = None
            logger.warning("jwt_service_unavailable")
        logger.info("api_started", version=__version__, environment=settings.environment)
        try:
            yield
        finally:
            await app.state.db_engine.dispose()
            logger.info("api_stopped")

    app = FastAPI(
        title="VISiOnRoute API",
        description="Sürücü davranışlarını ve yol koşullarını analiz eden ulaşım "
        "güvenliği platformu API'si.",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs" if not settings.environment.is_production_like else None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
    )
    register_middleware(app, settings)
    register_error_handlers(app)

    app.include_router(health_router)
    _include_v1_routers(app)
    return app


def _include_v1_routers(app: FastAPI) -> None:
    """v1 routers are registered here as milestones land."""
    from visionroute.api.routers import v1

    app.include_router(v1.router, prefix="/api/v1")
