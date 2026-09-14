"""KVKK: export and erasure requests, worker processing, retention purge,
permissions and tenant isolation."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.helpers import auth_headers, deliver_mail, invite_and_login, last_email_to
from tests.integration.test_coaching import _org_with_event
from visionroute.application.privacy.processor import PrivacyProcessor
from visionroute.config.settings import Settings
from visionroute.domain.privacy import MAX_ATTEMPTS
from visionroute.domain.storage import StorageError
from visionroute.infrastructure.db.engine import build_engine, build_session_factory
from visionroute.infrastructure.security.crypto import build_field_cipher
from visionroute.infrastructure.storage import build_object_storage

JPEG = b"\xff\xd8\xff\xe0" + b"\x01" * 500


async def _process(settings: Settings, *, storage: Any = None, now: datetime | None = None) -> int:
    engine = build_engine(settings)
    try:
        processor = PrivacyProcessor(
            build_session_factory(engine),
            storage or build_object_storage(settings),
            build_field_cipher(settings),
        )
        total = 0
        for _ in range(10):
            handled = await processor.process_due(now=now)
            total += handled
            if handled == 0:
                break
        return total
    finally:
        await engine.dispose()


async def _purge(settings: Settings, org_id: str, now: datetime) -> dict[str, int]:
    engine = build_engine(settings)
    try:
        processor = PrivacyProcessor(
            build_session_factory(engine), build_object_storage(settings), None
        )
        return await processor.purge_expired(now=now, organization_ids=[uuid.UUID(org_id)])
    finally:
        await engine.dispose()


async def _scalar(settings: Settings, sql: str, **params: object) -> Any:
    engine = build_engine(settings)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT set_config('app.rls_bypass', 'on', true)"))
            return (await conn.execute(text(sql), params)).scalar()
    finally:
        await engine.dispose()


def _request(client: TestClient, auth: dict[str, object], **body: object) -> Any:
    return client.post("/api/v1/privacy/requests", json=body, headers=auth_headers(auth))


def _org_id(client: TestClient, auth: dict[str, object]) -> str:
    org: dict[str, str] = client.get(
        "/api/v1/organizations/current", headers=auth_headers(auth)
    ).json()
    return org["id"]


def _attach_media(client: TestClient, auth: dict[str, object], event_id: str) -> str:
    slot = client.post(
        f"/api/v1/safety-events/{event_id}/evidence/uploads",
        json={"content_type": "image/jpeg", "size_bytes": len(JPEG)},
        headers=auth_headers(auth),
    ).json()
    upload = slot["upload"]
    assert client.put(upload["url"], content=JPEG, headers=upload["headers"]).status_code == 204
    done = client.post(
        f"/api/v1/safety-events/{event_id}/evidence/{slot['evidence_id']}/complete",
        headers=auth_headers(auth),
    )
    assert done.status_code == 200
    evidence_id: str = slot["evidence_id"]
    return evidence_id


async def test_driver_export_archive(client: TestClient, test_settings: Settings) -> None:
    owner, event_id, driver_id = await _org_with_event(client, test_settings, "kvkk-exp")
    _attach_media(client, owner, event_id)

    created = _request(client, owner, kind="export", subject_type="driver", subject_id=driver_id)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "pending"
    assert created.json()["subject_name"] == "Koçluk Sürücüsü"
    duplicate = _request(client, owner, kind="export", subject_type="driver", subject_id=driver_id)
    assert duplicate.status_code == 409

    assert await _process(test_settings) >= 1
    items = client.get("/api/v1/privacy/requests", headers=auth_headers(owner)).json()
    item = next(i for i in items if i["id"] == created.json()["id"])
    assert item["status"] == "completed" and item["download_available"] is True
    assert item["result"]["safety_events"] == 1 and item["result"]["telemetry_points"] >= 1

    link = client.get(
        f"/api/v1/privacy/requests/{item['id']}/download", headers=auth_headers(owner)
    )
    assert link.status_code == 200
    archive = client.get(link.json()["url"])
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zf:
        names = set(zf.namelist())
        assert {"BENIOKU.txt", "manifest.json", "surucu.json", "telemetri.csv"} <= names
        assert json.loads(zf.read("surucu.json"))["full_name"] == "Koçluk Sürücüsü"
        assert len(json.loads(zf.read("guvenlik_olaylari.json"))) == 1
        media = [n for n in names if n.startswith("media/")]
        assert len(media) == 1 and zf.read(media[0]) == JPEG

    audit = await _scalar(
        test_settings,
        "SELECT count(*) FROM audit_logs WHERE resource_id = :r AND action IN "
        "('privacy.export_requested','privacy.export_completed','privacy.export_downloaded')",
        r=item["id"],
    )
    assert audit == 3


async def test_self_service_export_and_notification(
    client: TestClient, test_settings: Settings
) -> None:
    owner, _, _ = await _org_with_event(client, test_settings, "kvkk-self")
    analyst = await invite_and_login(
        client, test_settings, owner, "analist@kvkk-self.example", "analyst"
    )
    # Regular members cannot manage organization privacy requests.
    assert client.get("/api/v1/privacy/requests", headers=auth_headers(analyst)).status_code == 403

    mine = client.post("/api/v1/privacy/me/export", headers=auth_headers(analyst))
    assert mine.status_code == 201, mine.text
    others = client.post("/api/v1/privacy/me/export", headers=auth_headers(owner)).json()
    await _process(test_settings)
    await deliver_mail(test_settings)
    assert "hazır" in last_email_to("analist@kvkk-self.example").subject

    listed = client.get("/api/v1/privacy/me/requests", headers=auth_headers(analyst)).json()
    assert [r["id"] for r in listed] == [mine.json()["id"]]
    link = client.get(
        f"/api/v1/privacy/me/requests/{mine.json()['id']}/download",
        headers=auth_headers(analyst),
    )
    assert link.status_code == 200
    with zipfile.ZipFile(io.BytesIO(client.get(link.json()["url"]).content)) as zf:
        account = json.loads(zf.read("hesap.json"))
        assert account["email"] == "analist@kvkk-self.example"
        assert "password_hash" not in account and "mfa_totp_secret_enc" not in account
    # Another member's export is not reachable through the self-service route.
    foreign = client.get(
        f"/api/v1/privacy/me/requests/{others['id']}/download", headers=auth_headers(analyst)
    )
    assert foreign.status_code == 404


async def test_driver_erasure(client: TestClient, test_settings: Settings) -> None:
    owner, event_id, driver_id = await _org_with_event(client, test_settings, "kvkk-del")
    evidence_id = _attach_media(client, owner, event_id)
    access = client.get(
        f"/api/v1/safety-events/{event_id}/evidence/{evidence_id}/access",
        headers=auth_headers(owner),
    ).json()

    no_reason = _request(client, owner, kind="erasure", subject_type="driver", subject_id=driver_id)
    assert no_reason.status_code == 422
    created = _request(
        client,
        owner,
        kind="erasure",
        subject_type="driver",
        subject_id=driver_id,
        reason="Sürücü işten ayrıldı ve silme başvurusu yaptı.",
    )
    assert created.status_code == 201
    await _process(test_settings)

    result = next(
        r
        for r in client.get("/api/v1/privacy/requests", headers=auth_headers(owner)).json()
        if r["id"] == created.json()["id"]
    )
    assert result["status"] == "completed"
    assert result["result"]["telemetry_points_deleted"] >= 1
    assert result["result"]["evidence_media_deleted"] == 1
    assert result["subject_name"].startswith("Silinmiş sürücü")

    drivers = client.get("/api/v1/drivers", headers=auth_headers(owner)).json()
    rows = drivers["items"] if isinstance(drivers, dict) else drivers
    assert all(d["full_name"] != "Koçluk Sürücüsü" for d in rows)
    assert (
        await _scalar(
            test_settings, "SELECT count(*) FROM telemetry_points WHERE driver_id = :d", d=driver_id
        )
        == 0
    )
    # The safety event remains for fleet statistics, without location.
    detail = client.get(f"/api/v1/safety-events/{event_id}", headers=auth_headers(owner)).json()
    assert detail["latitude"] is None and detail["longitude"] is None
    assert client.get(access["url"]).status_code == 404

    again = _request(
        client,
        owner,
        kind="erasure",
        subject_type="driver",
        subject_id=driver_id,
        reason="Tekrar deneme amaçlı ikinci talep.",
    )
    assert again.status_code == 409


async def test_member_erasure_revokes_access(client: TestClient, test_settings: Settings) -> None:
    owner, _, _ = await _org_with_event(client, test_settings, "kvkk-user")
    member = await invite_and_login(
        client, test_settings, owner, "uye@kvkk-user.example", "analyst"
    )
    members = client.get(
        "/api/v1/organizations/current/members", headers=auth_headers(owner)
    ).json()
    member_id = next(m["user_id"] for m in members if m["email"] == "uye@kvkk-user.example")
    owner_id = next(m["user_id"] for m in members if m["email"] != "uye@kvkk-user.example")
    reason = "Çalışan ayrıldı, hesap verilerinin silinmesini talep etti."

    self_erasure = _request(
        client, owner, kind="erasure", subject_type="user", subject_id=owner_id, reason=reason
    )
    assert self_erasure.status_code == 409
    created = _request(
        client, owner, kind="erasure", subject_type="user", subject_id=member_id, reason=reason
    )
    assert created.status_code == 201
    await _process(test_settings)

    assert client.get("/api/v1/auth/me", headers=auth_headers(member)).status_code == 401
    login = client.post(
        "/api/v1/auth/login", json={"email": "uye@kvkk-user.example", "password": "DavetliParola7!"}
    )
    assert login.status_code == 401
    status_row = await _scalar(test_settings, "SELECT status FROM users WHERE id = :u", u=member_id)
    assert status_row == "erased"
    email_row = await _scalar(test_settings, "SELECT email FROM users WHERE id = :u", u=member_id)
    assert email_row.endswith("@silinmis.invalid")


async def test_retention_settings_and_purge(client: TestClient, test_settings: Settings) -> None:
    owner, event_id, _ = await _org_with_event(client, test_settings, "kvkk-ret")
    _attach_media(client, owner, event_id)
    org_id = _org_id(client, owner)

    retention = client.get("/api/v1/privacy/retention", headers=auth_headers(owner)).json()
    plan_days = retention["plan_days"]
    too_short = client.put(
        "/api/v1/privacy/retention", json={"telemetry_days": 5}, headers=auth_headers(owner)
    )
    assert too_short.status_code == 422
    too_long = client.put(
        "/api/v1/privacy/retention",
        json={"telemetry_days": plan_days + 1},
        headers=auth_headers(owner),
    )
    assert too_long.status_code == 422
    updated = client.put(
        "/api/v1/privacy/retention", json={"telemetry_days": 30}, headers=auth_headers(owner)
    )
    assert updated.status_code == 200
    telemetry = next(c for c in updated.json()["categories"] if c["key"] == "telemetry_days")
    assert telemetry["effective_days"] == 30

    # Nothing is due yet.
    now = datetime.now(UTC)
    assert (await _purge(test_settings, org_id, now))["telemetry_points"] == 0
    # 31 days later raw telemetry is past retention; media (plan default) is not.
    later = await _purge(test_settings, org_id, now + timedelta(days=31))
    assert later["telemetry_points"] >= 1 and later["evidence_media"] == 0
    much_later = await _purge(test_settings, org_id, now + timedelta(days=plan_days + 1))
    assert much_later["evidence_media"] == 1
    detail = client.get(f"/api/v1/safety-events/{event_id}", headers=auth_headers(owner)).json()
    assert any(e["status"] == "deleted" for e in detail["evidence"])


async def test_tenant_isolation(client: TestClient, test_settings: Settings) -> None:
    owner_a, _, driver_a = await _org_with_event(client, test_settings, "kvkk-ta")
    owner_b, _, _ = await _org_with_event(client, test_settings, "kvkk-tb")
    created = _request(client, owner_a, kind="export", subject_type="driver", subject_id=driver_a)
    assert created.status_code == 201

    cross = _request(client, owner_b, kind="export", subject_type="driver", subject_id=driver_a)
    assert cross.status_code == 404
    listed = client.get("/api/v1/privacy/requests", headers=auth_headers(owner_b)).json()
    assert created.json()["id"] not in {r["id"] for r in listed}
    await _process(test_settings)
    download = client.get(
        f"/api/v1/privacy/requests/{created.json()['id']}/download", headers=auth_headers(owner_b)
    )
    assert download.status_code == 404
    cancel = client.post(
        f"/api/v1/privacy/requests/{created.json()['id']}/cancel", headers=auth_headers(owner_b)
    )
    assert cancel.status_code == 404


class _BrokenStorage:
    async def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        raise StorageError("depo kapalı")

    async def delete(self, key: str) -> None:
        return None

    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes:
        raise StorageError("depo kapalı")


async def test_failures_retry_then_fail(client: TestClient, test_settings: Settings) -> None:
    owner, _, driver_id = await _org_with_event(client, test_settings, "kvkk-fail")
    created = _request(client, owner, kind="export", subject_type="driver", subject_id=driver_id)
    request_id = created.json()["id"]

    now = datetime.now(UTC)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        await _process(test_settings, storage=_BrokenStorage(), now=now)
        state = await _scalar(
            test_settings, "SELECT status FROM privacy_requests WHERE id = :r", r=request_id
        )
        expected = "failed" if attempt == MAX_ATTEMPTS else "pending"
        assert state == expected, (attempt, state)
        now += timedelta(hours=2)

    item = next(
        r
        for r in client.get("/api/v1/privacy/requests", headers=auth_headers(owner)).json()
        if r["id"] == request_id
    )
    assert item["error_code"] == "StorageError" and item["download_available"] is False


async def test_self_service_export_is_rate_limited(
    client: TestClient, test_settings: Settings
) -> None:
    owner, _, _ = await _org_with_event(client, test_settings, "kvkk-sinir")
    statuses = [
        client.post("/api/v1/privacy/me/export", headers=auth_headers(owner)).status_code
        for _ in range(4)
    ]
    # One job at a time (409 while pending); a small daily budget per user (429).
    assert statuses == [201, 409, 409, 429]
