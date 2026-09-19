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
from visionroute.api.ratelimit import enforce_rate_limit
from visionroute.application.api_clients.service import (
    EVIDENCE_SCOPE,
    INGEST_SCOPE,
    ApiClientService,
)
from visionroute.application.context import RequestContext
from visionroute.config.settings import Settings
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
    settings: Settings = request.app.state.settings
    await enforce_rate_limit(
        request,
        scope="ingest:client",
        identity=str(verified.api_client_id),
        limit=settings.ingest_rate_limit_per_minute,
        window_seconds=60,
    )
    return IngestPrincipal(
        organization_id=verified.organization_id,
        api_client_id=verified.api_client_id,
        scopes=verified.scopes,
    )


ApiKeyAuth = Annotated[IngestPrincipal, Depends(_authenticate)]


def _require_ingest_scope(principal: ApiKeyAuth) -> IngestPrincipal:
    if INGEST_SCOPE not in principal.scopes:
        raise ForbiddenError("Bu anahtar veri alımı için yetkili değil.", code="SCOPE_MISSING")
    return principal


def _require_evidence_scope(principal: ApiKeyAuth) -> IngestPrincipal:
    if EVIDENCE_SCOPE not in principal.scopes:
        raise ForbiddenError(
            "Bu anahtar kanıt yükleme için yetkili değil (evidence:write).", code="SCOPE_MISSING"
        )
    return principal


IngestAuth = Annotated[IngestPrincipal, Depends(_require_ingest_scope)]
EvidenceAuth = Annotated[IngestPrincipal, Depends(_require_evidence_scope)]


async def get_ingest_session(
    request: Request, principal: ApiKeyAuth
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


# Commit before the response is sent (see TenantSession in api/deps.py).
IngestSession = Annotated[AsyncSession, Depends(get_ingest_session, scope="function")]


def ingest_context(principal: IngestPrincipal, request: Request) -> RequestContext:
    return RequestContext(
        user_id=None,
        organization_id=principal.organization_id,
        role=None,
        is_platform_admin=False,
        actor_label=f"api_client:{principal.api_client_id}",
        request_id=getattr(request.state, "request_id", None),
    )
