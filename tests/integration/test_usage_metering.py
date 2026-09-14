"""Usage metering snapshots, subscription view and trial expiry policy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.helpers import auth_headers
from tests.integration.test_coaching import _org_with_event
from visionroute.application.saas.usage import UsageMeteringService
from visionroute.config.settings import Settings
from visionroute.infrastructure.db.engine import build_engine, build_session_factory


async def _sql(settings: Settings, sql: str, **params: object) -> Any:
    engine = build_engine(settings)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.rls_bypass', 'on', true)"))
            result = await conn.execute(text(sql), params)
            return result.scalar() if result.returns_rows else None
    finally:
        await engine.dispose()


async def _metering(settings: Settings) -> tuple[UsageMeteringService, Any]:
    engine = build_engine(settings)
    return UsageMeteringService(build_session_factory(engine)), engine


def _org_id(client: TestClient, auth: dict[str, object]) -> str:
    org: dict[str, str] = client.get(
        "/api/v1/organizations/current", headers=auth_headers(auth)
    ).json()
    return org["id"]


async def test_daily_snapshot_is_idempotent_and_listed(
    client: TestClient, test_settings: Settings
) -> None:
    owner, _, _ = await _org_with_event(client, test_settings, "usage-snap")
    org_id = _org_id(client, owner)
    import uuid

    service, engine = await _metering(test_settings)
    today = datetime.now(UTC).date()
    try:
        first = await service.snapshot_day(today, organization_ids=[uuid.UUID(org_id)])
        second = await service.snapshot_day(today, organization_ids=[uuid.UUID(org_id)])
    finally:
        await engine.dispose()
    assert first == second == 6
    rows = await _sql(
        test_settings,
        "SELECT count(*) FROM usage_records WHERE organization_id = :o AND period_start = :d",
        o=org_id,
        d=today,
    )
    assert rows == 6

    usage = client.get("/api/v1/subscription/usage?days=7", headers=auth_headers(owner))
    assert usage.status_code == 200
    body = usage.json()
    metrics = {m["metric"]: m for m in body["metrics"]}
    assert metrics["vehicles"]["label"] == "Araç"
    assert metrics["vehicles"]["points"][-1]["value"] == 1
    assert metrics["safety_events"]["points"][-1]["value"] == 1
    assert body["current"]["vehicles"] == 1

    subscription = client.get("/api/v1/subscription", headers=auth_headers(owner)).json()
    assert subscription["status"] == "trial"
    assert subscription["billing_mode"] == "manual_invoice"
    assert subscription["trial_days_left"] > 0
    assert subscription["growth_blocked"] is False
    assert subscription["usage"]["active_members"] == 1


async def test_expired_trial_blocks_growth_but_not_ingestion(
    client: TestClient, test_settings: Settings
) -> None:
    owner, _, _ = await _org_with_event(client, test_settings, "usage-trial")
    org_id = _org_id(client, owner)
    await _sql(
        test_settings,
        "UPDATE subscriptions SET trial_ends_at = :t WHERE organization_id = :o",
        t=datetime.now(UTC) - timedelta(minutes=1),
        o=org_id,
    )

    # Enforcement does not wait for the scheduler.
    subscription = client.get("/api/v1/subscription", headers=auth_headers(owner)).json()
    assert subscription["status"] == "past_due" and subscription["growth_blocked"] is True
    blocked = client.post(
        "/api/v1/vehicles", json={"external_id": "34YENI01"}, headers=auth_headers(owner)
    )
    assert blocked.status_code == 409
    assert "Aboneliğiniz etkin değil" in blocked.json()["error"]["message"]

    api_client = client.post(
        "/api/v1/integrations/clients", json={"name": "Cihaz 2"}, headers=auth_headers(owner)
    ).json()
    api_key = client.post(
        f"/api/v1/integrations/clients/{api_client['id']}/tokens",
        json={"scopes": ["ingest:write"]},
        headers=auth_headers(owner),
    ).json()["api_key"]
    ingest = client.post(
        "/api/v1/ingest/events",
        json={
            "source_key": "t-1",
            "events": [
                {
                    "schema_version": "1.0",
                    "source": "t-1",
                    "event_id": "usage-trial-2",
                    "event_type": "telemetry.position",
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "vehicle_external_id": "34KOC01",
                    "payload": {"latitude": 39.9, "longitude": 32.8, "speed_kph": 40},
                }
            ],
        },
        headers={"X-API-Key": api_key},
    )
    assert ingest.status_code in (200, 202), ingest.text
    assert ingest.json()["accepted"] == 1

    service, engine = await _metering(test_settings)
    try:
        assert await service.expire_trials() >= 1
    finally:
        await engine.dispose()
    stored = await _sql(
        test_settings, "SELECT status FROM subscriptions WHERE organization_id = :o", o=org_id
    )
    assert stored == "past_due"
    audited = await _sql(
        test_settings,
        "SELECT count(*) FROM audit_logs WHERE organization_id = :o "
        "AND action = 'subscription.trial_expired'",
        o=org_id,
    )
    assert audited == 1


async def test_platform_usage_requires_platform_admin(
    client: TestClient, test_settings: Settings
) -> None:
    owner, _, _ = await _org_with_event(client, test_settings, "usage-plat")
    org_id = _org_id(client, owner)
    denied = client.get(
        f"/api/v1/platform/organizations/{org_id}/usage", headers=auth_headers(owner)
    )
    assert denied.status_code == 403
