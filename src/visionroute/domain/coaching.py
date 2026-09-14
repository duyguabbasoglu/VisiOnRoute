"""Coaching workflow rules (framework-free).

Lifecycle: open → in_progress → completed, with cancel allowed from any
active state. Completed and canceled actions are terminal (history is kept,
a new action is created instead of reopening). An event can have at most one
*active* coaching action.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum


class CoachingStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELED = "canceled"


ACTIVE_STATUSES = frozenset({CoachingStatus.OPEN, CoachingStatus.IN_PROGRESS})

STATUS_LABELS_TR: dict[CoachingStatus, str] = {
    CoachingStatus.OPEN: "Açık",
    CoachingStatus.IN_PROGRESS: "Devam ediyor",
    CoachingStatus.COMPLETED: "Tamamlandı",
    CoachingStatus.CANCELED: "İptal edildi",
}


class CoachingOutcome(StrEnum):
    COACHED = "coached"
    NO_ACTION_NEEDED = "no_action_needed"
    ESCALATED = "escalated"
    DRIVER_UNAVAILABLE = "driver_unavailable"


OUTCOME_LABELS_TR: dict[CoachingOutcome, str] = {
    CoachingOutcome.COACHED: "Sürücüyle görüşme yapıldı",
    CoachingOutcome.NO_ACTION_NEEDED: "İşlem gerekmedi",
    CoachingOutcome.ESCALATED: "Üst yönetime iletildi",
    CoachingOutcome.DRIVER_UNAVAILABLE: "Sürücüye ulaşılamadı",
}

_TRANSITIONS: dict[CoachingStatus, frozenset[CoachingStatus]] = {
    CoachingStatus.OPEN: frozenset(
        {CoachingStatus.IN_PROGRESS, CoachingStatus.COMPLETED, CoachingStatus.CANCELED}
    ),
    CoachingStatus.IN_PROGRESS: frozenset({CoachingStatus.COMPLETED, CoachingStatus.CANCELED}),
    CoachingStatus.COMPLETED: frozenset(),
    CoachingStatus.CANCELED: frozenset(),
}

DEFAULT_DUE_DAYS = 7


def can_transition(current: CoachingStatus, target: CoachingStatus) -> bool:
    return target in _TRANSITIONS[current]


def is_overdue(status: CoachingStatus, due_at: datetime | None, now: datetime) -> bool:
    return status in ACTIVE_STATUSES and due_at is not None and due_at < now


class Resolution(StrEnum):
    """How a reviewed safety event was resolved."""

    COACHING_ASSIGNED = "kocluk_atandi"
    DRIVER_INFORMED = "surucu_bilgilendirildi"
    NO_ACTION_REQUIRED = "islem_gerekmedi"
    EQUIPMENT_CHECK = "ekipman_kontrolu"
    FALSE_ALARM = "yanlis_alarm"


RESOLUTION_LABELS_TR: dict[Resolution, str] = {
    Resolution.COACHING_ASSIGNED: "Koçluk atandı",
    Resolution.DRIVER_INFORMED: "Sürücü bilgilendirildi",
    Resolution.NO_ACTION_REQUIRED: "İşlem gerekmedi",
    Resolution.EQUIPMENT_CHECK: "Ekipman/cihaz kontrolü",
    Resolution.FALSE_ALARM: "Yanlış alarm",
}
