"""Deterministic safety-event rules, severity, and explainability (framework-free).

Numerical telemetry classification is done here by explicit, versioned rules —
never by an LLM (spec 5.5, 12). Each rule answers the explainability questions:
what happened, when, where, on what data, which rule/threshold, measured value,
confidence, and whether human review is warranted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

RULESET_VERSION = 2
SEVERITY_FRAMEWORK_VERSION = 1


class SafetyEventType(StrEnum):
    HARSH_BRAKING = "harsh_braking"
    HARSH_ACCELERATION = "harsh_acceleration"
    HARSH_CORNERING = "harsh_cornering"
    SPEEDING = "speeding"
    GPS_ANOMALY = "gps_anomaly"


# Turkish, uncertainty-aware labels shown to users. Visual-inference events (not
# in this deterministic set) use "olasılığı/belirtisi" phrasing elsewhere.
EVENT_LABELS_TR: dict[SafetyEventType, str] = {
    SafetyEventType.HARSH_BRAKING: "Sert fren",
    SafetyEventType.HARSH_ACCELERATION: "Sert hızlanma",
    SafetyEventType.HARSH_CORNERING: "Sert viraj",
    SafetyEventType.SPEEDING: "Hız aşımı",
    SafetyEventType.GPS_ANOMALY: "GPS anomalisi",
}


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_LABELS_TR: dict[Severity, str] = {
    Severity.LOW: "Düşük",
    Severity.MEDIUM: "Orta",
    Severity.HIGH: "Yüksek",
    Severity.CRITICAL: "Kritik",
}


@dataclass(frozen=True)
class Thresholds:
    """Rule thresholds. Overridable per organization; these are the defaults."""

    harsh_braking_ms2: float = 3.5  # deceleration magnitude
    harsh_acceleration_ms2: float = 3.0
    harsh_cornering_ms2: float = 4.0  # lateral magnitude
    speeding_kph: float = 120.0  # absolute cap until per-segment limits exist
    sustained_speeding_kph: float = 130.0

    @classmethod
    def from_overrides(cls, overrides: dict[str, object] | None) -> Thresholds:
        if not overrides:
            return cls()
        base = cls()
        values: dict[str, float] = {}
        for f in (
            "harsh_braking_ms2",
            "harsh_acceleration_ms2",
            "harsh_cornering_ms2",
            "speeding_kph",
            "sustained_speeding_kph",
        ):
            raw = overrides.get(f)
            values[f] = float(raw) if isinstance(raw, int | float) else getattr(base, f)
        return cls(**values)


@dataclass(frozen=True)
class TelemetrySample:
    """Minimal telemetry needed to evaluate rules for one point."""

    speed_kph: float | None
    acceleration_ms2: float | None
    lateral_acceleration_ms2: float | None
    quality: float  # data-quality score in [0,1]


@dataclass(frozen=True)
class RuleHit:
    event_type: SafetyEventType
    severity: Severity
    confidence: float
    measured_value: float
    threshold: float
    reason_tr: str
    needs_review: bool
    extra: dict[str, float] = field(default_factory=dict)


def _magnitude_severity(ratio: float) -> Severity:
    """Map how far past threshold a value is to a severity band."""
    if ratio >= 2.0:
        return Severity.CRITICAL
    if ratio >= 1.6:
        return Severity.HIGH
    if ratio >= 1.25:
        return Severity.MEDIUM
    return Severity.LOW


def _confidence(quality: float) -> float:
    """Deterministic rules are certain about the math; confidence reflects how
    trustworthy the *input* is. Low data quality lowers confidence and flags
    the event for human review."""
    return round(max(0.3, min(1.0, quality)), 3)


def evaluate_point(sample: TelemetrySample, thresholds: Thresholds) -> list[RuleHit]:
    """Return all rule hits for one telemetry sample (usually zero or one)."""
    hits: list[RuleHit] = []
    conf = _confidence(sample.quality)
    needs_review = sample.quality < 0.6

    accel = sample.acceleration_ms2
    if accel is not None and accel <= -thresholds.harsh_braking_ms2:
        magnitude = abs(accel)
        ratio = magnitude / thresholds.harsh_braking_ms2
        hits.append(
            RuleHit(
                event_type=SafetyEventType.HARSH_BRAKING,
                severity=_magnitude_severity(ratio),
                confidence=conf,
                measured_value=round(magnitude, 2),
                threshold=thresholds.harsh_braking_ms2,
                reason_tr=(
                    f"Ölçülen yavaşlama {magnitude:.1f} m/s², eşik "
                    f"{thresholds.harsh_braking_ms2:.1f} m/s²."
                ),
                needs_review=needs_review,
            )
        )
    if accel is not None and accel >= thresholds.harsh_acceleration_ms2:
        ratio = accel / thresholds.harsh_acceleration_ms2
        hits.append(
            RuleHit(
                event_type=SafetyEventType.HARSH_ACCELERATION,
                severity=_magnitude_severity(ratio),
                confidence=conf,
                measured_value=round(accel, 2),
                threshold=thresholds.harsh_acceleration_ms2,
                reason_tr=(
                    f"Ölçülen ivme {accel:.1f} m/s², eşik "
                    f"{thresholds.harsh_acceleration_ms2:.1f} m/s²."
                ),
                needs_review=needs_review,
            )
        )

    lateral = sample.lateral_acceleration_ms2
    if lateral is not None and abs(lateral) >= thresholds.harsh_cornering_ms2:
        magnitude = abs(lateral)
        ratio = magnitude / thresholds.harsh_cornering_ms2
        hits.append(
            RuleHit(
                event_type=SafetyEventType.HARSH_CORNERING,
                severity=_magnitude_severity(ratio),
                confidence=conf,
                measured_value=round(magnitude, 2),
                threshold=thresholds.harsh_cornering_ms2,
                reason_tr=(
                    f"Ölçülen yanal ivme {magnitude:.1f} m/s², eşik "
                    f"{thresholds.harsh_cornering_ms2:.1f} m/s²."
                ),
                needs_review=needs_review,
            )
        )

    speed = sample.speed_kph
    if speed is not None and speed > thresholds.speeding_kph:
        ratio = speed / thresholds.speeding_kph
        severity = Severity.HIGH if speed >= thresholds.sustained_speeding_kph else Severity.MEDIUM
        hits.append(
            RuleHit(
                event_type=SafetyEventType.SPEEDING,
                severity=severity,
                confidence=conf,
                measured_value=round(speed, 1),
                threshold=thresholds.speeding_kph,
                reason_tr=(
                    f"Ölçülen hız {speed:.0f} km/s, eşik {thresholds.speeding_kph:.0f} km/s."
                ),
                needs_review=needs_review,
                extra={"ratio": round(ratio, 2)},
            )
        )

    return hits
