"""Event review workflow: confirm / reject / uncertain, notes, root cause, resolution.

Every review action is audit-logged (immutable trail) and updates the event's
review lifecycle. Reviewers need the EVENTS_REVIEW permission (enforced at the
API layer). The ``kocluk_atandi`` resolution is only valid for confirmed events
and deterministically creates (or reuses) the event's active coaching action.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.audit import record_audit
from visionroute.application.coaching.service import CoachingService
from visionroute.application.context import RequestContext
from visionroute.application.errors import DomainNotFoundError, ValidationFailedError
from visionroute.domain.coaching import Resolution
from visionroute.infrastructure.db.models.coaching import CoachingAction
from visionroute.infrastructure.db.models.safety import SafetyEvent

_REVIEW_DECISIONS = {"confirmed", "rejected", "uncertain"}


@dataclass(frozen=True)
class CoachingAssignment:
    assignee_user_id: uuid.UUID | None = None
    due_at: datetime | None = None


@dataclass(frozen=True)
class ReviewOutcome:
    event: SafetyEvent
    coaching_action: CoachingAction | None


class EventReviewService:
    def __init__(self, session: AsyncSession, coaching: CoachingService | None = None) -> None:
        self._db = session
        self._coaching = coaching or CoachingService(session)

    async def review(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        *,
        decision: str,
        notes: str | None = None,
        root_cause: str | None = None,
        resolution: Resolution | None = None,
        coaching: CoachingAssignment | None = None,
    ) -> ReviewOutcome:
        if decision not in _REVIEW_DECISIONS:
            raise ValidationFailedError(
                [f"Geçersiz karar. Beklenen: {', '.join(sorted(_REVIEW_DECISIONS))}."]
            )
        if resolution == Resolution.COACHING_ASSIGNED and decision != "confirmed":
            raise ValidationFailedError(["Koçluk yalnızca onaylanan olaylar için atanabilir."])
        event = await self._db.get(SafetyEvent, event_id)
        if event is None or event.organization_id != tenant_id:
            raise DomainNotFoundError("Güvenlik olayı bulunamadı.")

        event.review_status = decision
        event.reviewer_user_id = ctx.user_id
        event.reviewed_at = datetime.now(UTC)
        if notes is not None:
            event.reviewer_notes = notes
        if root_cause is not None:
            event.root_cause = root_cause
        if resolution is not None:
            event.resolution = resolution.value

        action: CoachingAction | None = None
        if resolution == Resolution.COACHING_ASSIGNED:
            action, _created = await self._coaching.create_action(
                ctx,
                tenant_id,
                title=None,
                description=notes,
                safety_event_id=event.id,
                assignee_user_id=coaching.assignee_user_id if coaching else None,
                due_at=coaching.due_at if coaching else None,
                source="event_review",
            )

        await record_audit(
            self._db,
            ctx,
            action="safety_event.reviewed",
            resource_type="safety_event",
            resource_id=str(event.id),
            data={
                "decision": decision,
                "resolution": resolution.value if resolution else None,
                "coaching_action_id": str(action.id) if action else None,
            },
        )
        return ReviewOutcome(event=event, coaching_action=action)
