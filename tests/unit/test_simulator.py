"""The demo telemetry simulator produces synthetic, physically plausible samples."""

import itertools
from datetime import UTC, datetime

from visionroute.cli.simulate import SAMPLE_SECONDS, _build_events, haversine_m


def test_samples_are_synthetic_ordered_and_plausible() -> None:
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    events = _build_events(
        "34ABC123", "SUR-001", "telematik-1", 40, inject_harsh_brake=True, now=now
    )

    times = [datetime.fromisoformat(str(event["occurred_at"])) for event in events]
    assert times == sorted(times)
    assert len(set(times)) == len(times)
    assert times[-1] == now

    positions: list[tuple[float, float]] = []
    harsh = 0
    for event in events:
        payload = event["payload"]
        assert isinstance(payload, dict)
        assert payload["data_origin"] == "synthetic"
        assert payload["environment"] == "demo"
        positions.append((float(payload["latitude"]), float(payload["longitude"])))
        if float(payload["acceleration_ms2"]) <= -6.0:
            harsh += 1
    assert harsh == 1

    # 120 km/h for one sampling interval plus GPS jitter bounds every step.
    max_step_m = 120 / 3.6 * SAMPLE_SECONDS + 10
    for previous, current in itertools.pairwise(positions):
        assert haversine_m(previous, current) <= max_step_m
    assert haversine_m(positions[0], positions[-1]) > 100
