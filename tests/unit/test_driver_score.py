"""Driver risk score unit tests (transparent, exposure-normalized)."""

from datetime import UTC, datetime, timedelta

from visionroute.domain.driver_score import (
    MIN_EXPOSURE_KM,
    ScoredEvent,
    compute_driver_score,
)

NOW = datetime(2026, 7, 17, tzinfo=UTC)


def _event(severity: str, *, days_ago: int = 1, review: str = "confirmed") -> ScoredEvent:
    return ScoredEvent(
        severity=severity,
        confidence=0.9,
        data_quality=1.0,
        occurred_at=NOW - timedelta(days=days_ago),
        review_status=review,
    )


def test_insufficient_exposure_returns_no_score() -> None:
    score = compute_driver_score([_event("high")], exposure_km=10.0, now=NOW)
    assert score is not None
    assert score.has_sufficient_exposure is False
    assert score.score == 0.0


def test_clean_driver_scores_near_100() -> None:
    score = compute_driver_score([], exposure_km=500.0, now=NOW)
    assert score is not None
    assert score.has_sufficient_exposure
    assert score.score == 100.0


def test_more_severe_events_lower_the_score() -> None:
    low = compute_driver_score([_event("low")], 200.0, now=NOW)
    critical = compute_driver_score([_event("critical")], 200.0, now=NOW)
    assert low is not None and critical is not None
    assert critical.score < low.score


def test_rejected_events_excluded() -> None:
    with_rejected = compute_driver_score([_event("critical", review="rejected")], 200.0, now=NOW)
    assert with_rejected is not None
    assert with_rejected.event_count == 0
    assert with_rejected.score == 100.0


def test_recency_decay_reduces_impact_of_old_events() -> None:
    recent = compute_driver_score([_event("high", days_ago=1)], 200.0, now=NOW)
    old = compute_driver_score([_event("high", days_ago=120)], 200.0, now=NOW)
    assert recent is not None and old is not None
    assert old.score > recent.score  # older event hurts less


def test_exposure_normalization() -> None:
    # Same event count, more km → better (lower risk index).
    dense = compute_driver_score([_event("high")] * 3, 100.0, now=NOW)
    sparse = compute_driver_score([_event("high")] * 3, 1000.0, now=NOW)
    assert dense is not None and sparse is not None
    assert sparse.risk_index < dense.risk_index
    assert sparse.score > dense.score


def test_min_exposure_constant_is_respected() -> None:
    just_under = compute_driver_score([], MIN_EXPOSURE_KM - 0.1, now=NOW)
    just_over = compute_driver_score([], MIN_EXPOSURE_KM + 0.1, now=NOW)
    assert just_under is not None and not just_under.has_sufficient_exposure
    assert just_over is not None and just_over.has_sufficient_exposure
