"""API token listing exposes metadata only and respects tenant boundaries."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import auth_headers, create_org_and_login


def test_token_listing_shows_metadata_and_revocation(client: TestClient) -> None:
    owner = create_org_and_login(client, "anahtar-liste", "o@anahtar-liste.example")
    api_client = client.post(
        "/api/v1/integrations/clients", json={"name": "Kamera"}, headers=auth_headers(owner)
    ).json()
    issued = client.post(
        f"/api/v1/integrations/clients/{api_client['id']}/tokens",
        json={"scopes": ["ingest:write", "evidence:write"]},
        headers=auth_headers(owner),
    ).json()

    listed = client.get(
        f"/api/v1/integrations/clients/{api_client['id']}/tokens", headers=auth_headers(owner)
    )
    assert listed.status_code == 200
    [token] = listed.json()
    assert token["id"] == issued["id"]
    assert issued["api_key"].startswith(token["prefix"])
    assert token["scopes"] == ["evidence:write", "ingest:write"]
    assert token["revoked_at"] is None
    assert "api_key" not in token and "token_hash" not in token
    assert issued["api_key"] not in listed.text

    revoked = client.delete(
        f"/api/v1/integrations/tokens/{issued['id']}", headers=auth_headers(owner)
    )
    assert revoked.status_code == 204
    after = client.get(
        f"/api/v1/integrations/clients/{api_client['id']}/tokens", headers=auth_headers(owner)
    ).json()
    assert after[0]["revoked_at"] is not None
    rejected = client.post(
        "/api/v1/ingest/events",
        json={"source_key": "x", "events": [{"event_id": "x"}]},
        headers={"X-API-Key": issued["api_key"]},
    )
    assert rejected.status_code == 401


def test_token_listing_is_tenant_scoped(client: TestClient) -> None:
    owner_a = create_org_and_login(client, "anahtar-a", "o@anahtar-a.example")
    owner_b = create_org_and_login(client, "anahtar-b", "o@anahtar-b.example")
    api_client = client.post(
        "/api/v1/integrations/clients", json={"name": "A cihazı"}, headers=auth_headers(owner_a)
    ).json()
    cross = client.get(
        f"/api/v1/integrations/clients/{api_client['id']}/tokens", headers=auth_headers(owner_b)
    )
    assert cross.status_code == 404
