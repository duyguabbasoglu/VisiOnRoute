"""Synthetic telemetry generation (framework-free). SYNTHETIC/DEMO ONLY.

Shared by the CLI simulator and the in-app demo seed. Every envelope produced
here carries ``data_origin="synthetic"`` and ``environment="demo"`` in its
payload so it can never masquerade as production evidence. Routes are
fictional polylines over Ankara; vehicle and driver identifiers are supplied
by the caller and must be fictional too.
"""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from visionroute.domain.ingestion import SCHEMA_VERSION

DATA_ORIGIN = "synthetic"
ENVIRONMENT = "demo"

type LatLon = tuple[float, float]

# A short synthetic route in Ankara (WGS84). Vehicles drive along a route and
# back again, so consecutive samples stay physically plausible.
ROUTE_NORTH: tuple[LatLon, ...] = (
    (39.9208, 32.8541),
    (39.9250, 32.8600),
    (39.9300, 32.8660),
    (39.9360, 32.8700),
    (39.9420, 32.8745),
    (39.9480, 32.8790),
)
ROUTE_WEST: tuple[LatLon, ...] = (
    (39.9110, 32.8100),
    (39.9095, 32.7950),
    (39.9080, 32.7800),
    (39.9065, 32.7650),
    (39.9050, 32.7500),
)
ROUTE_SOUTH: tuple[LatLon, ...] = (
    (39.9000, 32.8550),
    (39.8900, 32.8525),
    (39.8800, 32.8500),
    (39.8700, 32.8475),
    (39.8600, 32.8450),
)

_EARTH_RADIUS_M = 6_371_000.0
# ~3 m of GPS jitter; never enough to fake movement.
_JITTER_DEG = 0.00003


def haversine_m(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


def route_length_m(route: Sequence[LatLon]) -> float:
    return sum(haversine_m(a, b) for a, b in itertools.pairwise(route))


def route_position(route: Sequence[LatLon], distance_m: float) -> LatLon:
    """Position after driving ``distance_m`` along the route, bouncing back
    and forth between its ends."""
    segments = list(itertools.pairwise(route))
    lengths = [haversine_m(a, b) for a, b in segments]
    total = sum(lengths)
    remaining = distance_m % (2 * total)
    if remaining > total:  # driving back towards the start
        remaining = 2 * total - remaining
    for (start, end), length in zip(segments, lengths, strict=True):
        if remaining <= length:
            fraction = remaining / length if length else 0.0
            return (
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            )
        remaining -= length
    return route[-1]


@dataclass(frozen=True)
class Incident:
    """A deliberate, clearly-over-threshold sample injected into a trip.

    ``kind`` is one of ``harsh_braking``, ``harsh_acceleration``,
    ``harsh_cornering`` or ``speeding``. The incident fires at the first sample
    whose travelled distance reaches ``at_distance_m``; that sample is snapped
    onto exactly that distance so repeated trips hit the same road spot.
    """

    kind: str
    at_distance_m: float
    magnitude: float


@dataclass(frozen=True)
class TripPlan:
    vehicle_external_id: str
    driver_external_id: str | None
    route: tuple[LatLon, ...]
    start: datetime
    samples: int
    sample_seconds: float = 5.0
    cruise_kph: float = 55.0
    incidents: tuple[Incident, ...] = field(default=())


def build_trip_events(
    plan: TripPlan, source_key: str, rng: random.Random, *, event_prefix: str = "sim"
) -> list[dict[str, object]]:
    """Canonical ``telemetry.position`` envelopes for one synthetic trip."""
    pending = sorted(plan.incidents, key=lambda incident: incident.at_distance_m)
    events: list[dict[str, object]] = []
    speed = plan.cruise_kph
    travelled_m = 0.0
    for i in range(plan.samples):
        accel = rng.uniform(-1.2, 1.2)
        lateral = rng.uniform(-1.0, 1.0)
        speed = max(15.0, min(95.0, speed + accel * 2))
        if i > 0:
            travelled_m += speed / 3.6 * plan.sample_seconds
        if pending and travelled_m >= pending[0].at_distance_m:
            incident = pending.pop(0)
            travelled_m = incident.at_distance_m
            if incident.kind == "harsh_braking":
                accel = -incident.magnitude
            elif incident.kind == "harsh_acceleration":
                accel = incident.magnitude
            elif incident.kind == "harsh_cornering":
                lateral = incident.magnitude
            elif incident.kind == "speeding":
                speed = incident.magnitude
        lat, lon = route_position(plan.route, travelled_m)
        occurred_at = plan.start + timedelta(seconds=plan.sample_seconds * i)
        events.append(
            {
                "schema_version": SCHEMA_VERSION,
                "source": source_key,
                "event_id": f"{event_prefix}-{plan.vehicle_external_id}-"
                f"{int(occurred_at.timestamp())}-{i:03d}",
                "event_type": "telemetry.position",
                "occurred_at": occurred_at.isoformat(),
                "vehicle_external_id": plan.vehicle_external_id,
                "driver_external_id": plan.driver_external_id,
                "payload": {
                    "latitude": round(lat + rng.uniform(-_JITTER_DEG, _JITTER_DEG), 6),
                    "longitude": round(lon + rng.uniform(-_JITTER_DEG, _JITTER_DEG), 6),
                    "speed_kph": round(speed, 1),
                    "acceleration_ms2": round(accel, 2),
                    "lateral_acceleration_ms2": round(lateral, 2),
                    "heading_deg": round(rng.uniform(0, 360), 1),
                    "gps_hdop": round(rng.uniform(0.7, 1.6), 1),
                    "satellites": rng.randint(9, 14),
                    "data_origin": DATA_ORIGIN,
                    "environment": ENVIRONMENT,
                },
            }
        )
    return events
