"""Audit trail writer. Critical operations must call this inside the same
transaction as the change they record."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.context import RequestContext
from visionroute.infrastructure.db.models.system import AuditLog


async def record_audit(
    session: AsyncSession,
    ctx: RequestContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    data: dict[str, Any] | None = None,
    organization_id: uuid.UUID | None = None,
) -> None:
    """``organization_id`` overrides the context tenant — needed for auth
    flows where the actor is anonymous but the affected tenant is known."""
    session.add(
        AuditLog(
            organization_id=organization_id or ctx.organization_id,
            actor_user_id=ctx.user_id,
            actor_label=ctx.actor_label,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ctx.ip_address,
            request_id=ctx.request_id,
            data=data or {},
        )
    )
