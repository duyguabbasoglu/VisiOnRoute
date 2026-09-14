"""webhook secret: encrypt existing plaintext secrets (data step 2/3)

Requires VISIONROUTE_FIELD_ENCRYPTION_KEYS when rows exist. The tables use
FORCE ROW LEVEL SECURITY, so the migration must enable ``app.rls_bypass``;
otherwise it would see zero rows and the next step would drop the plaintext
column with nothing encrypted.

Revision ID: 4e8b2d3c6a21
Revises: 3f9a1c2b7d10
Create Date: 2026-09-13 20:00:01+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from visionroute.config.settings import get_settings
from visionroute.infrastructure.security.crypto import build_field_cipher

revision: str = "4e8b2d3c6a21"
down_revision: str | None = "3f9a1c2b7d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MISSING_KEYS = (
    "webhook_endpoints has rows but VISIONROUTE_FIELD_ENCRYPTION_KEYS is not configured; "
    "configure the field encryption keys before running this migration."
)


def _bypass_rls() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'on', true)")


def upgrade() -> None:
    _bypass_rls()
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, secret FROM webhook_endpoints WHERE secret_enc IS NULL")
    ).all()
    if not rows:
        return
    cipher = build_field_cipher(get_settings())
    if cipher is None:
        raise RuntimeError(_MISSING_KEYS)
    for row_id, secret in rows:
        bind.execute(
            sa.text("UPDATE webhook_endpoints SET secret_enc = :enc WHERE id = :id"),
            {"enc": cipher.encrypt(secret), "id": row_id},
        )


def downgrade() -> None:
    _bypass_rls()
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, secret_enc FROM webhook_endpoints WHERE secret_enc IS NOT NULL")
    ).all()
    if rows:
        cipher = build_field_cipher(get_settings())
        if cipher is None:
            raise RuntimeError(_MISSING_KEYS)
        for row_id, secret_enc in rows:
            bind.execute(
                sa.text(
                    "UPDATE webhook_endpoints SET secret = :plain, secret_enc = NULL WHERE id = :id"
                ),
                {"plain": cipher.decrypt(secret_enc), "id": row_id},
            )
    op.alter_column("webhook_endpoints", "secret", nullable=False)
