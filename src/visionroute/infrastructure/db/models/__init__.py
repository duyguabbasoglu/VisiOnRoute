"""SQLAlchemy models. Import all modules here so Alembic sees full metadata."""

from visionroute.infrastructure.db.models import fleet, identity, system

__all__ = ["fleet", "identity", "system"]
