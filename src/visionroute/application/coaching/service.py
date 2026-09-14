"""Coaching workflow: create (manually or from an event review), assign,
progress, complete or cancel coaching actions.

Tenant scoping is explicit in every query and backed by RLS. Users with the
self-service driver role only see actions for drivers linked to their account.
Creating an action for an event is idempotent: an event has at most one
active action (enforced by a partial unique index; concurrent creates resolve
to the existing action).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.errors import (
    DomainConflictError,
    DomainNotFoundError,
    ValidationFailedError,
)
from visionroute.application.mail.service import MailService
from visionroute.domain.coaching import (
    ACTIVE_STATUSES,
    DEFAULT_DUE_DAYS,
    CoachingOutcome,
    CoachingStatus,
    can_transition,
)
from visionroute.domain.permissions import Permission, RoleKey, role_has
from visionroute.domain.safety import EVENT_LABELS_TR, SafetyEventType
from visionroute.infrastructure.db.models.coaching import CoachingAction
from visionroute.infrastructure.db.models.fleet import Driver
from visionroute.infrastructure.db.models.identity import Membership, Organization, User
from visionroute.infrastructure.db.models.safety import SafetyEvent

_MAX_PAGE = 200


@dataclass(frozen=True)
class CoachingFilters:
    status: CoachingStatus | None = None
    driver_id: uuid.UUID | None = None
    assigned_to_me: bool = False
    overdue_only: bool = False
    safety_event_id: uuid.UUID | None = None


@dataclass(frozen=True)
class CoachingSummary:
    open: int
    in_progress: int
    completed: int
    canceled: int
    overdue: int
    completed_last_30_days: int
    average_days_to_complete: float | None


@dataclass(frozen=True)
class Assignee:
    user_id: uuid.UUID
    full_name: str
    email: str
    role_key: str


class CoachingService:
    def __init__(self, session: AsyncSession, mail: MailService | None = None) -> None:
        self._db = session
        self._mail = mail

    # ------------------------------------------------------------ queries

    def _scoped(self, ctx: RequestContext, tenant_id: uuid.UUID) -> Select[tuple[CoachingAction]]:
        stmt = select(CoachingAction).where(CoachingAction.organization_id == tenant_id)
        if ctx.role == RoleKey.DRIVER and not ctx.is_platform_admin:
            # Object-level scoping for self-service drivers.
            stmt = stmt.join(Driver, Driver.id == CoachingAction.driver_id).where(
                Driver.user_id == ctx.user_id
            )
        return stmt

    async def list_actions(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        filters: CoachingFilters,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[CoachingAction], int]:
        stmt = self._scoped(ctx, tenant_id)
        now = datetime.now(UTC)
        if filters.status is not None:
            stmt = stmt.where(CoachingAction.status == filters.status.value)
        if filters.driver_id is not None:
            stmt = stmt.where(CoachingAction.driver_id == filters.driver_id)
        if filters.safety_event_id is not None:
            stmt = stmt.where(CoachingAction.safety_event_id == filters.safety_event_id)
        if filters.assigned_to_me:
            stmt = stmt.where(CoachingAction.assignee_user_id == ctx.user_id)
        if filters.overdue_only:
            stmt = stmt.where(
                CoachingAction.status.in_([s.value for s in ACTIVE_STATUSES]),
                CoachingAction.due_at < now,
            )
        total = int(
            (await self._db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        )
        rows = await self._db.execute(
            stmt.order_by(CoachingAction.due_at.asc().nullslast(), CoachingAction.created_at.desc())
            .limit(min(limit, _MAX_PAGE))
            .offset(offset)
        )
        return list(rows.scalars()), total

    async def get_action(
        self, ctx: RequestContext, tenant_id: uuid.UUID, action_id: uuid.UUID
    ) -> CoachingAction:
        action = (
            await self._db.execute(
                self._scoped(ctx, tenant_id).where(CoachingAction.id == action_id)
            )
        ).scalar_one_or_none()
        if action is None:
            raise DomainNotFoundError("Koçluk kaydı bulunamadı.")
        return action

    async def active_for_event(
        self, tenant_id: uuid.UUID, safety_event_id: uuid.UUID
    ) -> CoachingAction | None:
        return (
            await self._db.execute(
                select(CoachingAction).where(
                    CoachingAction.organization_id == tenant_id,
                    CoachingAction.safety_event_id == safety_event_id,
                    CoachingAction.status.in_([s.value for s in ACTIVE_STATUSES]),
                )
            )
        ).scalar_one_or_none()

    async def assignees(self, tenant_id: uuid.UUID) -> list[Assignee]:
        rows = await self._db.execute(
            select(User, Membership.role_key)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == tenant_id,
                Membership.status == "active",
                User.status == "active",
            )
            .order_by(User.full_name)
        )
        return [
            Assignee(user.id, user.full_name, user.email, role_key)
            for user, role_key in rows.all()
            if role_has(RoleKey(role_key), Permission.COACHING_MANAGE)
        ]

    async def summary(self, tenant_id: uuid.UUID) -> CoachingSummary:
        now = datetime.now(UTC)
        counts = {
            status: int(count)
            for status, count in (
                await self._db.execute(
                    select(CoachingAction.status, func.count())
                    .where(CoachingAction.organization_id == tenant_id)
                    .group_by(CoachingAction.status)
                )
            ).all()
        }
        overdue = int(
            (
                await self._db.execute(
                    select(func.count()).where(
                        CoachingAction.organization_id == tenant_id,
                        CoachingAction.status.in_([s.value for s in ACTIVE_STATUSES]),
                        CoachingAction.due_at < now,
                    )
                )
            ).scalar_one()
        )
        recent = await self._db.execute(
            select(
                func.count(),
                func.avg(
                    func.extract("epoch", CoachingAction.completed_at - CoachingAction.created_at)
                ),
            ).where(
                CoachingAction.organization_id == tenant_id,
                CoachingAction.status == CoachingStatus.COMPLETED.value,
                CoachingAction.completed_at >= now - timedelta(days=30),
            )
        )
        completed_recent, avg_seconds = recent.one()
        return CoachingSummary(
            open=counts.get(CoachingStatus.OPEN.value, 0),
            in_progress=counts.get(CoachingStatus.IN_PROGRESS.value, 0),
            completed=counts.get(CoachingStatus.COMPLETED.value, 0),
            canceled=counts.get(CoachingStatus.CANCELED.value, 0),
            overdue=overdue,
            completed_last_30_days=int(completed_recent or 0),
            average_days_to_complete=(
                round(float(avg_seconds) / 86400, 1) if avg_seconds is not None else None
            ),
        )

    # ------------------------------------------------------------ commands

    async def create_action(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        *,
        title: str | None,
        description: str | None = None,
        safety_event_id: uuid.UUID | None = None,
        driver_id: uuid.UUID | None = None,
        assignee_user_id: uuid.UUID | None = None,
        due_at: datetime | None = None,
        source: str = "manual",
    ) -> tuple[CoachingAction, bool]:
        """Create an action. Returns (action, created); for an event that
        already has an active action the existing one is returned unchanged."""
        event: SafetyEvent | None = None
        if safety_event_id is not None:
            event = await self._db.get(SafetyEvent, safety_event_id)
            if event is None or event.organization_id != tenant_id:
                raise DomainNotFoundError("Güvenlik olayı bulunamadı.")
            existing = await self.active_for_event(tenant_id, safety_event_id)
            if existing is not None:
                return existing, False
            driver_id = driver_id or event.driver_id

        if driver_id is not None:
            driver = await self._db.get(Driver, driver_id)
            if driver is None or driver.organization_id != tenant_id:
                raise DomainNotFoundError("Sürücü bulunamadı.")
        if assignee_user_id is not None:
            if not ctx.has_permission(Permission.COACHING_MANAGE):
                raise ValidationFailedError(
                    ["Koçluk sorumlusu atamak için koçluk yönetim yetkisi gerekir."]
                )
            await self._require_assignee(tenant_id, assignee_user_id)
        if due_at is not None and due_at.tzinfo is None:
            raise ValidationFailedError(["Termin tarihi saat dilimi içermelidir."])

        resolved_title = (title or "").strip() or self._default_title(event)
        action = CoachingAction(
            organization_id=tenant_id,
            safety_event_id=safety_event_id,
            driver_id=driver_id,
            assignee_user_id=assignee_user_id,
            created_by_user_id=ctx.user_id,
            title=resolved_title[:200],
            description=description,
            due_at=due_at or datetime.now(UTC) + timedelta(days=DEFAULT_DUE_DAYS),
        )
        try:
            async with self._db.begin_nested():
                self._db.add(action)
                await self._db.flush()
        except IntegrityError:
            # A concurrent request created the active action first.
            if safety_event_id is not None:
                existing = await self.active_for_event(tenant_id, safety_event_id)
                if existing is not None:
                    return existing, False
            raise
        await record_audit(
            self._db,
            ctx,
            action="coaching_action.created",
            resource_type="coaching_action",
            resource_id=str(action.id),
            data={
                "source": source,
                "safety_event_id": str(safety_event_id) if safety_event_id else None,
                "assignee_user_id": str(assignee_user_id) if assignee_user_id else None,
            },
        )
        if assignee_user_id is not None and assignee_user_id != ctx.user_id:
            await self._notify_assignee(tenant_id, action)
        return action, True

    async def update_action(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        action_id: uuid.UUID,
        *,
        changes: dict[str, object],
    ) -> CoachingAction:
        action = await self.get_action(ctx, tenant_id, action_id)
        if CoachingStatus(action.status) not in ACTIVE_STATUSES:
            raise DomainConflictError("Tamamlanmış veya iptal edilmiş koçluk kaydı düzenlenemez.")
        audit: dict[str, object] = {}
        if "assignee_user_id" in changes:
            assignee = changes["assignee_user_id"]
            if assignee is not None and not isinstance(assignee, uuid.UUID):
                raise ValidationFailedError(["Geçersiz koçluk sorumlusu."])
            if assignee is not None:
                await self._require_assignee(tenant_id, assignee)
            if assignee != action.assignee_user_id:
                action.assignee_user_id = assignee
                audit["assignee_user_id"] = str(assignee) if assignee else None
                if assignee is not None and assignee != ctx.user_id:
                    await self._notify_assignee(tenant_id, action)
        for field in ("title", "description", "notes", "due_at"):
            if field in changes:
                value = changes[field]
                if field == "title" and not (isinstance(value, str) and value.strip()):
                    raise ValidationFailedError(["Başlık boş olamaz."])
                if field == "due_at" and isinstance(value, datetime) and value.tzinfo is None:
                    raise ValidationFailedError(["Termin tarihi saat dilimi içermelidir."])
                setattr(action, field, value)
                audit[field] = value.isoformat() if isinstance(value, datetime) else "değişti"
        if audit:
            await record_audit(
                self._db,
                ctx,
                action="coaching_action.updated",
                resource_type="coaching_action",
                resource_id=str(action.id),
                data=audit,
            )
        return action

    async def transition(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        action_id: uuid.UUID,
        target: CoachingStatus,
        *,
        outcome: CoachingOutcome | None = None,
        outcome_notes: str | None = None,
        cancel_reason: str | None = None,
    ) -> CoachingAction:
        action = await self.get_action(ctx, tenant_id, action_id)
        current = CoachingStatus(action.status)
        if current == target:
            return action  # idempotent repeat of the same transition
        if not can_transition(current, target):
            raise DomainConflictError("Bu koçluk kaydı mevcut durumundan bu duruma geçirilemez.")
        now = datetime.now(UTC)
        if target == CoachingStatus.IN_PROGRESS:
            action.started_at = now
            if action.assignee_user_id is None:
                action.assignee_user_id = ctx.user_id
        elif target == CoachingStatus.COMPLETED:
            if outcome is None:
                raise ValidationFailedError(["Tamamlamak için bir sonuç seçin."])
            action.outcome = outcome.value
            action.outcome_notes = outcome_notes
            action.completed_at = now
            action.started_at = action.started_at or now
        elif target == CoachingStatus.CANCELED:
            if not cancel_reason or not cancel_reason.strip():
                raise ValidationFailedError(["İptal nedeni gereklidir."])
            action.cancel_reason = cancel_reason.strip()[:300]
            action.canceled_at = now
        action.status = target.value
        await record_audit(
            self._db,
            ctx,
            action=f"coaching_action.{target.value}",
            resource_type="coaching_action",
            resource_id=str(action.id),
            data={"from": current.value, "outcome": outcome.value if outcome else None},
        )
        return action

    # ------------------------------------------------------------ internals

    async def _require_assignee(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
        if not any(a.user_id == user_id for a in await self.assignees(tenant_id)):
            raise ValidationFailedError(
                ["Seçilen kullanıcı bu organizasyonda koçluk yönetim yetkisine sahip değil."]
            )

    @staticmethod
    def _default_title(event: SafetyEvent | None) -> str:
        if event is None:
            return "Sürücü koçluğu"
        try:
            label = EVENT_LABELS_TR[SafetyEventType(event.event_type)]
        except ValueError:
            label = event.event_type
        return f"{label} olayı için sürücü koçluğu"

    async def _notify_assignee(self, tenant_id: uuid.UUID, action: CoachingAction) -> None:
        if self._mail is None or action.assignee_user_id is None:
            return
        assignee = await self._db.get(User, action.assignee_user_id)
        organization = await self._db.get(Organization, tenant_id)
        if assignee is None or organization is None:
            return
        await self._mail.enqueue(
            template="coaching_assigned",
            recipient=assignee.email,
            context={
                "full_name": assignee.full_name,
                "organization_name": organization.name,
                "title": action.title,
                "due_at": action.due_at.isoformat() if action.due_at else "",
                "action_id": str(action.id),
            },
            organization_id=tenant_id,
            related=("coaching_action", str(action.id)),
        )
