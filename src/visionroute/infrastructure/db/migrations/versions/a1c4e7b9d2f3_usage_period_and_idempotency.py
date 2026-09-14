"""usage period and idempotency

Daily usage snapshots are keyed by (organization, metric, UTC day) so the
scheduler can recompute them idempotently.

Revision ID: a1c4e7b9d2f3
Revises: d7281e06faa5
Create Date: 2026-09-14 09:10:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e7b9d2f3"
down_revision: str | None = "d7281e06faa5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("usage_records", sa.Column("period_start", sa.Date(), nullable=True))
    # FORCE RLS applies to the migration role too; existing rows of every
    # tenant must be backfilled.
    op.execute("SELECT set_config('app.rls_bypass', 'on', true)")
    op.execute(
        "UPDATE usage_records SET period_start = (recorded_at AT TIME ZONE 'UTC')::date "
        "WHERE period_start IS NULL"
    )
    # Keep the newest value per key before enforcing uniqueness.
    op.execute(
        "DELETE FROM usage_records u USING usage_records newer "
        "WHERE u.organization_id = newer.organization_id AND u.metric = newer.metric "
        "AND u.period_start = newer.period_start "
        "AND (u.recorded_at, u.id) < (newer.recorded_at, newer.id)"
    )
    op.alter_column("usage_records", "period_start", nullable=False)
    op.create_unique_constraint(
        "uq_usage_records_org_metric_period",
        "usage_records",
        ["organization_id", "metric", "period_start"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_usage_records_org_metric_period", "usage_records", type_="unique")
    op.drop_column("usage_records", "period_start")
