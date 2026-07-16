"""The database RBAC seed must exactly match the domain catalog.

If someone edits visionroute.domain.permissions without a matching migration,
this test fails — preventing UI/reporting drift from real authorization.
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from visionroute.config.settings import Settings
from visionroute.domain.permissions import ROLE_PERMISSIONS, Permission, RoleKey


def test_seeded_rbac_matches_catalog(test_settings: Settings) -> None:
    async def run() -> None:
        engine = create_async_engine(test_settings.database_url)
        try:
            async with engine.connect() as conn:
                db_perms = {
                    r[0] for r in await conn.execute(text("SELECT code FROM permissions"))
                }
                db_roles = {r[0] for r in await conn.execute(text("SELECT key FROM roles"))}
                db_pairs = {
                    (r[0], r[1])
                    for r in await conn.execute(
                        text("SELECT role_key, permission_code FROM role_permissions")
                    )
                }
        finally:
            await engine.dispose()

        assert db_perms == {p.value for p in Permission}
        assert db_roles == {r.value for r in RoleKey}
        catalog_pairs = {
            (role.value, perm.value)
            for role, perms in ROLE_PERMISSIONS.items()
            for perm in perms
        }
        assert db_pairs == catalog_pairs

    asyncio.run(run())
