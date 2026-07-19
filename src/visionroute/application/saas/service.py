"""Subscription entitlements and enforcement (M10).

Limits are enforced in the application layer (deny-by-default): creation
paths call ``enforce_*`` before writing. ``-1`` means unlimited. The default
billing mode is manual invoicing (Turkish enterprise sales, ADR-0009); the
Stripe adapter activates only when configured with credentials.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.errors import DomainConflictError
from visionroute.infrastructure.db.models.fleet import Vehicle
from visionroute.infrastructure.db.models.identity import Membership
from visionroute.infrastructure.db.models.saas import Plan, Subscription

DEFAULT_TRIAL_PLAN = "baslangic"
TRIAL_DAYS = 30

# Seeded system plans; the migration mirrors this catalog.
PLAN_CATALOG: list[dict[str, object]] = [
    {
        "key": "baslangic",
        "name_tr": "Başlangıç",
        "vehicle_limit": 10,
        "user_limit": 5,
        "retention_days": 90,
        "monthly_price_try": 4900.0,
    },
    {
        "key": "profesyonel",
        "name_tr": "Profesyonel",
        "vehicle_limit": 100,
        "user_limit": 25,
        "retention_days": 365,
        "monthly_price_try": 19900.0,
    },
    {
        "key": "kurumsal",
        "name_tr": "Kurumsal",
        "vehicle_limit": -1,
        "user_limit": -1,
        "retention_days": 730,
        "monthly_price_try": None,  # sözleşmeye tabi
    },
]


@dataclass(frozen=True)
class Entitlements:
    plan_key: str
    plan_name_tr: str
    status: str
    vehicle_limit: int
    user_limit: int
    retention_days: int
    trial_ends_at: datetime | None


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def start_trial(self, organization_id: uuid.UUID) -> Subscription:
        subscription = Subscription(
            organization_id=organization_id,
            plan_key=DEFAULT_TRIAL_PLAN,
            status="trial",
            trial_ends_at=datetime.now(UTC) + timedelta(days=TRIAL_DAYS),
        )
        self._db.add(subscription)
        return subscription

    async def get_entitlements(self, organization_id: uuid.UUID) -> Entitlements:
        row = await self._db.execute(
            select(Subscription, Plan)
            .join(Plan, Plan.key == Subscription.plan_key)
            .where(Subscription.organization_id == organization_id)
        )
        pair = row.one_or_none()
        if pair is None:
            # Legacy orgs created before M10 fall back to the trial plan.
            plan_row = await self._db.get(Plan, DEFAULT_TRIAL_PLAN)
            if plan_row is None:  # pragma: no cover - seed guarantees existence
                msg = "Plan kataloğu eksik."
                raise RuntimeError(msg)
            return Entitlements(
                plan_key=plan_row.key,
                plan_name_tr=plan_row.name_tr,
                status="trial",
                vehicle_limit=plan_row.vehicle_limit,
                user_limit=plan_row.user_limit,
                retention_days=plan_row.retention_days,
                trial_ends_at=None,
            )
        subscription, plan = pair
        return Entitlements(
            plan_key=plan.key,
            plan_name_tr=plan.name_tr,
            status=subscription.status,
            vehicle_limit=plan.vehicle_limit,
            user_limit=plan.user_limit,
            retention_days=plan.retention_days,
            trial_ends_at=subscription.trial_ends_at,
        )

    async def enforce_vehicle_limit(self, organization_id: uuid.UUID) -> None:
        entitlements = await self.get_entitlements(organization_id)
        if entitlements.vehicle_limit < 0:
            return
        count = await self._db.execute(
            select(func.count()).where(Vehicle.organization_id == organization_id)
        )
        if int(count.scalar_one()) >= entitlements.vehicle_limit:
            raise DomainConflictError(
                f"Araç limiti aşıldı ({entitlements.vehicle_limit} araç, "
                f"{entitlements.plan_name_tr} planı). Planınızı yükseltin."
            )

    async def enforce_user_limit(self, organization_id: uuid.UUID) -> None:
        entitlements = await self.get_entitlements(organization_id)
        if entitlements.user_limit < 0:
            return
        count = await self._db.execute(
            select(func.count()).where(Membership.organization_id == organization_id)
        )
        if int(count.scalar_one()) >= entitlements.user_limit:
            raise DomainConflictError(
                f"Kullanıcı limiti aşıldı ({entitlements.user_limit} kullanıcı, "
                f"{entitlements.plan_name_tr} planı). Planınızı yükseltin."
            )

    async def change_plan(self, organization_id: uuid.UUID, plan_key: str) -> Subscription:
        plan = await self._db.get(Plan, plan_key)
        if plan is None:
            raise DomainConflictError("Bilinmeyen plan.")
        row = await self._db.execute(
            select(Subscription).where(Subscription.organization_id == organization_id)
        )
        subscription = row.scalar_one_or_none()
        if subscription is None:
            subscription = Subscription(
                organization_id=organization_id, plan_key=plan_key, status="active"
            )
            self._db.add(subscription)
        else:
            subscription.plan_key = plan_key
            subscription.status = "active"
            subscription.trial_ends_at = None
        return subscription
