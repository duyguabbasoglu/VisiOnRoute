"""API client + token management (machine-to-machine auth for ingestion).

Tokens are opaque; only their SHA-256 digest is stored. The cleartext is
returned exactly once at creation. Verification is constant-time via the DB
lookup on the digest, with explicit expiry/revocation checks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.errors import DomainNotFoundError
from visionroute.infrastructure.db.models.identity import ApiClient, ApiToken
from visionroute.infrastructure.security.tokens import (
    generate_opaque_secret,
    hash_opaque_secret,
)

INGEST_SCOPE = "ingest:write"


@dataclass(frozen=True)
class VerifiedToken:
    token_id: uuid.UUID
    api_client_id: uuid.UUID
    organization_id: uuid.UUID
    scopes: list[str]


class ApiClientService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def create_client(
        self, ctx: RequestContext, tenant_id: uuid.UUID, *, name: str
    ) -> ApiClient:
        client = ApiClient(organization_id=tenant_id, name=name, created_by_user_id=ctx.user_id)
        self._db.add(client)
        await self._db.flush()
        await record_audit(
            self._db,
            ctx,
            action="api_client.created",
            resource_type="api_client",
            resource_id=str(client.id),
            data={"name": name},
        )
        return client

    async def list_clients(self, tenant_id: uuid.UUID) -> list[ApiClient]:
        result = await self._db.execute(
            select(ApiClient)
            .where(ApiClient.organization_id == tenant_id)
            .order_by(ApiClient.created_at.desc())
        )
        return list(result.scalars())

    async def issue_token(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        client_id: uuid.UUID,
        *,
        scopes: list[str],
        expires_at: datetime | None = None,
    ) -> tuple[ApiToken, str]:
        client = await self._db.get(ApiClient, client_id)
        if client is None or client.organization_id != tenant_id:
            raise DomainNotFoundError("API istemcisi bulunamadı.")
        cleartext, digest = generate_opaque_secret("vrk")
        token = ApiToken(
            api_client_id=client.id,
            token_hash=digest,
            prefix=cleartext[:12],
            scopes=scopes,
            expires_at=expires_at,
        )
        self._db.add(token)
        await self._db.flush()
        await record_audit(
            self._db,
            ctx,
            action="api_token.issued",
            resource_type="api_token",
            resource_id=str(token.id),
            data={"scopes": scopes, "client_id": str(client.id)},
        )
        return token, cleartext

    async def revoke_token(
        self, ctx: RequestContext, tenant_id: uuid.UUID, token_id: uuid.UUID
    ) -> None:
        token = await self._db.get(ApiToken, token_id)
        if token is None:
            raise DomainNotFoundError("Anahtar bulunamadı.")
        client = await self._db.get(ApiClient, token.api_client_id)
        if client is None or client.organization_id != tenant_id:
            raise DomainNotFoundError("Anahtar bulunamadı.")
        token.revoked_at = datetime.now(UTC)
        await record_audit(
            self._db,
            ctx,
            action="api_token.revoked",
            resource_type="api_token",
            resource_id=str(token.id),
        )

    async def verify_token(self, cleartext: str) -> VerifiedToken | None:
        """Resolve an API key to its tenant/scopes, or None if invalid.

        Runs under an RLS-bypass session because it must find the token before
        any tenant context is known.
        """
        digest = hash_opaque_secret(cleartext)
        result = await self._db.execute(
            select(ApiToken, ApiClient)
            .join(ApiClient, ApiClient.id == ApiToken.api_client_id)
            .where(ApiToken.token_hash == digest)
        )
        row = result.one_or_none()
        if row is None:
            return None
        token, client = row
        now = datetime.now(UTC)
        if token.revoked_at is not None:
            return None
        if token.expires_at is not None and token.expires_at <= now:
            return None
        if client.status != "active":
            return None
        token.last_used_at = now
        return VerifiedToken(
            token_id=token.id,
            api_client_id=client.id,
            organization_id=client.organization_id,
            scopes=list(token.scopes),
        )
