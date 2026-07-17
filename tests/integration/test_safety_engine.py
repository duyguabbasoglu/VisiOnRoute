"""End-to-end M6: telemetry with a harsh event → safety event with explanation."""

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
        "/api/v1/integrations/clients", json={"name": "Cihaz"}, headers=_h(owner)
    ).json()
    token = client.post(
        f"/api/v1/integrations/clients/{api_client['id']}/tokens",
        json={"scopes": ["ingest:write"]},
        headers=_h(owner),
    ).json()
    return owner, token["api_key"]


def _point(eid: str, when: datetime, *, accel: float | None = None, speed: float = 50.0) -> dict:
    payload: dict[str, object] = {
        "latitude": 39.92,
        "longitude": 32.85,
        "speed_kph": speed,
        "gps_hdop": 1.0,
        "satellites": 12,
    }
    if accel is not None:
        payload["acceleration_ms2"] = accel
    return {
        "schema_version": "1.0",
        "source": "t-1",
        "event_id": eid,
        "event_type": "telemetry.position",
        "occurred_at": when.isoformat(),
        "vehicle_external_id": "34ABC123",
        "payload": payload,
    }


async def _drain(settings: Settings) -> None:
    worker = Worker(settings)
    for _ in range(6):
        if await worker.run_once() == 0:
            break
    await worker._engine.dispose()


async def test_harsh_braking_creates_explained_event(
    client: TestClient, test_settings: Settings
) -> None:
    owner, api_key = _setup(client, "safety-brake")
    base = datetime.now(UTC) - timedelta(minutes=5)
    events = [
        _point("s1", base),
        _point("s2", base + timedelta(seconds=30), accel=-6.5, speed=70),
        _point("s3", base + timedelta(seconds=60)),
    ]
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": events},
        headers={"X-API-Key": api_key},
    )
    await _drain(test_settings)

    listing = client.get("/api/v1/safety-events", headers=_h(owner)).json()
    assert listing["total"] == 1
    event = listing["items"][0]
    assert event["event_type"] == "harsh_braking"
    assert event["event_label"] == "Sert fren"
    assert event["severity"] in {"high", "critical"}

    detail = client.get(f"/api/v1/safety-events/{event['id']}", headers=_h(owner)).json()
    exp = detail["explanation"]
    assert exp["ne_oldu"] == "Sert fren"
    assert exp["olculen_deger"] == 6.5
    assert exp["esik"] == 3.5
    assert 0.0 <= exp["guven_seviyesi"] <= 1.0
    assert detail["ruleset_version"] >= 1
    # Telemetry-window evidence is attached.
    assert any(ev["kind"] == "telemetry_window" for ev in detail["evidence"])


async def test_dedup_collapses_repeated_hits(client: TestClient, test_settings: Settings) -> None:
    owner, api_key = _setup(client, "safety-dedup")
    base = datetime.now(UTC) - timedelta(minutes=5)
    # Two harsh-braking points within the same 30s dedup bucket.
    events = [
        _point("d1", base, accel=-5.0),
        _point("d2", base + timedelta(seconds=5), accel=-5.5),
    ]
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": events},
        headers={"X-API-Key": api_key},
    )
    await _drain(test_settings)

    listing = client.get("/api/v1/safety-events", headers=_h(owner)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["occurrence_count"] == 2


async def test_safety_events_tenant_isolated(client: TestClient, test_settings: Settings) -> None:
    owner_a, key_a = _setup(client, "safety-iso-a")
    owner_b, _key_b = _setup(client, "safety-iso-b")
    base = datetime.now(UTC) - timedelta(minutes=5)
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": [_point("i1", base, accel=-6.0)]},
        headers={"X-API-Key": key_a},
    )
    await _drain(test_settings)

    assert client.get("/api/v1/safety-events", headers=_h(owner_a)).json()["total"] == 1
    assert client.get("/api/v1/safety-events", headers=_h(owner_b)).json()["total"] == 0


async def test_normal_driving_produces_no_events(
    client: TestClient, test_settings: Settings
) -> None:
    owner, api_key = _setup(client, "safety-normal")
    base = datetime.now(UTC) - timedelta(minutes=5)
    # Gentle braking (-2.5 m/s²) is below the default 3.5 threshold → no event.
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": [_point("t1", base, accel=-2.5)]},
        headers={"X-API-Key": api_key},
    )
    await _drain(test_settings)
    assert client.get("/api/v1/safety-events", headers=_h(owner)).json()["total"] == 0
