"""Canonical ingestion contract unit tests (framework-free domain)."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from visionroute.domain.ingestion import (
    EventEnvelope,
    RejectionReason,
    TelemetryPayload,
    check_timestamp,
    is_schema_supported,
)


def _valid_envelope() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "source": "telematik-1",
        "event_id": "evt-1",
        "event_type": "telemetry.position",
        "occurred_at": datetime.now(UTC).isoformat(),
        "vehicle_external_id": "34ABC123",
        "payload": {"latitude": 39.92, "longitude": 32.85, "speed_kph": 50},
    }


def test_valid_envelope_parses() -> None:
    envelope = EventEnvelope.model_validate(_valid_envelope())
    assert envelope.event_type.value == "telemetry.position"


def test_naive_timestamp_rejected() -> None:
    data = _valid_envelope()
    data["occurred_at"] = "2026-07-16T09:30:00"  # no timezone
    with pytest.raises(ValidationError, match="saat dilimi"):
        EventEnvelope.model_validate(data)


def test_extra_fields_forbidden() -> None:
    data = _valid_envelope()
    data["surprise"] = "x"
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)


def test_coordinates_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate({"latitude": 120.0, "longitude": 0.0})


def test_synthetic_markers_accepted_in_payload() -> None:
    payload = TelemetryPayload.model_validate(
        {"latitude": 39.9, "longitude": 32.8, "data_origin": "synthetic", "environment": "demo"}
    )
    assert payload.data_origin == "synthetic"


def test_timestamp_future_and_old() -> None:
    now = datetime.now(UTC)
    assert check_timestamp(now + timedelta(minutes=30), now=now) == (
        RejectionReason.TIMESTAMP_IN_FUTURE
    )
    assert check_timestamp(now - timedelta(days=5), now=now) == (RejectionReason.TIMESTAMP_TOO_OLD)
    assert check_timestamp(now - timedelta(minutes=1), now=now) is None


def test_schema_support() -> None:
    assert is_schema_supported("1.0")
    assert not is_schema_supported("2.0")
