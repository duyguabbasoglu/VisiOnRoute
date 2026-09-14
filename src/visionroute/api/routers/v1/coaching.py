"""Coaching actions: list, detail, create, assign, start, complete, cancel."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.api.deps import TenantSession, get_optional_field_cipher, require_permission
from visionroute.api.errors import ForbiddenError
from visionroute.application.coaching.service import CoachingFilters, CoachingService
from visionroute.application.context import RequestContext
from visionroute.application.mail.service import MailService
from visionroute.domain.coaching import (
    OUTCOME_LABELS_TR,
    STATUS_LABELS_TR,
    CoachingOutcome,
    CoachingStatus,
    is_overdue,
)
from visionroute.domain.permissions import ROLE_LABELS_TR, Permission, RoleKey
from visionroute.domain.safety import EVENT_LABELS_TR, SafetyEventType
from visionroute.infrastructure.db.models.coaching import CoachingAction
from visionroute.infrastructure.db.models.fleet import Driver
from visionroute.infrastructure.db.models.identity import User
from visionroute.infrastructure.db.models.safety import SafetyEvent
from visionroute.infrastructure.security.crypto import FieldCipher

router = APIRouter(prefix="/coaching-actions", tags=["coaching"])

OptionalCipher = Annotated[FieldCipher | None, Depends(get_optional_field_cipher)]


def _tenant(ctx: RequestContext) -> uuid.UUID:
    if ctx.organization_id is None:  # pragma: no cover - TenantSession guarantees this
        raise ForbiddenError
    return ctx.organization_id


class CoachingActionOut(BaseModel):
    id: str
    title: str
    description: str | None
    status: str
    status_label: str
    is_overdue: bool
    safety_event_id: str | None
    event_label: str | None
    event_occurred_at: datetime | None
    driver_id: str | None
    driver_name: str | None
    assignee_user_id: str | None
    assignee_name: str | None
    created_by_name: str | None
    due_at: datetime | None
    notes: str | None
    outcome: str | None
    outcome_label: str | None
    outcome_notes: str | None
    started_at: datetime | None
    completed_at: datetime | None
    canceled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime


class CoachingActionList(BaseModel):
    items: list[CoachingActionOut]
    total: int
    limit: int
    offset: int


class CoachingCreateResponse(CoachingActionOut):
    created: bool


class CoachingCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    safety_event_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None
    assignee_user_id: uuid.UUID | None = None
    due_at: datetime | None = None


class CoachingUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)
    due_at: datetime | None = None
    assignee_user_id: uuid.UUID | None = None


class CompleteRequest(BaseModel):
    outcome: CoachingOutcome
    outcome_notes: str | None = Field(default=None, max_length=4000)


class CancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class AssigneeOut(BaseModel):
    user_id: str
    full_name: str
    email: str
    role_label: str


class CoachingSummaryOut(BaseModel):
    open: int
    in_progress: int
    completed: int
    canceled: int
    overdue: int
    completed_last_30_days: int
    average_days_to_complete: float | None


def _service(db: AsyncSession, cipher: FieldCipher | None) -> CoachingService:
    return CoachingService(db, MailService(db, cipher))


async def _render(db: AsyncSession, actions: list[CoachingAction]) -> list[CoachingActionOut]:
    driver_ids = {a.driver_id for a in actions if a.driver_id}
    user_ids = {u for a in actions for u in (a.assignee_user_id, a.created_by_user_id) if u}
    event_ids = {a.safety_event_id for a in actions if a.safety_event_id}
    drivers = (
        {
            d.id: d
            for d in (await db.execute(select(Driver).where(Driver.id.in_(driver_ids)))).scalars()
        }
        if driver_ids
        else {}
    )
    users = (
        {u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars()}
        if user_ids
        else {}
    )
    events = (
        {
            e.id: e
            for e in (
                await db.execute(select(SafetyEvent).where(SafetyEvent.id.in_(event_ids)))
            ).scalars()
        }
        if event_ids
        else {}
    )
    now = datetime.now(UTC)
    out: list[CoachingActionOut] = []
    for a in actions:
        status_value = CoachingStatus(a.status)
        event = events.get(a.safety_event_id) if a.safety_event_id else None
        driver = drivers.get(a.driver_id) if a.driver_id else None
        assignee = users.get(a.assignee_user_id) if a.assignee_user_id else None
        creator = users.get(a.created_by_user_id) if a.created_by_user_id else None
        out.append(
            CoachingActionOut(
                id=str(a.id),
                title=a.title,
                description=a.description,
                status=a.status,
                status_label=STATUS_LABELS_TR[status_value],
                is_overdue=is_overdue(status_value, a.due_at, now),
                safety_event_id=str(a.safety_event_id) if a.safety_event_id else None,
                event_label=_event_label(event.event_type) if event else None,
                event_occurred_at=event.occurred_at if event else None,
                driver_id=str(a.driver_id) if a.driver_id else None,
                driver_name=driver.full_name if driver else None,
                assignee_user_id=str(a.assignee_user_id) if a.assignee_user_id else None,
                assignee_name=assignee.full_name if assignee else None,
                created_by_name=creator.full_name if creator else None,
                due_at=a.due_at,
                notes=a.notes,
                outcome=a.outcome,
                outcome_label=OUTCOME_LABELS_TR[CoachingOutcome(a.outcome)] if a.outcome else None,
                outcome_notes=a.outcome_notes,
                started_at=a.started_at,
                completed_at=a.completed_at,
                canceled_at=a.canceled_at,
                cancel_reason=a.cancel_reason,
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
        )
    return out


def _event_label(event_type: str) -> str:
    try:
        return EVENT_LABELS_TR[SafetyEventType(event_type)]
    except ValueError:
        return event_type


@router.get("", response_model=CoachingActionList)
async def list_coaching_actions(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.COACHING_READ)],
    status_filter: Annotated[CoachingStatus | None, Query(alias="status")] = None,
    driver_id: uuid.UUID | None = None,
    safety_event_id: uuid.UUID | None = None,
    assigned_to_me: bool = False,
    overdue: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CoachingActionList:
    actions, total = await CoachingService(db).list_actions(
        ctx,
        _tenant(ctx),
        CoachingFilters(
            status=status_filter,
            driver_id=driver_id,
            assigned_to_me=assigned_to_me,
            overdue_only=overdue,
            safety_event_id=safety_event_id,
        ),
        limit=limit,
        offset=offset,
    )
    return CoachingActionList(
        items=await _render(db, actions), total=total, limit=limit, offset=offset
    )


@router.get("/summary", response_model=CoachingSummaryOut)
async def coaching_summary(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.COACHING_READ)],
) -> CoachingSummaryOut:
    summary = await CoachingService(db).summary(_tenant(ctx))
    return CoachingSummaryOut(**summary.__dict__)


@router.get("/assignees", response_model=list[AssigneeOut])
async def coaching_assignees(
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.COACHING_MANAGE)],
) -> list[AssigneeOut]:
    return [
        AssigneeOut(
            user_id=str(a.user_id),
            full_name=a.full_name,
            email=a.email,
            role_label=ROLE_LABELS_TR.get(RoleKey(a.role_key), a.role_key),
        )
        for a in await CoachingService(db).assignees(_tenant(ctx))
    ]


@router.get("/{action_id}", response_model=CoachingActionOut)
async def get_coaching_action(
    action_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.COACHING_READ)],
) -> CoachingActionOut:
    action = await CoachingService(db).get_action(ctx, _tenant(ctx), action_id)
    return (await _render(db, [action]))[0]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CoachingCreateResponse)
async def create_coaching_action(
    body: CoachingCreate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.COACHING_MANAGE)],
    cipher: OptionalCipher,
) -> CoachingCreateResponse:
    """Koçluk görevi oluşturur. Olay için zaten aktif görev varsa mevcut görev döner."""
    action, created = await _service(db, cipher).create_action(
        ctx,
        _tenant(ctx),
        title=body.title,
        description=body.description,
        safety_event_id=body.safety_event_id,
        driver_id=body.driver_id,
        assignee_user_id=body.assignee_user_id,
        due_at=body.due_at,
    )
    rendered = (await _render(db, [action]))[0]
    return CoachingCreateResponse(**rendered.model_dump(), created=created)


@router.patch("/{action_id}", response_model=CoachingActionOut)
async def update_coaching_action(
    action_id: uuid.UUID,
    body: CoachingUpdate,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.COACHING_MANAGE)],
    cipher: OptionalCipher,
) -> CoachingActionOut:
    changes = {field: getattr(body, field) for field in body.model_fields_set}
    action = await _service(db, cipher).update_action(ctx, _tenant(ctx), action_id, changes=changes)
    return (await _render(db, [action]))[0]


@router.post("/{action_id}/start", response_model=CoachingActionOut)
async def start_coaching_action(
    action_id: uuid.UUID,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.COACHING_MANAGE)],
) -> CoachingActionOut:
    action = await CoachingService(db).transition(
        ctx, _tenant(ctx), action_id, CoachingStatus.IN_PROGRESS
    )
    return (await _render(db, [action]))[0]


@router.post("/{action_id}/complete", response_model=CoachingActionOut)
async def complete_coaching_action(
    action_id: uuid.UUID,
    body: CompleteRequest,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.COACHING_MANAGE)],
) -> CoachingActionOut:
    action = await CoachingService(db).transition(
        ctx,
        _tenant(ctx),
        action_id,
        CoachingStatus.COMPLETED,
        outcome=body.outcome,
        outcome_notes=body.outcome_notes,
    )
    return (await _render(db, [action]))[0]


@router.post("/{action_id}/cancel", response_model=CoachingActionOut)
async def cancel_coaching_action(
    action_id: uuid.UUID,
    body: CancelRequest,
    db: TenantSession,
    ctx: Annotated[RequestContext, require_permission(Permission.COACHING_MANAGE)],
) -> CoachingActionOut:
    action = await CoachingService(db).transition(
        ctx, _tenant(ctx), action_id, CoachingStatus.CANCELED, cancel_reason=body.reason
    )
    return (await _render(db, [action]))[0]
