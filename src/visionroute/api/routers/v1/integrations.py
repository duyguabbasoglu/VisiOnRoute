"""Integration management: data sources, API clients/keys, source health."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from visionroute.api.deps import TenantSession, VerifiedEmailContext, require_permission
from visionroute.api.errors import ForbiddenError
from visionroute.application.api_clients.service import INGEST_SCOPE, ApiClientService
from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.errors import DomainConflictError
from visionroute.domain.permissions import Permission
from visionroute.infrastructure.db.models.ingestion import DataSource

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _tenant(ctx: RequestContext) -> uuid.UUID:
    if ctx.organization_id is None:  # pragma: no cover
        raise ForbiddenError
    return ctx.organization_id


# ----------------------------------------------------------------- schemas


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    source_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,118}[a-z0-9]$")
    kind: str = Field(default="rest", pattern="^(rest|webhook|mqtt|kafka|s3_batch|csv|simulator)$")
    license: str | None = Field(default=None, max_length=200)
    attribution: str | None = Field(default=None, max_length=300)


class DataSourceOut(BaseModel):
    id: str
    name: str
    source_key: str
    kind: str
    status: str
    license: str | None
    attribution: str | None
    last_event_at: datetime | None
    last_success_at: datetime | None
    accepted_count: int
    rejected_count: int
    duplicate_count: int


class ApiClientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class ApiTokenCreate(BaseModel):
    scopes: list[str] = Field(default_factory=lambda: [INGEST_SCOPE])
    expires_at: datetime | None = None


class ApiTokenOut(BaseModel):
    id: str
    prefix: str
    scopes: list[str]
    expires_at: datetime | None
    # Present only at creation; never retrievable afterwards.
    api_key: str | None = None


class ApiClientOut(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime


# ----------------------------------------------------------------- data sources


@router.post("/data-sources", status_code=status.HTTP_201_CREATED, response_model=DataSourceOut)
async def create_data_source(
    body: DataSourceCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.INTEGRATIONS_MANAGE)],
) -> DataSourceOut:
    tenant_id = _tenant(ctx)
    existing = await db.execute(
        select(DataSource).where(
            DataSource.organization_id == tenant_id,
            DataSource.source_key == body.source_key,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise DomainConflictError("Bu kaynak anahtarı (source_key) zaten kullanımda.")
    source = DataSource(
        organization_id=tenant_id,
        name=body.name,
        source_key=body.source_key,
        kind=body.kind,
        license=body.license,
        attribution=body.attribution,
    )
    db.add(source)
    await db.flush()
    await record_audit(
        db,
        ctx,
        action="data_source.created",
        resource_type="data_source",
        resource_id=str(source.id),
        data={"source_key": source.source_key, "kind": source.kind},
    )
    return _source_out(source)


@router.get("/data-sources", response_model=list[DataSourceOut])
async def list_data_sources(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.INTEGRATIONS_READ)],
) -> list[DataSourceOut]:
    result = await db.execute(
        select(DataSource)
        .where(DataSource.organization_id == _tenant(ctx))
        .order_by(DataSource.created_at.desc())
    )
    return [_source_out(s) for s in result.scalars()]


# ----------------------------------------------------------------- api clients


@router.post("/clients", status_code=status.HTTP_201_CREATED, response_model=ApiClientOut)
async def create_api_client(
    body: ApiClientCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.INTEGRATIONS_MANAGE)],
) -> ApiClientOut:
    service = ApiClientService(db)
    client = await service.create_client(ctx, _tenant(ctx), name=body.name)
    return ApiClientOut(
        id=str(client.id), name=client.name, status=client.status, created_at=client.created_at
    )


@router.get("/clients", response_model=list[ApiClientOut])
async def list_api_clients(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.INTEGRATIONS_READ)],
) -> list[ApiClientOut]:
    service = ApiClientService(db)
    return [
        ApiClientOut(id=str(c.id), name=c.name, status=c.status, created_at=c.created_at)
        for c in await service.list_clients(_tenant(ctx))
    ]


@router.post(
    "/clients/{client_id}/tokens",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiTokenOut,
)
async def issue_api_token(
    client_id: uuid.UUID,
    body: ApiTokenCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.INTEGRATIONS_MANAGE)],
    _verified: VerifiedEmailContext,
) -> ApiTokenOut:
    service = ApiClientService(db)
    token, cleartext = await service.issue_token(
        ctx, _tenant(ctx), client_id, scopes=body.scopes, expires_at=body.expires_at
    )
    return ApiTokenOut(
        id=str(token.id),
        prefix=token.prefix,
        scopes=list(token.scopes),
        expires_at=token.expires_at,
        api_key=cleartext,
    )


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_token(
    token_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.INTEGRATIONS_MANAGE)],
) -> None:
    service = ApiClientService(db)
    await service.revoke_token(ctx, _tenant(ctx), token_id)


def _source_out(s: DataSource) -> DataSourceOut:
    return DataSourceOut(
        id=str(s.id),
        name=s.name,
        source_key=s.source_key,
        kind=s.kind,
        status=s.status,
        license=s.license,
        attribution=s.attribution,
        last_event_at=s.last_event_at,
        last_success_at=s.last_success_at,
        accepted_count=s.accepted_count,
        rejected_count=s.rejected_count,
        duplicate_count=s.duplicate_count,
    )
