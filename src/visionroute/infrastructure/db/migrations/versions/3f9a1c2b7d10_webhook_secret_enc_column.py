"""webhook secret: add encrypted column (schema step 1/3)

Revision ID: 3f9a1c2b7d10
Revises: 6e3bcf315d54
Create Date: 2026-09-13 20:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3f9a1c2b7d10"
down_revision: str | None = "6e3bcf315d54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("webhook_endpoints", sa.Column("secret_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("webhook_endpoints", "secret_enc")
