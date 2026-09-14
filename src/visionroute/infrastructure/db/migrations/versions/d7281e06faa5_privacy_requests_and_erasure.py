"""privacy requests and erasure

KVKK data-subject requests (export / erasure) with FORCE RLS, and an
``erased`` status for drivers and users whose identifiers were pseudonymized.

Revision ID: d7281e06faa5
Revises: 3cb50dec8f4c
Create Date: 2026-09-14 08:36:56.182219+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d7281e06faa5"
down_revision: str | None = "3cb50dec8f4c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_PREDICATE = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR organization_id::text = current_setting('app.tenant_id', true)"
)


def upgrade() -> None:
    op.create_table(
        "privacy_requests",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("subject_type", sa.String(length=20), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("requested_by_user_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("artifact_key", sa.String(length=400), nullable=True),
        sa.Column("artifact_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("artifact_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('export','erasure')", name=op.f("ck_privacy_requests_kind_valid")
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','completed','failed','canceled')",
            name=op.f("ck_privacy_requests_status_valid"),
        ),
        sa.CheckConstraint(
            "subject_type IN ('driver','user')", name=op.f("ck_privacy_requests_subject_type_valid")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_privacy_requests_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name=op.f("fk_privacy_requests_requested_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_privacy_requests")),
    )
    op.create_index(
        "ix_privacy_requests_due", "privacy_requests", ["status", "next_attempt_at"], unique=False
    )
    op.create_index(
        "ix_privacy_requests_org_created",
        "privacy_requests",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_privacy_requests_active_subject",
        "privacy_requests",
        ["organization_id", "kind", "subject_type", "subject_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','processing')"),
    )
    op.execute("ALTER TABLE privacy_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE privacy_requests FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY privacy_requests_tenant_isolation ON privacy_requests "
        f"USING ({_TENANT_PREDICATE}) WITH CHECK ({_TENANT_PREDICATE})"
    )

    op.add_column("drivers", sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint(op.f("ck_drivers_status_valid"), "drivers", type_="check")
    op.create_check_constraint(
        op.f("ck_drivers_status_valid"), "drivers", "status IN ('active','inactive','erased')"
    )
    op.drop_constraint(op.f("ck_users_status_valid"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_status_valid"), "users", "status IN ('active','disabled','erased')"
    )


def downgrade() -> None:
    # Erased rows keep their pseudonymized identifiers; they map to the closest
    # pre-existing non-active status so no personal data is restored.
    op.execute("SELECT set_config('app.rls_bypass', 'on', true)")
    op.execute("UPDATE users SET status = 'disabled' WHERE status = 'erased'")
    op.execute("UPDATE drivers SET status = 'inactive' WHERE status = 'erased'")
    op.drop_constraint(op.f("ck_users_status_valid"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_status_valid"), "users", "status IN ('active','disabled')"
    )
    op.drop_constraint(op.f("ck_drivers_status_valid"), "drivers", type_="check")
    op.create_check_constraint(
        op.f("ck_drivers_status_valid"), "drivers", "status IN ('active','inactive')"
    )
    op.drop_column("drivers", "erased_at")

    op.execute("DROP POLICY IF EXISTS privacy_requests_tenant_isolation ON privacy_requests")
    op.drop_index(
        "uq_privacy_requests_active_subject",
        table_name="privacy_requests",
        postgresql_where=sa.text("status IN ('pending','processing')"),
    )
    op.drop_index("ix_privacy_requests_org_created", table_name="privacy_requests")
    op.drop_index("ix_privacy_requests_due", table_name="privacy_requests")
    op.drop_table("privacy_requests")
