"""Usage metering and subscription lifecycle rules (framework-free).

Billing stays manual (``billing_mode=manual_invoice``): the platform records
daily usage and enforces plan limits; invoices are issued outside the product.
No payment provider is integrated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

# metric -> (Turkish label, Turkish unit)
USAGE_METRICS: dict[str, tuple[str, str]] = {
    "vehicles": ("Araç", "adet"),
    "active_members": ("Aktif kullanıcı", "kişi"),
    "ingest_events": ("Alınan veri olayı", "adet"),
    "telemetry_points": ("Telemetri noktası", "adet"),
    "safety_events": ("Güvenlik olayı", "adet"),
    "evidence_storage_bytes": ("Kanıt depolama", "bayt"),
}
# Point-in-time values (the rest count activity inside the day).
GAUGE_METRICS = frozenset({"vehicles", "active_members", "evidence_storage_bytes"})

# Subscription states that stop growth (new vehicles, users) but never stop
# ingestion or access to existing safety data.
GROWTH_BLOCKED_STATUSES = frozenset({"past_due", "canceled"})

SUBSCRIPTION_STATUS_LABELS_TR: dict[str, str] = {
    "trial": "Deneme",
    "active": "Etkin",
    "past_due": "Ödeme bekleniyor / deneme sona erdi",
    "canceled": "İptal edildi",
}


@dataclass(frozen=True, slots=True)
class DayWindow:
    start: datetime
    end: datetime


def day_window(day: date) -> DayWindow:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return DayWindow(start=start, end=start + timedelta(days=1))


def trial_has_expired(status: str, trial_ends_at: datetime | None, now: datetime) -> bool:
    return status == "trial" and trial_ends_at is not None and trial_ends_at <= now


def effective_status(status: str, trial_ends_at: datetime | None, now: datetime) -> str:
    """Status used for enforcement, independent of scheduler lag."""
    return "past_due" if trial_has_expired(status, trial_ends_at, now) else status


def trial_days_left(status: str, trial_ends_at: datetime | None, now: datetime) -> int | None:
    if status != "trial" or trial_ends_at is None:
        return None
    return max(0, math.ceil((trial_ends_at - now).total_seconds() / 86_400))
