"""Deterministic safety-rule unit tests."""

from visionroute.domain.safety import (
    SafetyEventType,
    Severity,
    TelemetrySample,
    Thresholds,
    evaluate_point,
)


def _sample(**kw: float | None) -> TelemetrySample:
    base: dict[str, float | None] = {
        "speed_kph": None,
        "acceleration_ms2": None,
        "lateral_acceleration_ms2": None,
        "quality": 1.0,
    }
    base.update(kw)
    return TelemetrySample(**base)  # type: ignore[arg-type]


def test_no_hit_for_normal_driving() -> None:
    assert evaluate_point(_sample(speed_kph=80, acceleration_ms2=1.0), Thresholds()) == []


def test_harsh_braking_detected() -> None:
    hits = evaluate_point(_sample(acceleration_ms2=-4.0), Thresholds())
    assert len(hits) == 1
    assert hits[0].event_type == SafetyEventType.HARSH_BRAKING
    assert hits[0].measured_value == 4.0
    assert "yavaşlama" in hits[0].reason_tr


def test_harsh_braking_severity_scales() -> None:
    low = evaluate_point(_sample(acceleration_ms2=-3.6), Thresholds())[0]
    critical = evaluate_point(_sample(acceleration_ms2=-8.0), Thresholds())[0]
    assert low.severity == Severity.LOW
    assert critical.severity == Severity.CRITICAL


def test_harsh_acceleration_and_cornering() -> None:
    accel = evaluate_point(_sample(acceleration_ms2=3.5), Thresholds())
    assert accel[0].event_type == SafetyEventType.HARSH_ACCELERATION
    corner = evaluate_point(_sample(lateral_acceleration_ms2=-5.0), Thresholds())
    assert corner[0].event_type == SafetyEventType.HARSH_CORNERING


def test_speeding_bands() -> None:
    medium = evaluate_point(_sample(speed_kph=125), Thresholds())[0]
    high = evaluate_point(_sample(speed_kph=140), Thresholds())[0]
    assert medium.severity == Severity.MEDIUM
    assert high.severity == Severity.HIGH


def test_low_quality_lowers_confidence_and_flags_review() -> None:
    hit = evaluate_point(_sample(acceleration_ms2=-5.0, quality=0.4), Thresholds())[0]
    assert hit.confidence <= 0.4
    assert hit.needs_review is True


def test_org_threshold_overrides_apply() -> None:
    strict = Thresholds.from_overrides({"harsh_braking_ms2": 2.0})
    # -2.5 would not trip the default 3.5 threshold but trips the stricter 2.0.
    assert evaluate_point(_sample(acceleration_ms2=-2.5), Thresholds()) == []
    assert len(evaluate_point(_sample(acceleration_ms2=-2.5), strict)) == 1


def test_multiple_simultaneous_hits() -> None:
    # A single point can breach braking AND cornering.
    hits = evaluate_point(
        _sample(acceleration_ms2=-4.0, lateral_acceleration_ms2=5.0), Thresholds()
    )
    types = {h.event_type for h in hits}
    assert SafetyEventType.HARSH_BRAKING in types
    assert SafetyEventType.HARSH_CORNERING in types
