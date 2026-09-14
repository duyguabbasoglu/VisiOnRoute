"""Coaching workflow: review integration, idempotency, lifecycle, assignment,
permissions, driver scoping, tenant isolation, analytics and CSV report."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.helpers import (
    auth_headers,
    create_org_and_login,
    deliver_mail,
    invite_and_login,
    last_email_to,
)
from visionroute.application.coaching.service import CoachingService
from visionroute.application.context import RequestContext
from visionroute.config.settings import Settings
from visionroute.domain.permissions import RoleKey
from visionroute.infrastructure.db.engine import build_engine, build_session_factory
from visionroute.infrastructure.db.tenancy import set_tenant
from visionroute.worker.runner import Worker


def _h(auth: dict[str, object]) -> dict[str, str]:
    return auth_headers(auth)


async def _drain(settings: Settings) -> None:
    worker = Worker(settings)
    try:
        for _ in range(8):
            if await worker.run_once() == 0:
                break
    finally:
        await worker._engine.dispose()


async def _org_with_event(
    client: TestClient, settings: Settings, slug: str
) -> tuple[dict[str, object], str, str]:
    """Organization with an assigned driver and one harsh-braking event.
    Returns (owner auth, safety event id, driver id)."""
    owner = create_org_and_login(client, slug, f"o@{slug}.example")
    vehicle = client.post(
        "/api/v1/vehicles", json={"external_id": "34KOC01"}, headers=_h(owner)
    ).json()
    driver = client.post(
        "/api/v1/drivers",
        json={"external_id": "SUR-K1", "full_name": "Koçluk Sürücüsü"},
        headers=_h(owner),
    ).json()
    client.post(
        "/api/v1/assignments",
        json={"driver_id": driver["id"], "vehicle_id": vehicle["id"]},
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
    api_key = client.post(
        f"/api/v1/integrations/clients/{api_client['id']}/tokens",
        json={"scopes": ["ingest:write"]},
        headers=_h(owner),
    ).json()["api_key"]
    client.post(
        "/api/v1/ingest/events",
        json={
            "source_key": "t-1",
            "events": [
                {
                    "schema_version": "1.0",
                    "source": "t-1",
                    "event_id": f"{slug}-1",
                    "event_type": "telemetry.position",
                    "occurred_at": (datetime.now(UTC) - timedelta(minutes=3)).isoformat(),
                    "vehicle_external_id": "34KOC01",
                    "payload": {
                        "latitude": 39.92,
                        "longitude": 32.85,
                        "speed_kph": 70,
                        "acceleration_ms2": -6.5,
                        "gps_hdop": 1.0,
                        "satellites": 12,
                    },
                }
            ],
        },
        headers={"X-API-Key": api_key},
    )
    await _drain(settings)
    event_id = client.get("/api/v1/safety-events", headers=_h(owner)).json()["items"][0]["id"]
    return owner, event_id, driver["id"]


def _review(client: TestClient, auth: dict[str, object], event_id: str, **body: Any) -> Any:
    payload = {"decision": "confirmed", "resolution": "kocluk_atandi", **body}
    return client.post(f"/api/v1/safety-events/{event_id}/review", json=payload, headers=_h(auth))


async def test_review_creates_single_coaching_action(
    client: TestClient, test_settings: Settings
) -> None:
    owner, event_id, driver_id = await _org_with_event(client, test_settings, "coach-review")
    first = _review(client, owner, event_id, notes="Takip mesafesi konuşulacak")
    assert first.status_code == 200, first.text
    action_id = first.json()["coaching_action_id"]
    assert action_id

    again = _review(client, owner, event_id)
    assert again.json()["coaching_action_id"] == action_id  # idempotent

    listing = client.get(
        f"/api/v1/coaching-actions?safety_event_id={event_id}", headers=_h(owner)
    ).json()
    assert listing["total"] == 1
    action = listing["items"][0]
    assert action["status"] == "open"
    assert action["driver_id"] == driver_id
    assert action["driver_name"] == "Koçluk Sürücüsü"
    assert action["event_label"] == "Sert fren"
    assert action["due_at"] is not None

    detail = client.get(f"/api/v1/safety-events/{event_id}", headers=_h(owner)).json()
    assert detail["resolution_label"] == "Koçluk atandı"
    assert detail["coaching_action"]["id"] == action_id


async def test_review_validation(client: TestClient, test_settings: Settings) -> None:
    owner, event_id, _ = await _org_with_event(client, test_settings, "coach-validate")
    rejected = _review(client, owner, event_id, decision="rejected")
    assert rejected.status_code == 422
    assert "onaylanan" in rejected.json()["error"]["message"]
    unknown = _review(client, owner, event_id, resolution="uydurma")
    assert unknown.status_code == 422
    other = _review(client, owner, event_id, resolution="yanlis_alarm", decision="rejected")
    assert other.status_code == 200
    assert other.json()["coaching_action_id"] is None


async def test_lifecycle_and_transition_rules(client: TestClient, test_settings: Settings) -> None:
    owner, event_id, _ = await _org_with_event(client, test_settings, "coach-life")
    action_id = _review(client, owner, event_id).json()["coaching_action_id"]
    base = f"/api/v1/coaching-actions/{action_id}"

    started = client.post(f"{base}/start", headers=_h(owner))
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"
    assert started.json()["assignee_user_id"] is not None  # starter becomes assignee

    no_outcome = client.post(f"{base}/complete", json={}, headers=_h(owner))
    assert no_outcome.status_code == 422
    done = client.post(
        f"{base}/complete",
        json={"outcome": "coached", "outcome_notes": "Sürücüyle görüşüldü"},
        headers=_h(owner),
    )
    assert done.status_code == 200
    assert done.json()["outcome_label"] == "Sürücüyle görüşme yapıldı"
    assert done.json()["completed_at"] is not None

    assert client.post(f"{base}/start", headers=_h(owner)).status_code == 409
    assert client.patch(base, json={"notes": "x"}, headers=_h(owner)).status_code == 409

    # A completed action no longer blocks a new one for the same event.
    new_action = _review(client, owner, event_id).json()["coaching_action_id"]
    assert new_action != action_id
    no_reason = client.post(
        f"/api/v1/coaching-actions/{new_action}/cancel", json={"reason": ""}, headers=_h(owner)
    )
    assert no_reason.status_code == 422
    canceled = client.post(
        f"/api/v1/coaching-actions/{new_action}/cancel",
        json={"reason": "Sürücü görevden ayrıldı"},
        headers=_h(owner),
    )
    assert canceled.json()["status"] == "canceled"


async def test_assignment_rules_and_notification(
    client: TestClient, test_settings: Settings
) -> None:
    owner, event_id, _ = await _org_with_event(client, test_settings, "coach-assign")
    coach = await invite_and_login(
        client, test_settings, owner, "koc@coach-assign.example", "coach"
    )
    analyst = await invite_and_login(
        client, test_settings, owner, "an@coach-assign.example", "analyst"
    )

    assignees = client.get("/api/v1/coaching-actions/assignees", headers=_h(owner)).json()
    emails = {a["email"] for a in assignees}
    assert "koc@coach-assign.example" in emails
    assert "an@coach-assign.example" not in emails

    bad = _review(client, owner, event_id, coaching_assignee_user_id=analyst["user"]["id"])  # type: ignore[index]
    assert bad.status_code == 422

    good = _review(
        client,
        owner,
        event_id,
        coaching_assignee_user_id=coach["user"]["id"],  # type: ignore[index]
        coaching_due_at=(datetime.now(UTC) + timedelta(days=3)).isoformat(),
    )
    assert good.status_code == 200, good.text
    await deliver_mail(test_settings)
    email = last_email_to("koc@coach-assign.example", "koçluk görevi")
    assert f"/panel/kocluk/{good.json()['coaching_action_id']}" in email.text_body

    mine = client.get("/api/v1/coaching-actions?assigned_to_me=true", headers=_h(coach)).json()
    assert mine["total"] == 1
    assert client.get("/api/v1/coaching-actions", headers=_h(analyst)).status_code == 403


async def test_reviewer_without_coaching_permission(
    client: TestClient, test_settings: Settings
) -> None:
    owner, event_id, _ = await _org_with_event(client, test_settings, "coach-reviewer")
    reviewer = await invite_and_login(
        client, test_settings, owner, "inc@coach-reviewer.example", "event_reviewer"
    )
    coach = await invite_and_login(
        client, test_settings, owner, "koc@coach-reviewer.example", "coach"
    )

    with_assignee = _review(
        client, reviewer, event_id, coaching_assignee_user_id=coach["user"]["id"]
    )  # type: ignore[index]
    assert with_assignee.status_code == 422
    unassigned = _review(client, reviewer, event_id)
    assert unassigned.status_code == 200
    assert unassigned.json()["coaching_action_id"]


async def test_tenant_isolation_and_driver_scoping(
    client: TestClient, test_settings: Settings
) -> None:
    owner_a, event_a, driver_a = await _org_with_event(client, test_settings, "coach-iso-a")
    owner_b, _event_b, _ = await _org_with_event(client, test_settings, "coach-iso-b")
    action_id = _review(client, owner_a, event_a).json()["coaching_action_id"]

    base = f"/api/v1/coaching-actions/{action_id}"
    assert client.get(base, headers=_h(owner_b)).status_code == 404
    assert client.patch(base, json={"notes": "saldırı"}, headers=_h(owner_b)).status_code == 404
    assert client.post(f"{base}/start", headers=_h(owner_b)).status_code == 404
    assert client.get("/api/v1/coaching-actions", headers=_h(owner_b)).json()["total"] == 0
    forged = client.post(
        "/api/v1/coaching-actions", json={"safety_event_id": event_a}, headers=_h(owner_b)
    )
    assert forged.status_code == 404

    # A self-service driver only sees actions for the driver linked to them.
    driver_user = await invite_and_login(
        client, test_settings, owner_a, "surucu@coach-iso-a.example", "driver"
    )
    assert client.get("/api/v1/coaching-actions", headers=_h(driver_user)).json()["total"] == 0
    engine = build_engine(test_settings)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.rls_bypass', 'on', true)"))
            await conn.execute(
                text("UPDATE drivers SET user_id = :u WHERE id = :d"),
                {"u": driver_user["user"]["id"], "d": driver_a},  # type: ignore[index]
            )
    finally:
        await engine.dispose()
    visible = client.get("/api/v1/coaching-actions", headers=_h(driver_user)).json()
    assert visible["total"] == 1
    assert client.post(f"{base}/start", headers=_h(driver_user)).status_code == 403


async def test_concurrent_creates_resolve_to_one_action(
    client: TestClient, test_settings: Settings
) -> None:
    owner, event_id, _ = await _org_with_event(client, test_settings, "coach-race")
    tenant_id = uuid.UUID(str(owner["user"]["organization_id"]))  # type: ignore[index]
    ctx = RequestContext(
        user_id=uuid.UUID(str(owner["user"]["id"])),  # type: ignore[index]
        organization_id=tenant_id,
        role=RoleKey.OWNER,
        is_platform_admin=False,
        actor_label="test",
    )
    engine = build_engine(test_settings)
    factory = build_session_factory(engine)

    async def create() -> uuid.UUID:
        async with factory() as session:
            await set_tenant(session, tenant_id)
            action, _ = await CoachingService(session).create_action(
                ctx, tenant_id, title=None, safety_event_id=uuid.UUID(event_id)
            )
            await session.commit()
            return action.id

    try:
        ids = await asyncio.gather(create(), create(), create())
    finally:
        await engine.dispose()
    assert len(set(ids)) == 1
    listing = client.get(
        f"/api/v1/coaching-actions?safety_event_id={event_id}", headers=_h(owner)
    ).json()
    assert listing["total"] == 1


async def test_summary_overdue_and_csv_report(client: TestClient, test_settings: Settings) -> None:
    owner, event_id, _ = await _org_with_event(client, test_settings, "coach-summary")
    action_id = _review(client, owner, event_id).json()["coaching_action_id"]
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    patched = client.patch(
        f"/api/v1/coaching-actions/{action_id}", json={"due_at": past}, headers=_h(owner)
    )
    assert patched.status_code == 200
    assert patched.json()["is_overdue"] is True

    summary = client.get("/api/v1/coaching-actions/summary", headers=_h(owner)).json()
    assert summary["open"] == 1
    assert summary["overdue"] == 1
    assert (
        client.get("/api/v1/coaching-actions?overdue=true", headers=_h(owner)).json()["total"] == 1
    )

    report = client.get("/api/v1/reports/coaching.csv", headers=_h(owner))
    assert report.status_code == 200
    assert "attachment" in report.headers["Content-Disposition"]
    assert "Koçluk" in report.text
    assert action_id in report.text
    assert "Gecikmiş" in report.text
