"""SQLAlchemy models. Import all modules here so Alembic sees full metadata."""

from visionroute.infrastructure.db.models import (
    coaching,
    fleet,
    identity,
    ingestion,
    mail,
    notifications,
    roadrisk,
    saas,
    safety,
    system,
    telemetry,
)

__all__ = [
    "coaching",
    "fleet",
    "identity",
    "ingestion",
    "mail",
    "notifications",
    "roadrisk",
    "saas",
    "safety",
    "system",
    "telemetry",
]
