"""evidence media lifecycle

Adds upload/verification/deletion state to ``event_evidence`` for media
evidence stored in object storage. Existing rows (telemetry windows) become
``available`` / ``not_applicable``. The table already has FORCE RLS.

Revision ID: 3cb50dec8f4c
Revises: 8c3d5e7f9a21
Create Date: 2026-09-14 08:20:47.852117+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3cb50dec8f4c"
down_revision: str | None = "8c3d5e7f9a21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event_evidence",
        sa.Column("status", sa.String(length=20), server_default="available", nullable=False),
    )
    op.add_column("event_evidence", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column(
        "event_evidence", sa.Column("original_filename", sa.String(length=200), nullable=True)
    )
    op.add_column("event_evidence", sa.Column("uploaded_by_user_id", sa.UUID(), nullable=True))
    op.add_column(
        "event_evidence", sa.Column("uploaded_by_api_client_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "event_evidence",
        sa.Column(
            "redaction_status",
            sa.String(length=30),
            server_default="not_applicable",
            nullable=False,
        ),
    )
    op.add_column(
        "event_evidence", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_event_evidence_status_valid"),
        "event_evidence",
        "status IN ('pending_upload','available','rejected','deleted')",
    )
    op.create_check_constraint(
        op.f("ck_event_evidence_redaction_status_valid"),
        "event_evidence",
        "redaction_status IN ('not_applicable','not_processed','pending','completed','failed')",
    )


def downgrade() -> None:
    # Media rows only exist with the new lifecycle; the old schema cannot
    # represent pending/rejected uploads, so they are removed on downgrade.
    op.execute("DELETE FROM event_evidence WHERE status <> 'available'")
    op.drop_constraint(
        op.f("ck_event_evidence_redaction_status_valid"), "event_evidence", type_="check"
    )
    op.drop_constraint(op.f("ck_event_evidence_status_valid"), "event_evidence", type_="check")
    op.drop_column("event_evidence", "deleted_at")
    op.drop_column("event_evidence", "redaction_status")
    op.drop_column("event_evidence", "uploaded_by_api_client_id")
    op.drop_column("event_evidence", "uploaded_by_user_id")
    op.drop_column("event_evidence", "original_filename")
    op.drop_column("event_evidence", "size_bytes")
    op.drop_column("event_evidence", "status")
