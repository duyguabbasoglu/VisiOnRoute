"""PostgreSQL session tenancy context (RLS layer, ADR-0010).

Every transaction must declare its tenancy mode before touching
tenant-bound tables:

- ``set_tenant`` for tenant-scoped request handling (RLS filters rows),
- ``set_rls_bypass`` for trusted platform paths (auth, worker, platform admin).

``SET LOCAL`` scopes the setting to the current transaction only.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_tenant(session: AsyncSession, organization_id: uuid.UUID) -> None:
    # set_config with a parameter — the value is never interpolated into SQL.
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(organization_id)},
    )


async def set_rls_bypass(session: AsyncSession) -> None:
    await session.execute(text("SELECT set_config('app.rls_bypass', 'on', true)"))
