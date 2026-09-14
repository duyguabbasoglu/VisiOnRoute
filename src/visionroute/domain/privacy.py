"""KVKK (Law No. 6698) data-subject requests and retention rules (framework-free).

- Export (Art. 11 right of access): a machine-readable ZIP of the subject's
  personal data held by one organization, available for a limited time.
- Erasure (Art. 7 deletion/anonymization): direct identifiers are removed and
  operational records (safety events, trips, coaching history) are
  pseudonymized so fleet safety statistics remain valid without identifying
  the person. Audit logs are kept as required by the data controller's legal
  obligations; they reference internal identifiers only.
- Retention: time-based deletion of raw telemetry and evidence media, bounded
  by the subscription plan and optionally shortened by the organization.

Legal review of retention periods is the data controller's responsibility;
the defaults here are product limits, not legal advice.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum


class PrivacyRequestKind(StrEnum):
    EXPORT = "export"
    ERASURE = "erasure"


class PrivacySubjectType(StrEnum):
    DRIVER = "driver"
    USER = "user"


class PrivacyRequestStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


ACTIVE_STATUSES = frozenset({PrivacyRequestStatus.PENDING, PrivacyRequestStatus.PROCESSING})

KIND_LABELS_TR: dict[str, str] = {
    PrivacyRequestKind.EXPORT: "Veri dışa aktarma",
    PrivacyRequestKind.ERASURE: "Silme / anonimleştirme",
}
SUBJECT_LABELS_TR: dict[str, str] = {
    PrivacySubjectType.DRIVER: "Sürücü",
    PrivacySubjectType.USER: "Kullanıcı",
}
STATUS_LABELS_TR: dict[str, str] = {
    PrivacyRequestStatus.PENDING: "Sırada",
    PrivacyRequestStatus.PROCESSING: "İşleniyor",
    PrivacyRequestStatus.COMPLETED: "Tamamlandı",
    PrivacyRequestStatus.FAILED: "Başarısız",
    PrivacyRequestStatus.CANCELED: "İptal edildi",
}

EXPORT_AVAILABLE_FOR = timedelta(days=7)
PROCESSING_LEASE = timedelta(minutes=15)
MAX_ATTEMPTS = 5
# Caps a single export so one request cannot exhaust worker memory; larger
# histories are truncated and the manifest says so.
EXPORT_TELEMETRY_ROW_LIMIT = 200_000

MIN_RETENTION_DAYS = 30
RETENTION_CATEGORIES: dict[str, str] = {
    "telemetry_days": "Ham telemetri (konum/hız noktaları)",
    "evidence_media_days": "Kanıt medyası (görüntü/video)",
}


def retry_delay(attempts: int) -> timedelta:
    return timedelta(minutes=min(60, 2 ** max(0, attempts - 1)))


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    telemetry_days: int
    evidence_media_days: int


def resolve_retention(plan_days: int, overrides: dict[str, object]) -> RetentionPolicy:
    """Effective retention: the organization may shorten, never exceed, the plan."""

    def pick(key: str) -> int:
        value = overrides.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return max(MIN_RETENTION_DAYS, min(value, plan_days))
        return plan_days

    return RetentionPolicy(
        telemetry_days=pick("telemetry_days"), evidence_media_days=pick("evidence_media_days")
    )


def validate_retention_overrides(values: dict[str, int | None], plan_days: int) -> list[str]:
    problems: list[str] = []
    for key, value in values.items():
        if key not in RETENTION_CATEGORIES:
            problems.append(f"Bilinmeyen saklama kategorisi: {key}.")
        elif value is not None and not (MIN_RETENTION_DAYS <= value <= plan_days):
            problems.append(
                f"{RETENTION_CATEGORIES[key]} için saklama süresi {MIN_RETENTION_DAYS} ile "
                f"{plan_days} gün (plan sınırı) arasında olmalıdır."
            )
    return problems


def driver_pseudonym(driver_id: uuid.UUID) -> tuple[str, str]:
    """(full_name, external_id) replacing a driver's identifiers after erasure."""
    short = driver_id.hex[-8:]
    return f"Silinmiş sürücü {short}", f"silindi-{short}"


def user_pseudonym(user_id: uuid.UUID) -> tuple[str, str]:
    """(full_name, email) for an erased account; ``.invalid`` never routes mail."""
    short = user_id.hex[-12:]
    return f"Silinmiş kullanıcı {short[-8:]}", f"silindi-{short}@silinmis.invalid"
