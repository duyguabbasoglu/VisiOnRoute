"""Event review workflow: confirm / reject / uncertain, notes, resolution.

Every review action is audit-logged (immutable trail) and updates the event's
review lifecycle. Reviewers need the EVENTS_REVIEW permission (enforced at the
API layer)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.errors import DomainNotFoundError, ValidationFailedError
from visionroute.infrastructure.db.models.safety import SafetyEvent

_REVIEW_DECISIONS = {"confirmed", "rejected", "uncertain"}


class EventReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def review(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        *,
        decision: str,
        notes: str | None = None,
        root_cause: str | None = None,
        resolution: str | None = None,
    ) -> SafetyEvent:
        if decision not in _REVIEW_DECISIONS:
            raise ValidationFailedError(
                [f"Geçersiz karar. Beklenen: {', '.join(sorted(_REVIEW_DECISIONS))}."]
            )
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
            event.resolution = resolution

        await record_audit(
            self._db,
            ctx,
            action="safety_event.reviewed",
            resource_type="safety_event",
            resource_id=str(event.id),
            data={"decision": decision, "resolution": resolution},
        )
        return event
