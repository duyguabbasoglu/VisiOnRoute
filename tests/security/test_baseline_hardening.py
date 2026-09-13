"""Regression tests for defects found during the 2026-09 baseline audit.

- revoked/demoted memberships lose privileges immediately (not at JWT expiry)
- evidence payload requires EVIDENCE_READ, not just EVENTS_READ
- CSV reports neutralise spreadsheet formula injection
- a poison outbox event cannot block the rest of its batch
- scheduler ticks are mutually exclusive across replicas
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.helpers import create_org_and_login, invite_and_login
from visionroute.application.reports.service import csv_safe
from visionroute.config.settings import Settings
from visionroute.scheduler.runner import SCHEDULER_LOCK_KEY, Scheduler
from visionroute.worker.runner import Worker

pytestmark = pytest.mark.security


def _h(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


async def test_removed_member_token_is_rejected_immediately(
    client: TestClient, test_settings: Settings
) -> None:
    owner = create_org_and_login(client, "revoke-member", "o@revoke-member.example")
    member = await invite_and_login(
        client, test_settings, owner, "m@revoke-member.example", "analyst"
    )
    assert client.get("/api/v1/organizations/current", headers=_h(member)).status_code == 200

    members = client.get("/api/v1/organizations/current/members", headers=_h(owner)).json()
    membership_id = next(m["membership_id"] for m in members if m["email"].startswith("m@"))
    removed = client.delete(
        f"/api/v1/organizations/current/members/{membership_id}", headers=_h(owner)
    )
    assert removed.status_code == 204

    # The still-unexpired access token must not keep working.
    after = client.get("/api/v1/organizations/current", headers=_h(member))
    assert after.status_code == 401
    assert after.json()["error"]["code"] == "SESSION_REVOKED"


async def test_role_demotion_applies_to_existing_token(
    client: TestClient, test_settings: Settings
) -> None:
    owner = create_org_and_login(client, "demote-member", "o@demote-member.example")
    admin = await invite_and_login(client, test_settings, owner, "a@demote-member.example", "admin")
    ok = client.patch(
        "/api/v1/organizations/current", json={"name": "Yeni Ad A.Ş."}, headers=_h(admin)
    )
    assert ok.status_code == 200

    members = client.get("/api/v1/organizations/current/members", headers=_h(owner)).json()
    membership_id = next(m["membership_id"] for m in members if m["email"].startswith("a@"))
    demoted = client.patch(
        f"/api/v1/organizations/current/members/{membership_id}",
        json={"role": "analyst"},
        headers=_h(owner),
    )
    assert demoted.status_code == 200

    denied = client.patch(
        "/api/v1/organizations/current", json={"name": "Yetkisiz A.Ş."}, headers=_h(admin)
    )
    assert denied.status_code == 403


def _harsh_event(event_id: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "source": "t-1",
        "event_id": event_id,
        "event_type": "telemetry.position",
        "occurred_at": (datetime.now(UTC) - timedelta(minutes=2)).isoformat(),
        "vehicle_external_id": "34EV001",
        "payload": {
            "latitude": 39.92,
            "longitude": 32.85,
            "speed_kph": 70,
            "acceleration_ms2": -6.5,
            "gps_hdop": 1.0,
            "satellites": 12,
        },
    }


async def _drain(settings: Settings) -> None:
    worker = Worker(settings)
    try:
        for _ in range(8):
            if await worker.run_once() == 0:
                break
    finally:
        await worker._engine.dispose()


async def test_evidence_requires_evidence_permission(
    client: TestClient, test_settings: Settings
) -> None:
    owner = create_org_and_login(client, "evidence-perm", "o@evidence-perm.example")
    client.post("/api/v1/vehicles", json={"external_id": "34EV001"}, headers=_h(owner))
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
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": [_harsh_event("ev-1")]},
        headers={"X-API-Key": api_key},
    )
    await _drain(test_settings)

    event_id = client.get("/api/v1/safety-events", headers=_h(owner)).json()["items"][0]["id"]
    owner_view = client.get(f"/api/v1/safety-events/{event_id}", headers=_h(owner)).json()
    assert owner_view["evidence_restricted"] is False
    assert len(owner_view["evidence"]) == 1

    analyst = await invite_and_login(
        client, test_settings, owner, "an@evidence-perm.example", "analyst"
    )
    analyst_view = client.get(f"/api/v1/safety-events/{event_id}", headers=_h(analyst))
    assert analyst_view.status_code == 200
    assert analyst_view.json()["evidence_restricted"] is True
    assert analyst_view.json()["evidence"] == []


def test_csv_safe_neutralises_formula_prefixes() -> None:
    for dangerous in ("=1+1", "+cmd", "-2+3", "@SUM(A1)", "\tx", "\rx"):
        assert csv_safe(dangerous).startswith("'")
    assert csv_safe("Sert fren") == "Sert fren"


def test_csv_report_escapes_tenant_controlled_text(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": '=HYPERLINK("http://saldirgan.example")',
            "slug": "csv-injection",
            "email": "o@csv-injection.example",
            "full_name": "Test Kullanıcı",
            "password": "GuvenliParola42!",
        },
    )
    assert response.status_code == 201, response.text
    csv_response = client.get("/api/v1/reports/safety-events.csv", headers=_h(response.json()))
    assert csv_response.status_code == 200
    assert "'=HYPERLINK" in csv_response.text
    assert ",=HYPERLINK" not in csv_response.text


async def test_poison_outbox_event_does_not_block_batch(test_settings: Settings) -> None:
    engine = create_async_engine(test_settings.database_url)
    poison_id, healthy_id = uuid.uuid4(), uuid.uuid4()
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.rls_bypass', 'on', true)"))
            # ``ingest_event_id`` is not a UUID → the handler raises a database
            # error, which previously poisoned the whole claim transaction.
            await conn.execute(
                text(
                    "INSERT INTO outbox_events (id, aggregate_type, aggregate_id, event_type, "
                    "payload, occurred_at) VALUES "
                    "(:p, 'ingest_event', 'x', 'ingest.event_accepted', "
                    "'{\"ingest_event_id\": \"gecersiz\"}', now() - interval '1 hour'), "
                    "(:h, 'misc', 'y', 'test.noop', '{}', now() - interval '1 hour')"
                ),
                {"p": poison_id, "h": healthy_id},
            )

        await _drain(test_settings)

        async with engine.connect() as conn:
            rows = dict(
                (
                    await conn.execute(
                        text("SELECT id, status FROM outbox_events WHERE id IN (:p, :h)"),
                        {"p": poison_id, "h": healthy_id},
                    )
                ).all()
            )
            attempts = (
                await conn.execute(
                    text("SELECT attempts FROM outbox_events WHERE id = :p"), {"p": poison_id}
                )
            ).scalar_one()
        assert rows[healthy_id] == "done"
        assert rows[poison_id] == "pending"
        assert attempts == 1
    finally:
        await engine.dispose()


async def test_scheduler_tick_is_mutually_exclusive(test_settings: Settings) -> None:
    engine = create_async_engine(test_settings.database_url)
    scheduler = Scheduler(test_settings)
    try:
        async with engine.connect() as holder:
            await holder.execute(text("SELECT pg_advisory_lock(:k)"), {"k": SCHEDULER_LOCK_KEY})
            assert await scheduler.run_once() is False
            await holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SCHEDULER_LOCK_KEY})
        assert await scheduler.run_once() is True
    finally:
        await scheduler._engine.dispose()
        await engine.dispose()
