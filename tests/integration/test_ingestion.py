"""Ingestion pipeline: API-key auth, validation, idempotency, quarantine, health."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.helpers import create_org_and_login


def _h(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _setup_ingest(client: TestClient, slug: str) -> tuple[str, str]:
    """Register org, a vehicle, a data source and an ingest API key.
    Returns (api_key, source_key)."""
    owner = create_org_and_login(client, slug, f"o@{slug}.example")
    client.post("/api/v1/vehicles", json={"external_id": "34ABC123"}, headers=_h(owner))
    source = client.post(
        "/api/v1/integrations/data-sources",
        json={"name": "Telematik", "source_key": "telematik-1", "kind": "rest"},
        headers=_h(owner),
    )
    assert source.status_code == 201, source.text
    api_client = client.post(
        "/api/v1/integrations/clients",
        json={"name": "Saha Cihazı"},
        headers=_h(owner),
    ).json()
    token = client.post(
        f"/api/v1/integrations/clients/{api_client['id']}/tokens",
        json={"scopes": ["ingest:write"]},
        headers=_h(owner),
    ).json()
    return token["api_key"], "telematik-1"


def _event(event_id: str, **payload: object) -> dict[str, object]:
    base = {"latitude": 39.92, "longitude": 32.85, "speed_kph": 50}
    base.update(payload)
    return {
        "schema_version": "1.0",
        "source": "telematik-1",
        "event_id": event_id,
        "event_type": "telemetry.position",
        "occurred_at": datetime.now(UTC).isoformat(),
        "vehicle_external_id": "34ABC123",
        "payload": base,
    }


def test_ingest_requires_valid_api_key(client: TestClient) -> None:
    api_key, source_key = _setup_ingest(client, "ingest-auth")

    # No key.
    no_key = client.post(
        "/api/v1/ingest/events", json={"source_key": source_key, "events": [_event("e1")]}
    )
    assert no_key.status_code == 401

    # Bad key.
    bad = client.post(
        "/api/v1/ingest/events",
        json={"source_key": source_key, "events": [_event("e1")]},
        headers={"X-API-Key": "vrk_gecersiz"},
    )
    assert bad.status_code == 401

    # Valid key.
    ok = client.post(
        "/api/v1/ingest/events",
        json={"source_key": source_key, "events": [_event("e1")]},
        headers={"X-API-Key": api_key},
    )
    assert ok.status_code == 200
    assert ok.json()["accepted"] == 1


def test_idempotent_dedup(client: TestClient) -> None:
    api_key, source_key = _setup_ingest(client, "ingest-dedup")
    headers = {"X-API-Key": api_key}
    payload = {"source_key": source_key, "events": [_event("dup-1")]}

    first = client.post("/api/v1/ingest/events", json=payload, headers=headers).json()
    second = client.post("/api/v1/ingest/events", json=payload, headers=headers).json()
    assert first["accepted"] == 1
    assert second["accepted"] == 0
    assert second["duplicates"] == 1


def test_quarantine_reasons(client: TestClient) -> None:
    api_key, source_key = _setup_ingest(client, "ingest-karantina")
    headers = {"X-API-Key": api_key}

    # Unknown vehicle.
    unknown = _event("q1")
    unknown["vehicle_external_id"] = "YOK-999"
    r1 = client.post(
        "/api/v1/ingest/events",
        json={"source_key": source_key, "events": [unknown]},
        headers=headers,
    ).json()
    assert r1["quarantined"] == 1
    assert r1["outcomes"][0]["rejection_reason"] == "unknown_vehicle"

    # Future timestamp.
    future = _event("q2")
    future["occurred_at"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    r2 = client.post(
        "/api/v1/ingest/events",
        json={"source_key": source_key, "events": [future]},
        headers=headers,
    ).json()
    assert r2["outcomes"][0]["rejection_reason"] == "timestamp_in_future"

    # Bad coordinates.
    bad_coords = _event("q3", latitude=200.0)
    r3 = client.post(
        "/api/v1/ingest/events",
        json={"source_key": source_key, "events": [bad_coords]},
        headers=headers,
    ).json()
    assert r3["outcomes"][0]["rejection_reason"] in {
        "coordinates_out_of_range",
        "invalid_payload",
    }

    # Unsupported schema version.
    old_schema = _event("q4")
    old_schema["schema_version"] = "0.9"
    r4 = client.post(
        "/api/v1/ingest/events",
        json={"source_key": source_key, "events": [old_schema]},
        headers=headers,
    ).json()
    assert r4["outcomes"][0]["rejection_reason"] == "schema_version_unsupported"


def test_source_health_counters_update(client: TestClient) -> None:
    api_key, source_key = _setup_ingest(client, "ingest-saglik")
    owner_headers = None
    # Re-login as owner to read health (owner token from setup is not returned;
    # log in fresh).
    owner = client.post(
        "/api/v1/auth/login",
        json={"email": "o@ingest-saglik.example", "password": "GuvenliParola42!"},
    ).json()
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}

    good = _event("h1")
    bad = _event("h2")
    bad["vehicle_external_id"] = "YOK"
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": source_key, "events": [good, bad]},
        headers={"X-API-Key": api_key},
    )

    sources = client.get("/api/v1/integrations/data-sources", headers=owner_headers).json()
    health = next(s for s in sources if s["source_key"] == source_key)
    assert health["accepted_count"] == 1
    assert health["rejected_count"] == 1
    assert health["last_event_at"] is not None


def test_revoked_key_rejected(client: TestClient) -> None:
    owner = create_org_and_login(client, "ingest-iptal", "o@ingest-iptal.example")
    client.post("/api/v1/vehicles", json={"external_id": "34ABC123"}, headers=_h(owner))
    client.post(
        "/api/v1/integrations/data-sources",
        json={"name": "Kaynak", "source_key": "s-1", "kind": "rest"},
        headers=_h(owner),
    )
    api_client = client.post(
        "/api/v1/integrations/clients", json={"name": "İstemci"}, headers=_h(owner)
    ).json()
    token = client.post(
        f"/api/v1/integrations/clients/{api_client['id']}/tokens",
        json={"scopes": ["ingest:write"]},
        headers=_h(owner),
    ).json()

    # Revoke, then the key must stop working.
    revoke = client.delete(f"/api/v1/integrations/tokens/{token['id']}", headers=_h(owner))
    assert revoke.status_code == 204
    blocked = client.post(
        "/api/v1/ingest/events",
        json={"source_key": "s-1", "events": [_event("x")]},
        headers={"X-API-Key": token["api_key"]},
    )
    assert blocked.status_code == 401


def test_cross_tenant_key_cannot_reach_other_source(client: TestClient) -> None:
    key_a, _ = _setup_ingest(client, "ingest-x-a")

    # Tenant B defines a source_key that tenant A does not have.
    owner_b = create_org_and_login(client, "ingest-x-b", "o@ingest-x-b.example")
    client.post(
        "/api/v1/integrations/data-sources",
        json={"name": "B Kaynağı", "source_key": "sadece-b", "kind": "rest"},
        headers=_h(owner_b),
    )

    # Tenant A's key targeting tenant B's source_key resolves under A's tenant
    # context, where "sadece-b" does not exist → 404 (no cross-tenant reach).
    resp = client.post(
        "/api/v1/ingest/events",
        json={"source_key": "sadece-b", "events": [_event("e")]},
        headers={"X-API-Key": key_a},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DATA_SOURCE_NOT_FOUND"
