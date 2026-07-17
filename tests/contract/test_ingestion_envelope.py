"""Contract tests for the public ingestion envelope.

These pin the wire format customers integrate against. A breaking change here
means a breaking change for every integrator — treat failures as intentional
contract decisions, not test noise.
"""

from datetime import UTC, datetime

from visionroute.domain.ingestion import SCHEMA_VERSION, EventEnvelope, EventType


def test_schema_version_is_stable() -> None:
    assert SCHEMA_VERSION == "1.0"


def test_documented_event_types_exist() -> None:
    # The public contract advertises exactly these event types.
    assert {t.value for t in EventType} == {
        "telemetry.position",
        "trip.start",
        "trip.end",
        "device.status",
        "provider.event",
    }


def test_minimal_valid_envelope_round_trips() -> None:
    raw = {
        "schema_version": "1.0",
        "source": "provider-x",
        "event_id": "abc-123",
        "event_type": "telemetry.position",
        "occurred_at": datetime.now(UTC).isoformat(),
        "vehicle_external_id": "34XYZ99",
        "payload": {"latitude": 41.0, "longitude": 29.0},
    }
    envelope = EventEnvelope.model_validate(raw)
    dumped = envelope.model_dump(mode="json")
    # Required public fields must survive a round trip.
    for field in (
        "schema_version",
        "source",
        "event_id",
        "event_type",
        "occurred_at",
        "vehicle_external_id",
        "payload",
    ):
        assert field in dumped


def test_received_at_and_signature_are_optional() -> None:
    raw = {
        "source": "p",
        "event_id": "e",
        "event_type": "device.status",
        "occurred_at": datetime.now(UTC).isoformat(),
        "vehicle_external_id": "v",
    }
    envelope = EventEnvelope.model_validate(raw)
    assert envelope.received_at is None
    assert envelope.signature is None
