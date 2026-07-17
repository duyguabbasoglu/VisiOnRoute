"""Canonical ingestion contract (framework-free).

This is the public data contract customers integrate against. It is versioned
(``schema_version``) and validated strictly. Numerical telemetry is never
interpreted by an LLM — only by deterministic rules downstream.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "1.0"

# How far into the future a timestamp may be before it's rejected as bogus.
_MAX_CLOCK_SKEW = timedelta(minutes=5)
# Oldest event we accept through the live path (older → historical import only).
_MAX_AGE = timedelta(days=3)


class EventType(StrEnum):
    """Accepted canonical event types. Telemetry positions drive the safety
    engine; explicit provider events are stored and may raise events too."""

    TELEMETRY_POSITION = "telemetry.position"
    TRIP_START = "trip.start"
    TRIP_END = "trip.end"
    DEVICE_STATUS = "device.status"
    PROVIDER_EVENT = "provider.event"  # provider-detected event (e.g. harsh braking)


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class TelemetryPayload(BaseModel):
    """Position + kinematics. Fields are optional because providers differ;
    the safety engine degrades gracefully when inputs are missing."""

    model_config = {"extra": "forbid"}

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    speed_kph: float | None = Field(default=None, ge=0.0, le=400.0)
    heading_deg: float | None = Field(default=None, ge=0.0, le=360.0)
    acceleration_ms2: float | None = Field(default=None, ge=-50.0, le=50.0)
    # Lateral acceleration for cornering (signed).
    lateral_acceleration_ms2: float | None = Field(default=None, ge=-50.0, le=50.0)
    odometer_km: float | None = Field(default=None, ge=0.0)
    gps_hdop: float | None = Field(default=None, ge=0.0, le=100.0)
    satellites: int | None = Field(default=None, ge=0, le=64)
    # Provenance markers. Real integrations omit these; the demo simulator sets
    # data_origin="synthetic", environment="demo" so synthetic data is never
    # mistaken for production evidence.
    data_origin: str | None = Field(default=None, max_length=20)
    environment: str | None = Field(default=None, max_length=20)


class EventEnvelope(BaseModel):
    """The canonical envelope every ingestion path produces."""

    model_config = {"extra": "forbid"}

    schema_version: str = Field(default=SCHEMA_VERSION)
    source: str = Field(min_length=1, max_length=120)
    event_id: str = Field(min_length=1, max_length=200)
    event_type: EventType
    occurred_at: datetime
    received_at: datetime | None = None
    vehicle_external_id: str = Field(min_length=1, max_length=120)
    driver_external_id: str | None = Field(default=None, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    # Optional provenance/signature block (verified by the ingestion adapter).
    signature: dict[str, Any] | None = None

    @field_validator("occurred_at", "received_at")
    @classmethod
    def _require_tz(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            msg = "Zaman damgaları saat dilimi bilgisi içermelidir (UTC önerilir)."
            raise ValueError(msg)
        return value


class RejectionReason(StrEnum):
    SCHEMA_VERSION_UNSUPPORTED = "schema_version_unsupported"
    INVALID_PAYLOAD = "invalid_payload"
    TIMESTAMP_IN_FUTURE = "timestamp_in_future"
    TIMESTAMP_TOO_OLD = "timestamp_too_old"
    UNKNOWN_VEHICLE = "unknown_vehicle"
    COORDINATES_OUT_OF_RANGE = "coordinates_out_of_range"


# Turkish, customer-facing explanations for each rejection reason.
REJECTION_MESSAGES_TR: dict[RejectionReason, str] = {
    RejectionReason.SCHEMA_VERSION_UNSUPPORTED: "Desteklenmeyen şema sürümü.",
    RejectionReason.INVALID_PAYLOAD: "Veri yükü doğrulanamadı.",
    RejectionReason.TIMESTAMP_IN_FUTURE: "Olay zamanı gelecekte görünüyor.",
    RejectionReason.TIMESTAMP_TOO_OLD: "Olay zamanı canlı akış için çok eski.",
    RejectionReason.UNKNOWN_VEHICLE: "Araç dış kimliği tanımlı değil.",
    RejectionReason.COORDINATES_OUT_OF_RANGE: "Konum koordinatları geçerli aralık dışında.",
}


def check_timestamp(
    occurred_at: datetime, *, now: datetime | None = None
) -> RejectionReason | None:
    """Deterministic clock-sanity check used by the ingestion pipeline."""
    now = now or datetime.now(UTC)
    if occurred_at > now + _MAX_CLOCK_SKEW:
        return RejectionReason.TIMESTAMP_IN_FUTURE
    if occurred_at < now - _MAX_AGE:
        return RejectionReason.TIMESTAMP_TOO_OLD
    return None


def is_schema_supported(schema_version: str) -> bool:
    return schema_version == SCHEMA_VERSION
