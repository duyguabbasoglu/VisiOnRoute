"""Evidence media: signed upload, content verification, signed access, audit,
permissions, API-key scopes and tenant isolation (local storage backend)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.helpers import auth_headers, invite_and_login
from tests.integration.test_coaching import _org_with_event
from visionroute.config.settings import Settings
from visionroute.infrastructure.db.engine import build_engine

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 1020
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


def _slot(
    client: TestClient, auth: dict[str, object], event_id: str, body: bytes, ctype: str
) -> Any:
    return client.post(
        f"/api/v1/safety-events/{event_id}/evidence/uploads",
        json={"content_type": ctype, "size_bytes": len(body), "filename": "Kabin görüntüsü.jpg"},
        headers=auth_headers(auth),
    )


def _put(client: TestClient, upload: dict[str, Any], body: bytes) -> Any:
    assert upload["method"] == "PUT"
    return client.put(upload["url"], content=body, headers=upload["headers"])


async def _audit_actions(settings: Settings, resource_id: str) -> list[str]:
    engine = build_engine(settings)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT set_config('app.rls_bypass', 'on', true)"))
            rows = await conn.execute(
                text("SELECT action, data::text FROM audit_logs WHERE resource_id = :r"),
                {"r": resource_id},
            )
            result = list(rows)
    finally:
        await engine.dispose()
    for _, data in result:
        assert "token=" not in data  # signed URLs never land in the audit trail
    return [row[0] for row in result]


async def test_upload_verify_access_and_delete(client: TestClient, test_settings: Settings) -> None:
    owner, event_id, _ = await _org_with_event(client, test_settings, "ev-media")

    slot = _slot(client, owner, event_id, JPEG, "image/jpeg")
    assert slot.status_code == 201, slot.text
    evidence_id = slot.json()["evidence_id"]
    upload = slot.json()["upload"]

    # Completing before the object exists is refused.
    early = client.post(
        f"/api/v1/safety-events/{event_id}/evidence/{evidence_id}/complete",
        headers=auth_headers(owner),
    )
    assert early.status_code == 409

    # The signed URL is bound to the declared type and size.
    wrong_type = client.put(upload["url"], content=JPEG, headers={"Content-Type": "text/html"})
    assert wrong_type.status_code == 400
    too_big = client.put(upload["url"], content=JPEG + b"x", headers=upload["headers"])
    assert too_big.status_code == 413
    tampered = client.put(upload["url"] + "x", content=JPEG, headers=upload["headers"])
    assert tampered.status_code == 403
    assert _put(client, upload, JPEG).status_code == 204

    done = client.post(
        f"/api/v1/safety-events/{event_id}/evidence/{evidence_id}/complete",
        headers=auth_headers(owner),
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "available"
    assert done.json()["redaction_status"] == "not_processed"

    detail = client.get(f"/api/v1/safety-events/{event_id}", headers=auth_headers(owner)).json()
    media = [e for e in detail["evidence"] if e["id"] == evidence_id]
    assert media and media[0]["kind"] == "snapshot" and media[0]["size_bytes"] == len(JPEG)
    assert "storage_key" not in media[0]

    access = client.get(
        f"/api/v1/safety-events/{event_id}/evidence/{evidence_id}/access",
        headers=auth_headers(owner),
    )
    assert access.status_code == 200
    downloaded = client.get(access.json()["url"])
    assert downloaded.status_code == 200
    assert downloaded.content == JPEG
    assert "attachment" in downloaded.headers["content-disposition"]
    assert downloaded.headers["cache-control"] == "no-store"
    # A download grant cannot be used to upload.
    assert (
        client.put(access.json()["url"], content=PNG, headers=upload["headers"]).status_code == 403
    )

    deleted = client.delete(
        f"/api/v1/safety-events/{event_id}/evidence/{evidence_id}", headers=auth_headers(owner)
    )
    assert deleted.status_code == 204
    # Previously issued URLs stop working once the object is gone.
    assert client.get(access.json()["url"]).status_code == 404
    gone = client.get(
        f"/api/v1/safety-events/{event_id}/evidence/{evidence_id}/access",
        headers=auth_headers(owner),
    )
    assert gone.status_code == 409

    actions = await _audit_actions(test_settings, evidence_id)
    for expected in (
        "evidence.upload_started",
        "evidence.uploaded",
        "evidence.media_accessed",
        "evidence.deleted",
    ):
        assert expected in actions


async def test_content_mismatch_is_rejected_and_removed(
    client: TestClient, test_settings: Settings
) -> None:
    owner, event_id, _ = await _org_with_event(client, test_settings, "ev-sniff")
    html = b"<html><script>alert(1)</script>" + b" " * 200
    slot = _slot(client, owner, event_id, html, "image/png").json()
    assert _put(client, slot["upload"], html).status_code == 204

    rejected = client.post(
        f"/api/v1/safety-events/{event_id}/evidence/{slot['evidence_id']}/complete",
        headers=auth_headers(owner),
    )
    assert rejected.status_code == 422
    access = client.get(
        f"/api/v1/safety-events/{event_id}/evidence/{slot['evidence_id']}/access",
        headers=auth_headers(owner),
    )
    assert access.status_code == 409
    assert "evidence.upload_rejected" in await _audit_actions(test_settings, slot["evidence_id"])

    unsupported = client.post(
        f"/api/v1/safety-events/{event_id}/evidence/uploads",
        json={"content_type": "text/html", "size_bytes": 10},
        headers=auth_headers(owner),
    )
    assert unsupported.status_code == 422
    oversized = client.post(
        f"/api/v1/safety-events/{event_id}/evidence/uploads",
        json={"content_type": "video/mp4", "size_bytes": test_settings.evidence_max_bytes + 1},
        headers=auth_headers(owner),
    )
    assert oversized.status_code == 422


async def test_permissions_and_tenant_isolation(
    client: TestClient, test_settings: Settings
) -> None:
    owner, event_id, _ = await _org_with_event(client, test_settings, "ev-perm")
    slot = _slot(client, owner, event_id, PNG, "image/png").json()
    _put(client, slot["upload"], PNG)
    client.post(
        f"/api/v1/safety-events/{event_id}/evidence/{slot['evidence_id']}/complete",
        headers=auth_headers(owner),
    )

    # Event reviewers see evidence metadata but not raw media.
    reviewer = await invite_and_login(
        client, test_settings, owner, "reviewer@ev-perm.example", "event_reviewer"
    )
    detail = client.get(f"/api/v1/safety-events/{event_id}", headers=auth_headers(reviewer))
    assert detail.status_code == 200
    for path, method in (
        (f"/api/v1/safety-events/{event_id}/evidence/{slot['evidence_id']}/access", "GET"),
        (f"/api/v1/safety-events/{event_id}/evidence/uploads", "POST"),
        (f"/api/v1/safety-events/{event_id}/evidence/{slot['evidence_id']}", "DELETE"),
    ):
        response = client.request(
            method,
            path,
            json={"content_type": "image/png", "size_bytes": 10} if method == "POST" else None,
            headers=auth_headers(reviewer),
        )
        assert response.status_code == 403, (path, response.text)

    # Another tenant cannot reach the evidence even with a valid role.
    other, other_event, _ = await _org_with_event(client, test_settings, "ev-perm-b")
    cross = client.get(
        f"/api/v1/safety-events/{event_id}/evidence/{slot['evidence_id']}/access",
        headers=auth_headers(other),
    )
    assert cross.status_code == 404
    cross_upload = _slot(client, other, event_id, PNG, "image/png")
    assert cross_upload.status_code == 404
    mismatched_event = client.get(
        f"/api/v1/safety-events/{other_event}/evidence/{slot['evidence_id']}/access",
        headers=auth_headers(other),
    )
    assert mismatched_event.status_code == 404


async def test_api_key_scopes(client: TestClient, test_settings: Settings) -> None:
    owner, event_id, _ = await _org_with_event(client, test_settings, "ev-key")
    api_client = client.post(
        "/api/v1/integrations/clients", json={"name": "Kamera"}, headers=auth_headers(owner)
    ).json()

    def token(scopes: list[str]) -> Any:
        return client.post(
            f"/api/v1/integrations/clients/{api_client['id']}/tokens",
            json={"scopes": scopes},
            headers=auth_headers(owner),
        )

    assert token(["admin:everything"]).status_code == 422
    assert token([]).status_code == 422
    ingest_only = token(["ingest:write"]).json()["api_key"]
    evidence_only = token(["evidence:write"]).json()["api_key"]

    body = {"safety_event_id": event_id, "content_type": "image/jpeg", "size_bytes": len(JPEG)}
    denied = client.post(
        "/api/v1/ingest/evidence/uploads", json=body, headers={"X-API-Key": ingest_only}
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "SCOPE_MISSING"
    # An evidence-only key cannot push telemetry.
    telemetry = client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": [{"event_id": "x"}]},
        headers={"X-API-Key": evidence_only},
    )
    assert telemetry.status_code == 403

    slot = client.post(
        "/api/v1/ingest/evidence/uploads", json=body, headers={"X-API-Key": evidence_only}
    )
    assert slot.status_code == 201, slot.text
    assert _put(client, slot.json()["upload"], JPEG).status_code == 204
    done = client.post(
        f"/api/v1/ingest/evidence/{slot.json()['evidence_id']}/complete",
        headers={"X-API-Key": evidence_only},
    )
    assert done.status_code == 200 and done.json()["status"] == "available"
