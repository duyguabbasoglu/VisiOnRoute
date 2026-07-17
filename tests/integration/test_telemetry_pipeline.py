"""End-to-end M5: ingest → worker → telemetry points → trips → live/trail API."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.helpers import create_org_and_login
from visionroute.config.settings import Settings
from visionroute.worker.runner import Worker


def _h(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _setup(client: TestClient, slug: str) -> tuple[dict[str, object], str]:
    owner = create_org_and_login(client, slug, f"o@{slug}.example")
    client.post("/api/v1/vehicles", json={"external_id": "34ABC123"}, headers=_h(owner))
    client.post(
        "/api/v1/integrations/data-sources",
        json={"name": "Telematik", "source_key": "t-1", "kind": "rest"},
        headers=_h(owner),
    )
    api_client = client.post(
        "/api/v1/integrations/clients", json={"name": "Cihaz İstemci"}, headers=_h(owner)
    ).json()
    token = client.post(
        f"/api/v1/integrations/clients/{api_client['id']}/tokens",
        json={"scopes": ["ingest:write"]},
        headers=_h(owner),
    ).json()
    return owner, token["api_key"]


def _point(event_id: str, lat: float, lon: float, when: datetime, speed: float = 50.0) -> dict:
    return {
        "schema_version": "1.0",
        "source": "t-1",
        "event_id": event_id,
        "event_type": "telemetry.position",
        "occurred_at": when.isoformat(),
        "vehicle_external_id": "34ABC123",
        "payload": {
            "latitude": lat,
            "longitude": lon,
            "speed_kph": speed,
            "gps_hdop": 1.0,
            "satellites": 12,
        },
    }


async def _drain_worker(test_settings: Settings) -> int:
    worker = Worker(test_settings)
    total = 0
    for _ in range(5):
        handled = await worker.run_once()
        total += handled
        if handled == 0:
            break
    await worker._engine.dispose()
    return total


async def test_worker_builds_telemetry_and_trip(
    client: TestClient, test_settings: Settings
) -> None:
    owner, api_key = _setup(client, "tel-pipeline")
    base = datetime.now(UTC) - timedelta(minutes=5)
    events = [
        _point("p1", 39.9208, 32.8541, base),
        _point("p2", 39.9250, 32.8600, base + timedelta(seconds=60)),
        _point("p3", 39.9300, 32.8660, base + timedelta(seconds=120), speed=70.0),
    ]
    resp = client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": events},
        headers={"X-API-Key": api_key},
    )
    assert resp.json()["accepted"] == 3

    handled = await _drain_worker(test_settings)
    assert handled >= 3

    # Live positions show one active vehicle with the latest coordinate.
    live = client.get("/api/v1/operations/live", headers=_h(owner)).json()
    assert len(live) == 1
    assert live[0]["latitude"] == 39.9300
    assert live[0]["max_speed_kph"] == 70.0

    # A trip was created with 3 points and non-zero distance.
    trips = client.get("/api/v1/trips", headers=_h(owner)).json()
    assert len(trips) == 1
    trip = trips[0]
    assert trip["point_count"] == 3
    assert trip["distance_km"] > 0

    # The trail returns points in order.
    trail = client.get(f"/api/v1/trips/{trip['id']}/trail", headers=_h(owner)).json()
    assert len(trail) == 3
    assert trail[0]["occurred_at"] < trail[-1]["occurred_at"]
    assert all(0.0 <= p["quality"] <= 1.0 for p in trail)


async def test_idle_gap_splits_trips(client: TestClient, test_settings: Settings) -> None:
    owner, api_key = _setup(client, "tel-gap")
    base = datetime.now(UTC) - timedelta(hours=2)
    # Two clusters separated by > 15 min idle gap → two trips.
    events = [
        _point("g1", 39.92, 32.85, base),
        _point("g2", 39.93, 32.86, base + timedelta(seconds=60)),
        _point("g3", 39.95, 32.90, base + timedelta(minutes=40)),
    ]
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": events},
        headers={"X-API-Key": api_key},
    )
    await _drain_worker(test_settings)

    trips = client.get("/api/v1/trips", headers=_h(owner)).json()
    assert len(trips) == 2
    statuses = {t["status"] for t in trips}
    assert "completed" in statuses  # the earlier trip was closed by the gap


async def test_telemetry_is_tenant_isolated(client: TestClient, test_settings: Settings) -> None:
    owner_a, key_a = _setup(client, "tel-iso-a")
    owner_b, _key_b = _setup(client, "tel-iso-b")
    base = datetime.now(UTC) - timedelta(minutes=3)
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": [_point("x1", 39.92, 32.85, base)]},
        headers={"X-API-Key": key_a},
    )
    await _drain_worker(test_settings)

    # Tenant A sees its live vehicle; tenant B sees none.
    assert len(client.get("/api/v1/operations/live", headers=_h(owner_a)).json()) == 1
    assert len(client.get("/api/v1/operations/live", headers=_h(owner_b)).json()) == 0
