"""Deterministic telemetry helpers: distance, data-quality scoring, trip gaps.

Framework-free and pure so they can be unit-tested and reused by the worker,
the safety engine, and analytics without a database.
"""

from __future__ import annotations

import math
from datetime import timedelta

# A trip is considered ended if no telemetry arrives for this long.
TRIP_IDLE_GAP = timedelta(minutes=15)
# Feeds quieter than this are flagged stale on the live map.
STALE_FEED_AFTER = timedelta(minutes=5)

_EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in kilometers."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def data_quality(
    *,
    gps_hdop: float | None,
    satellites: int | None,
    has_speed: bool,
) -> float:
    """Score telemetry input quality in [0, 1].

    Poor GPS geometry (high HDOP), few satellites, or missing kinematics lower
    the score; the driver-risk model penalizes low-quality inputs (spec 12.3).
    """
    score = 1.0
    if gps_hdop is not None:
        if gps_hdop > 10:
            score -= 0.5
        elif gps_hdop > 5:
            score -= 0.25
    if satellites is not None:
        if satellites < 4:
            score -= 0.4
        elif satellites < 6:
            score -= 0.15
    if not has_speed:
        score -= 0.1
    return max(0.0, min(1.0, round(score, 3)))


def implausible_jump_kph(distance_km: float, seconds: float) -> float | None:
    """Return the implied speed (km/h) if a position jump is physically
    implausible (> 400 km/h), else None. Used to flag GPS anomalies."""
    if seconds <= 0:
        return None
    implied = distance_km / (seconds / 3600.0)
    return implied if implied > 400.0 else None
