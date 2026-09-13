"""Platform administration (super admin only) + tenant subscription view."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select

from visionroute.api.deps import (
    PlatformSession,
    TenantSession,
    require_permission,
    require_platform_admin,
)
from visionroute.api.errors import ForbiddenError
from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.saas.service import SubscriptionService
from visionroute.domain.permissions import Permission
from visionroute.infrastructure.db.models.identity import Membership, Organization
from visionroute.infrastructure.db.models.ingestion import IngestEvent
from visionroute.infrastructure.db.models.mail import EmailMessage
from visionroute.infrastructure.db.models.notifications import WebhookDelivery
from visionroute.infrastructure.db.models.saas import Plan, Subscription
from visionroute.infrastructure.db.models.system import OutboxEvent

router = APIRouter(tags=["platform"])


# --------------------------------------------------------- tenant-facing


class EntitlementsOut(BaseModel):
    plan_key: str
    plan_name_tr: str
    status: str
    vehicle_limit: int
    user_limit: int
    retention_days: int
    trial_ends_at: datetime | None


@router.get("/subscription", response_model=EntitlementsOut)
async def my_subscription(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.SUBSCRIPTION_READ)],
) -> EntitlementsOut:
    if ctx.organization_id is None:  # pragma: no cover
        raise ForbiddenError
    entitlements = await SubscriptionService(db).get_entitlements(ctx.organization_id)
    return EntitlementsOut(**entitlements.__dict__)


# --------------------------------------------------------- platform admin


class PlatformOrgOut(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    member_count: int
    plan_key: str | None
    subscription_status: str | None


class PlanChangeRequest(BaseModel):
    plan_key: str = Field(min_length=2, max_length=40)


class PlatformHealthOut(BaseModel):
    outbox_pending: int
    outbox_dead_letter: int
    ingest_quarantined: int
    webhook_dead_letter: int
    email_pending: int
    email_dead_letter: int


@router.get("/platform/organizations", response_model=list[PlatformOrgOut])
async def platform_list_organizations(
    db: PlatformSession,
    ctx: Annotated[RequestContext, Depends(require_platform_admin)],
) -> list[PlatformOrgOut]:
    members = (
        select(Membership.organization_id, func.count().label("member_count"))
        .group_by(Membership.organization_id)
        .subquery()
    )
    rows = await db.execute(
        select(Organization, members.c.member_count, Subscription)
        .outerjoin(members, members.c.organization_id == Organization.id)
        .outerjoin(Subscription, Subscription.organization_id == Organization.id)
        .order_by(Organization.created_at.desc())
    )
    return [
        PlatformOrgOut(
            id=str(org.id),
            name=org.name,
            slug=org.slug,
            status=org.status,
            member_count=int(member_count or 0),
            plan_key=subscription.plan_key if subscription else None,
            subscription_status=subscription.status if subscription else None,
        )
        for org, member_count, subscription in rows.all()
    ]


@router.post("/platform/organizations/{organization_id}/plan", response_model=PlatformOrgOut)
async def platform_change_plan(
    organization_id: uuid.UUID,
    body: PlanChangeRequest,
    db: PlatformSession,
    ctx: Annotated[RequestContext, Depends(require_platform_admin)],
) -> PlatformOrgOut:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        from visionroute.api.errors import NotFoundError

        raise NotFoundError("Organizasyon bulunamadı.")
    subscription = await SubscriptionService(db).change_plan(organization_id, body.plan_key)
    await record_audit(
        db,
        ctx,
        action="subscription.plan_changed",
        resource_type="subscription",
        resource_id=str(subscription.id),
        data={"plan_key": body.plan_key},
        organization_id=organization_id,
    )
    member_count = await db.execute(
        select(func.count()).where(Membership.organization_id == organization_id)
    )
    return PlatformOrgOut(
        id=str(organization.id),
        name=organization.name,
        slug=organization.slug,
        status=organization.status,
        member_count=int(member_count.scalar_one()),
        plan_key=subscription.plan_key,
        subscription_status=subscription.status,
    )


@router.get("/platform/plans", response_model=list[dict[str, object]])
async def platform_list_plans(
    db: PlatformSession,
    ctx: Annotated[RequestContext, Depends(require_platform_admin)],
) -> list[dict[str, object]]:
    rows = await db.execute(select(Plan).order_by(Plan.key))
    return [
        {
            "key": p.key,
            "name_tr": p.name_tr,
            "vehicle_limit": p.vehicle_limit,
            "user_limit": p.user_limit,
            "retention_days": p.retention_days,
            "monthly_price_try": p.monthly_price_try,
        }
        for p in rows.scalars()
    ]


@router.get("/platform/health", response_model=PlatformHealthOut)
async def platform_health(
    db: PlatformSession,
    ctx: Annotated[RequestContext, Depends(require_platform_admin)],
) -> PlatformHealthOut:
    async def count(stmt: Select[tuple[int]]) -> int:
        return int((await db.execute(stmt)).scalar_one())

    return PlatformHealthOut(
        outbox_pending=await count(
            select(func.count()).where(OutboxEvent.status.in_(("pending", "processing")))
        ),
        outbox_dead_letter=await count(
            select(func.count()).where(OutboxEvent.status == "dead_letter")
        ),
        ingest_quarantined=await count(
            select(func.count()).where(IngestEvent.status == "quarantined")
        ),
        webhook_dead_letter=await count(
            select(func.count()).where(WebhookDelivery.status == "dead_letter")
        ),
        email_pending=await count(
            select(func.count()).where(EmailMessage.status.in_(("pending", "sending")))
        ),
        email_dead_letter=await count(
            select(func.count()).where(EmailMessage.status == "dead_letter")
        ),
    )
