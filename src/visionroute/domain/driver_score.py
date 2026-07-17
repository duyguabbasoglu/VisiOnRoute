"""Transparent driver risk score (spec 12.3), framework-free.

Design principles:
- normalized by exposure (per 100 km) — never raw event counts,
- configurable severity weights, recency decay, confidence & data-quality
  weighting,
- a minimum-exposure threshold below which no score is produced,
- fully explainable (every input to the number is returned),
- no demographic or protected-attribute inputs, no hidden variables,
- versioned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

SCORE_MODEL_VERSION = 1

# Minimum distance before a score is statistically meaningful.
MIN_EXPOSURE_KM = 50.0

# Severity weights: how much each confirmed/likely event contributes.
SEVERITY_WEIGHTS: dict[str, float] = {
    "low": 1.0,
    "medium": 2.5,
    "high": 5.0,
    "critical": 9.0,
}

# Half-life for recency decay (days): older events count less.
RECENCY_HALFLIFE_DAYS = 30.0


@dataclass(frozen=True)
class ScoredEvent:
    severity: str
    confidence: float
    data_quality: float | None
    occurred_at: datetime
    review_status: str  # pending | confirmed | rejected | uncertain


@dataclass(frozen=True)
class DriverScore:
    score: float  # 0 (worst) .. 100 (best); higher is safer
    risk_index: float  # weighted events per 100 km (lower is safer)
    exposure_km: float
    event_count: int
    weighted_events: float
    model_version: int
    has_sufficient_exposure: bool
    components: dict[str, float] = field(default_factory=dict)


def _recency_factor(occurred_at: datetime, now: datetime) -> float:
    age_days = max(0.0, (now - occurred_at).total_seconds() / 86400.0)
    return float(0.5 ** (age_days / RECENCY_HALFLIFE_DAYS))


def compute_driver_score(
    events: list[ScoredEvent],
    exposure_km: float,
    *,
    now: datetime,
) -> DriverScore | None:
    """Return a driver score, or None if exposure is below the threshold.

    Rejected events are excluded. Uncertain/pending events count at reduced
    weight (their confidence already reflects uncertainty)."""
    if exposure_km < MIN_EXPOSURE_KM:
        return DriverScore(
            score=0.0,
            risk_index=0.0,
            exposure_km=round(exposure_km, 1),
            event_count=0,
            weighted_events=0.0,
            model_version=SCORE_MODEL_VERSION,
            has_sufficient_exposure=False,
        )

    weighted = 0.0
    counted = 0
    for event in events:
        if event.review_status == "rejected":
            continue
        severity_weight = SEVERITY_WEIGHTS.get(event.severity, 1.0)
        recency = _recency_factor(event.occurred_at, now)
        quality = event.data_quality if event.data_quality is not None else 1.0
        # Confirmed events count fully; unconfirmed are discounted by confidence.
        review_factor = 1.0 if event.review_status == "confirmed" else event.confidence
        weighted += severity_weight * recency * quality * review_factor
        counted += 1

    risk_index = weighted / (exposure_km / 100.0)
    # Map the unbounded risk index to a 0..100 safety score with a smooth
    # decay: risk_index 0 → 100, higher → lower. k chosen so index ~10 ≈ 50.
    score = 100.0 * math.exp(-risk_index / 14.43)
    return DriverScore(
        score=round(score, 1),
        risk_index=round(risk_index, 3),
        exposure_km=round(exposure_km, 1),
        event_count=counted,
        weighted_events=round(weighted, 3),
        model_version=SCORE_MODEL_VERSION,
        has_sufficient_exposure=True,
        components={
            "min_exposure_km": MIN_EXPOSURE_KM,
            "recency_halflife_days": RECENCY_HALFLIFE_DAYS,
        },
    )
