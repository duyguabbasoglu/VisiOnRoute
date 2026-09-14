"""Every tenant-scoped table must enforce row-level security.

A new table with ``organization_id`` but no FORCE RLS policy would silently
bypass tenant isolation for any query that forgets a filter. Exceptions are
explicit and justified here; adding one requires a code review of this list.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from visionroute.config.settings import Settings

pytestmark = pytest.mark.security

# Tables read before a tenant is known or written for platform-level actors.
# Access to them goes through application code that filters organization_id.
RLS_EXEMPT = {
    # Written for anonymous/platform actions too (failed logins, bootstrap);
    # read only via audit.read with an explicit organization filter.
    "audit_logs",
    # Looked up by idempotency key before the request is authorized.
    "idempotency_keys",
    # Refresh-token rotation resolves the session before the tenant is known.
    "sessions",
}


async def test_tenant_tables_force_row_level_security(test_settings: Settings) -> None:
    engine = create_async_engine(test_settings.database_url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                        "(SELECT count(*) FROM pg_policies p "
                        " WHERE p.schemaname = 'public' AND p.tablename = c.relname) "
                        "FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
                        "AND NOT c.relispartition "
                        "AND EXISTS (SELECT 1 FROM information_schema.columns col "
                        "  WHERE col.table_schema = 'public' AND col.table_name = c.relname "
                        "  AND col.column_name = 'organization_id')"
                    )
                )
            ).all()
    finally:
        await engine.dispose()

    tables = {name for name, *_ in rows}
    assert "privacy_requests" in tables
    assert tables >= RLS_EXEMPT, "stale exemption: table no longer tenant-scoped"
    unprotected = sorted(
        name
        for name, enabled, forced, policies in rows
        if name not in RLS_EXEMPT and not (enabled and forced and policies > 0)
    )
    assert unprotected == [], f"tenant tables without FORCE RLS policy: {unprotected}"
