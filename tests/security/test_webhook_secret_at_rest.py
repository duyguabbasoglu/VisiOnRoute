"""Webhook signing secrets are encrypted at rest and shown only once.

The SSRF guard resolves DNS (unit-tested separately in test_urlguard); it is
bypassed here, as in test_notifications_reports, so these tests exercise
storage and tenancy behaviour without network access.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.helpers import create_org_and_login
from visionroute.config.settings import Settings
from visionroute.infrastructure.security.crypto import build_field_cipher

pytestmark = pytest.mark.security


def _h(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


@pytest.fixture
def no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    import visionroute.api.routers.v1.notifications_reports as api_module

    monkeypatch.setattr(api_module, "validate_url", lambda url, **kw: url)


async def _stored_secret(settings: Settings, webhook_id: str) -> str:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.rls_bypass', 'on', true)"))
            value = (
                await conn.execute(
                    text("SELECT secret_enc FROM webhook_endpoints WHERE id = :id"),
                    {"id": webhook_id},
                )
            ).scalar_one()
            return str(value)
    finally:
        await engine.dispose()


async def test_secret_encrypted_in_database_and_rotatable(
    client: TestClient, test_settings: Settings, no_dns: None
) -> None:
    owner = create_org_and_login(client, "webhook-at-rest", "o@webhook-at-rest.example")
    created = client.post(
        "/api/v1/webhooks",
        json={"url": "https://alici.example/hook", "description": "Alıcı"},
        headers=_h(owner),
    )
    assert created.status_code == 201, created.text
    webhook = created.json()
    plaintext = webhook["secret"]
    assert plaintext.startswith("whsec_")

    stored = await _stored_secret(test_settings, webhook["id"])
    assert stored.startswith("enc1:test-k1:")
    assert plaintext not in stored
    cipher = build_field_cipher(test_settings)
    assert cipher is not None
    assert cipher.decrypt(stored) == plaintext

    listed = client.get("/api/v1/webhooks", headers=_h(owner)).json()
    assert all(item["secret"] is None for item in listed)

    rotated = client.post(f"/api/v1/webhooks/{webhook['id']}/rotate-secret", headers=_h(owner))
    assert rotated.status_code == 200
    new_secret = rotated.json()["secret"]
    assert new_secret and new_secret != plaintext
    assert cipher.decrypt(await _stored_secret(test_settings, webhook["id"])) == new_secret


def test_webhook_management_is_tenant_scoped(client: TestClient, no_dns: None) -> None:
    owner_a = create_org_and_login(client, "webhook-scope-a", "a@webhook-scope-a.example")
    owner_b = create_org_and_login(client, "webhook-scope-b", "b@webhook-scope-b.example")
    created = client.post(
        "/api/v1/webhooks", json={"url": "https://alici.example/hook"}, headers=_h(owner_a)
    )
    assert created.status_code == 201, created.text
    webhook_id = created.json()["id"]

    for method, path in (
        ("post", f"/api/v1/webhooks/{webhook_id}/rotate-secret"),
        ("patch", f"/api/v1/webhooks/{webhook_id}"),
        ("delete", f"/api/v1/webhooks/{webhook_id}"),
        ("get", f"/api/v1/webhooks/{webhook_id}/deliveries"),
    ):
        kwargs: dict[str, object] = {"headers": _h(owner_b)}
        if method == "patch":
            kwargs["json"] = {"active": False}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 404, (method, path, response.text)

    paused = client.patch(
        f"/api/v1/webhooks/{webhook_id}", json={"active": False}, headers=_h(owner_a)
    )
    assert paused.status_code == 200
    assert paused.json()["active"] is False
    deliveries = client.get(f"/api/v1/webhooks/{webhook_id}/deliveries", headers=_h(owner_a))
    assert deliveries.status_code == 200
    assert client.delete(f"/api/v1/webhooks/{webhook_id}", headers=_h(owner_a)).status_code == 204


def test_webhook_creation_requires_configured_encryption(
    test_settings: Settings, no_dns: None
) -> None:
    from visionroute.api.main import create_app

    unkeyed = test_settings.model_copy(update={"field_encryption_keys": {}})
    with TestClient(create_app(unkeyed), raise_server_exceptions=False) as plain_client:
        owner = create_org_and_login(plain_client, "webhook-nokey", "o@webhook-nokey.example")
        response = plain_client.post(
            "/api/v1/webhooks", json={"url": "https://alici.example/hook"}, headers=_h(owner)
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ENCRYPTION_NOT_CONFIGURED"
