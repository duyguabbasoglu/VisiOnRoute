"""SQLAlchemy models. Import all modules here so Alembic sees full metadata."""

from visionroute.infrastructure.db.models import (
    fleet,
    identity,
    ingestion,
    notifications,
    roadrisk,
    safety,
    system,
    telemetry,
)

__all__ = [
    "fleet",
    "identity",
    "ingestion",
    "notifications",
    "roadrisk",
    "safety",
    "system",
    "telemetry",
]
