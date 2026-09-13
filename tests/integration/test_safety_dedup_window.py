"""Deterministic dedup-window regression tests.

Hits a few seconds apart must collapse into one event regardless of where
they fall relative to wall-clock boundaries (the previous fixed 30-second
bucket split them ~1/6 of the time), while hits further apart than the window
stay separate events.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.helpers import create_org_and_login
from visionroute.config.settings import Settings
from visionroute.worker.runner import Worker


def _h(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _setup(client: TestClient, slug: str) -> tuple[dict[str, object], str]:
    owner = create_org_and_login(client, slug, f"o@{slug}.example")
    client.post("/api/v1/vehicles", json={"external_id": "34DD001"}, headers=_h(owner))
    client.post(
        "/api/v1/integrations/data-sources",
        json={"name": "Telematik", "source_key": "t-1", "kind": "rest"},
        headers=_h(owner),
    )
    api_client = client.post(
        "/api/v1/integrations/clients", json={"name": "Cihaz"}, headers=_h(owner)
    ).json()
    api_key = client.post(
        f"/api/v1/integrations/clients/{api_client['id']}/tokens",
        json={"scopes": ["ingest:write"]},
        headers=_h(owner),
    ).json()["api_key"]
    return owner, api_key


def _brake(event_id: str, when: datetime) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "source": "t-1",
        "event_id": event_id,
        "event_type": "telemetry.position",
        "occurred_at": when.isoformat(),
        "vehicle_external_id": "34DD001",
        "payload": {
            "latitude": 39.92,
            "longitude": 32.85,
            "speed_kph": 60,
            "acceleration_ms2": -6.0,
            "gps_hdop": 1.0,
            "satellites": 12,
        },
    }


def _bucket_edge() -> datetime:
    """A timestamp 2 seconds before a 30-second clock boundary."""
    now = datetime.now(UTC) - timedelta(minutes=5)
    seconds = int(now.timestamp())
    return datetime.fromtimestamp(seconds - seconds % 30 + 28, tz=UTC)


async def _drain(settings: Settings) -> None:
    worker = Worker(settings)
    try:
        for _ in range(8):
            if await worker.run_once() == 0:
                break
    finally:
        await worker._engine.dispose()


async def test_hits_straddling_clock_boundary_collapse(
    client: TestClient, test_settings: Settings
) -> None:
    owner, api_key = _setup(client, "dedup-straddle")
    edge = _bucket_edge()
    client.post(
        "/api/v1/ingest/events",
        json={
            "source_key": "t-1",
            "events": [_brake("s1", edge), _brake("s2", edge + timedelta(seconds=5))],
        },
        headers={"X-API-Key": api_key},
    )
    await _drain(test_settings)

    listing = client.get("/api/v1/safety-events", headers=_h(owner)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["occurrence_count"] == 2


async def test_hits_outside_window_stay_separate(
    client: TestClient, test_settings: Settings
) -> None:
    owner, api_key = _setup(client, "dedup-separate")
    edge = _bucket_edge()
    client.post(
        "/api/v1/ingest/events",
        json={
            "source_key": "t-1",
            "events": [_brake("p1", edge), _brake("p2", edge + timedelta(seconds=90))],
        },
        headers={"X-API-Key": api_key},
    )
    await _drain(test_settings)

    listing = client.get("/api/v1/safety-events", headers=_h(owner)).json()
    assert listing["total"] == 2
    assert all(item["occurrence_count"] == 1 for item in listing["items"])
