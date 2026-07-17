"""Deterministic telemetry helper unit tests."""

from visionroute.domain.telemetry_rules import (
    data_quality,
    haversine_km,
    implausible_jump_kph,
)


def test_haversine_known_distance() -> None:
    # Ankara Kızılay → Çankaya, ~3 km apart.
    d = haversine_km(39.9208, 32.8541, 39.9000, 32.8600)
    assert 2.0 < d < 3.5


def test_haversine_zero() -> None:
    assert haversine_km(39.9, 32.8, 39.9, 32.8) == 0.0


def test_data_quality_perfect() -> None:
    assert data_quality(gps_hdop=1.0, satellites=12, has_speed=True) == 1.0


def test_data_quality_penalizes_poor_gps() -> None:
    score = data_quality(gps_hdop=12.0, satellites=3, has_speed=False)
    assert score < 0.2


def test_data_quality_bounded() -> None:
    score = data_quality(gps_hdop=50.0, satellites=0, has_speed=False)
    assert 0.0 <= score <= 1.0


def test_implausible_jump_detected() -> None:
    # 100 km in 60 seconds → 6000 km/h, implausible.
    assert implausible_jump_kph(100.0, 60.0) is not None
    # 0.5 km in 60 seconds → 30 km/h, fine.
    assert implausible_jump_kph(0.5, 60.0) is None
    # Zero elapsed time → cannot compute, treated as not-implausible.
    assert implausible_jump_kph(1.0, 0.0) is None
