"""webhook secret: require encrypted column, drop plaintext (schema step 3/3)

Revision ID: 5d7c3e4b9f32
Revises: 4e8b2d3c6a21
Create Date: 2026-09-13 20:00:02+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5d7c3e4b9f32"
down_revision: str | None = "4e8b2d3c6a21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("webhook_endpoints", "secret_enc", nullable=False)
    op.drop_column("webhook_endpoints", "secret")


def downgrade() -> None:
    # Restored nullable; the previous (data) revision's downgrade decrypts the
    # values back into it and re-applies NOT NULL.
    op.add_column("webhook_endpoints", sa.Column("secret", sa.String(length=100), nullable=True))
    op.alter_column("webhook_endpoints", "secret_enc", nullable=True)
