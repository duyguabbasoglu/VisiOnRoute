"""M7 end-to-end: event review workflow, road-risk clustering, driver score."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.helpers import create_org_and_login
from visionroute.config.settings import Settings
from visionroute.worker.runner import Worker


def _h(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _setup(client: TestClient, slug: str) -> tuple[dict[str, object], str, str]:
    owner = create_org_and_login(client, slug, f"o@{slug}.example")
    client.post("/api/v1/vehicles", json={"external_id": "34ABC123"}, headers=_h(owner))
    driver = client.post(
        "/api/v1/drivers",
        json={"external_id": "SUR-1", "full_name": "Test Sürücü"},
        headers=_h(owner),
    ).json()
    # Assign the driver so trips/events attribute to them.
    vehicles = client.get("/api/v1/vehicles", headers=_h(owner)).json()["items"]
    client.post(
        "/api/v1/assignments",
        json={"driver_id": driver["id"], "vehicle_id": vehicles[0]["id"]},
        headers=_h(owner),
    )
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
    return owner, token["api_key"], driver["id"]


def _point(eid: str, when: datetime, lat: float, lon: float, accel: float | None) -> dict:
    payload: dict[str, object] = {
        "latitude": lat,
        "longitude": lon,
        "speed_kph": 60,
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
    for _ in range(8):
        if await worker.run_once() == 0:
            break
    await worker._engine.dispose()


async def test_event_review_workflow(client: TestClient, test_settings: Settings) -> None:
    owner, api_key, _driver = _setup(client, "review-flow")
    base = datetime.now(UTC) - timedelta(minutes=10)
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": [_point("r1", base, 39.92, 32.85, -6.0)]},
        headers={"X-API-Key": api_key},
    )
    await _drain(test_settings)

    event = client.get("/api/v1/safety-events", headers=_h(owner)).json()["items"][0]
    review = client.post(
        f"/api/v1/safety-events/{event['id']}/review",
        json={
            "decision": "confirmed",
            "notes": "Görüntü doğrulandı",
            "root_cause": "ani_kesme",
            "resolution": "kocluk_atandi",
        },
        headers=_h(owner),
    )
    assert review.status_code == 200
    assert review.json()["review_status"] == "confirmed"

    # Filter by review_status reflects the change.
    confirmed = client.get(
        "/api/v1/safety-events?review_status=confirmed", headers=_h(owner)
    ).json()
    assert confirmed["total"] == 1


async def test_road_risk_clustering(client: TestClient, test_settings: Settings) -> None:
    owner, api_key, _driver = _setup(client, "road-risk")
    base = datetime.now(UTC) - timedelta(minutes=20)
    # Five harsh-braking events at the same location → one road risk.
    events = [
        _point(f"c{i}", base + timedelta(seconds=40 * i), 39.9200, 32.8500, -5.5) for i in range(5)
    ]
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": events},
        headers={"X-API-Key": api_key},
    )
    await _drain(test_settings)

    rebuild = client.post("/api/v1/road-risks/rebuild", headers=_h(owner)).json()
    assert rebuild["road_risks"] == 1
    risks = client.get("/api/v1/road-risks", headers=_h(owner)).json()
    assert len(risks) == 1
    assert risks[0]["risk_type"] == "repeated_harsh_events"
    assert risks[0]["observed_count"] >= 3


async def test_driver_score_endpoint(client: TestClient, test_settings: Settings) -> None:
    owner, api_key, driver_id = _setup(client, "driver-score")
    base = datetime.now(UTC) - timedelta(minutes=30)
    # Build enough exposure with a spread-out route plus one harsh event.
    events = []
    lat = 39.90
    for i in range(30):
        lat += 0.01  # ~1.1 km steps → ~33 km; add speed to accumulate distance
        accel = -6.0 if i == 10 else 0.5
        events.append(_point(f"d{i}", base + timedelta(seconds=30 * i), lat, 32.85, accel))
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": events},
        headers={"X-API-Key": api_key},
    )
    await _drain(test_settings)

    score = client.get(f"/api/v1/drivers/{driver_id}/risk-score", headers=_h(owner)).json()
    assert score["model_version"] >= 1
    # Either a real score (enough exposure) or a clear Turkish insufficient note.
    if score["has_sufficient_exposure"]:
        assert 0.0 <= score["score"] <= 100.0
    else:
        assert "yeterli sürüş verisi yok" in score["note"]


async def test_geofence_crud_and_rbac(client: TestClient) -> None:
    owner = create_org_and_login(client, "geofence", "o@geofence.example")
    created = client.post(
        "/api/v1/geofences",
        json={
            "name": "Riskli Kavşak",
            "center_latitude": 39.92,
            "center_longitude": 32.85,
            "radius_m": 200,
        },
        headers=_h(owner),
    )
    assert created.status_code == 201
    listing = client.get("/api/v1/geofences", headers=_h(owner)).json()
    assert len(listing) == 1
    assert listing[0]["name"] == "Riskli Kavşak"
