"""API-key authentication for machine-to-machine ingestion endpoints.

The ingest key is presented via the ``X-API-Key`` header. Verification uses an
RLS-bypass session (the tenant is unknown until the key resolves); the yielded
work session is then bound to the resolved tenant so RLS applies to all writes.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.api.errors import ForbiddenError, UnauthorizedError
from visionroute.application.api_clients.service import INGEST_SCOPE, ApiClientService
from visionroute.application.context import RequestContext
from visionroute.infrastructure.db.tenancy import set_rls_bypass, set_tenant


@dataclass(frozen=True)
class IngestPrincipal:
    organization_id: uuid.UUID
    api_client_id: uuid.UUID
    scopes: list[str]


async def _authenticate(request: Request) -> IngestPrincipal:
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        raise UnauthorizedError("API anahtarı gerekli (X-API-Key).", code="API_KEY_REQUIRED")

    factory = request.app.state.db_session_factory
    async with factory() as session:
        await set_rls_bypass(session)
        verified = await ApiClientService(session).verify_token(api_key)
        # last_used_at bookkeeping is committed even on rejection paths below.
        await session.commit()

    if verified is None:
        raise UnauthorizedError("API anahtarı geçersiz veya süresi dolmuş.", code="API_KEY_INVALID")
    if INGEST_SCOPE not in verified.scopes:
        raise ForbiddenError("Bu anahtar veri alımı için yetkili değil.", code="SCOPE_MISSING")
    return IngestPrincipal(
        organization_id=verified.organization_id,
        api_client_id=verified.api_client_id,
        scopes=verified.scopes,
    )


IngestAuth = Annotated[IngestPrincipal, Depends(_authenticate)]


async def get_ingest_session(
    request: Request, principal: IngestAuth
) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.db_session_factory
    async with factory() as session:
        await set_tenant(session, principal.organization_id)
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


IngestSession = Annotated[AsyncSession, Depends(get_ingest_session)]


def ingest_context(principal: IngestPrincipal, request: Request) -> RequestContext:
    return RequestContext(
        user_id=None,
        organization_id=principal.organization_id,
        role=None,
        is_platform_admin=False,
        actor_label=f"api_client:{principal.api_client_id}",
        request_id=getattr(request.state, "request_id", None),
    )
