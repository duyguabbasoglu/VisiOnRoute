"""session rotation successor

``sessions.replaced_by_id`` points from a rotated refresh-token session to its
successor, so a retried rotation (lost response) can be told apart from logout
or a superseded token. The sessions table has no RLS (see ADR-0010).

Revision ID: 0494b5ae9220
Revises: a1c4e7b9d2f3
Create Date: 2026-09-14 17:03:44.784317+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0494b5ae9220"
down_revision: str | None = "a1c4e7b9d2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("replaced_by_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_sessions_replaced_by_id_sessions"),
        "sessions",
        "sessions",
        ["replaced_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_sessions_replaced_by_id_sessions"), "sessions", type_="foreignkey")
    op.drop_column("sessions", "replaced_by_id")
