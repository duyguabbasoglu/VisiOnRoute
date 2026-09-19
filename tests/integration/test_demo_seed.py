"""Synthetic demo seed: gates, idempotency, provenance, and dashboard reads.

The seed must go through the real pipeline, so every assertion about the
populated dashboard is made through the normal authenticated API endpoints.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.helpers import (
    auth_headers,
    create_org_and_login,
    deliver_mail,
    invite_and_login,
    last_email_to,
    token_from,
)
from visionroute.config.settings import Environment, Settings
from visionroute.infrastructure.db.engine import build_engine, build_session_factory
from visionroute.infrastructure.db.models.ingestion import IngestEvent
from visionroute.infrastructure.db.tenancy import set_rls_bypass
from visionroute.worker.runner import Worker

SEED = "/api/v1/demo-data/seed"
STATUS = "/api/v1/demo-data"


@contextmanager
def demo_environment(client: TestClient, settings: Settings) -> Iterator[None]:
    """Serve requests as VISIONROUTE_ENVIRONMENT=demo.

    A real demo app refuses to start without TLS, S3, SMTP and Redis, so the
    running test app's settings are swapped instead of building a new app."""
    app_state = client.app.state  # type: ignore[attr-defined]
    app_state.settings = settings.model_copy(update={"environment": Environment.DEMO})
    try:
        yield
    finally:
        app_state.settings = settings


async def verified_owner(client: TestClient, settings: Settings, slug: str) -> dict[str, object]:
    email = f"sahip@{slug}.example"
    owner = create_org_and_login(client, slug, email)
    await deliver_mail(settings)
    token = token_from(last_email_to(email, "doğrulayın"))
    assert client.post("/api/v1/auth/email/verify", json={"token": token}).status_code == 200
    return owner


def _vehicle_count(client: TestClient, headers: dict[str, str]) -> int:
    return int(client.get("/api/v1/vehicles", headers=headers).json()["pagination"]["total"])


def _error_code(response: object) -> str:
    return str(response.json()["error"]["code"])  # type: ignore[attr-defined]


async def test_non_demo_environment_is_denied(client: TestClient, test_settings: Settings) -> None:
    owner = await verified_owner(client, test_settings, "demo-seed-local")
    denied = client.post(SEED, headers=auth_headers(owner))
    assert denied.status_code == 403
    assert _error_code(denied) == "DEMO_DATA_UNAVAILABLE"

    status = client.get(STATUS, headers=auth_headers(owner)).json()
    assert status == {
        "available": False,
        "seeded": False,
        "reason": "environment",
        "message": "Sentetik demo verisi yalnızca demo ortamında oluşturulabilir.",
    }
    assert _vehicle_count(client, auth_headers(owner)) == 0


async def test_unauthenticated_and_unauthorised_callers_are_denied(
    client: TestClient, test_settings: Settings
) -> None:
    owner = await verified_owner(client, test_settings, "demo-seed-deny")
    analyst = await invite_and_login(
        client, test_settings, owner, "analist@demo-seed-deny.example", "analyst"
    )
    unverified = create_org_and_login(client, "demo-seed-unverified", "u@demo-seed-unv.example")

    with demo_environment(client, test_settings):
        assert client.post(SEED).status_code == 401

        forbidden = client.post(SEED, headers=auth_headers(analyst))
        assert forbidden.status_code == 403
        assert _error_code(forbidden) == "DEMO_DATA_FORBIDDEN"
        assert client.get(STATUS, headers=auth_headers(analyst)).json()["reason"] == "role"

        not_verified = client.post(SEED, headers=auth_headers(unverified))
        assert not_verified.status_code == 403
        assert _error_code(not_verified) == "EMAIL_NOT_VERIFIED"

    # None of the denied calls wrote anything.
    assert _vehicle_count(client, auth_headers(owner)) == 0
    assert _vehicle_count(client, auth_headers(unverified)) == 0


async def test_verified_owner_seeds_real_dashboard_idempotently(
    client: TestClient, test_settings: Settings
) -> None:
    owner = await verified_owner(client, test_settings, "demo-seed-ok")
    other = await verified_owner(client, test_settings, "demo-seed-other")
    h = auth_headers(owner)

    with demo_environment(client, test_settings):
        before = client.get(STATUS, headers=h).json()
        assert before == {"available": True, "seeded": False, "reason": None, "message": None}

        response = client.post(SEED, headers=h)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["created"] is True
        assert (body["data_origin"], body["environment"]) == ("synthetic", "demo")
        summary = body["summary"]
        assert summary["vehicles"] == 3
        assert summary["drivers"] == 4
        assert summary["trips"] == 9
        assert summary["telemetry_points"] == 3 * (70 + 70 + 40)
        assert summary["safety_events"] >= 8
        assert summary["road_risks"] >= 2

        # Repeated clicks do not duplicate anything.
        again = client.post(SEED, headers=h)
        assert again.status_code == 200
        assert again.json()["created"] is False
        assert again.json()["summary"] == summary
        after = client.get(STATUS, headers=h).json()
        assert after["seeded"] is True
        assert after["available"] is False

    # Fleet: fictional DMO vehicles, pseudonymous drivers, open assignments.
    vehicles = client.get("/api/v1/vehicles", headers=h).json()["items"]
    assert sorted(v["plate"] for v in vehicles) == ["06 DMO 101", "06 DMO 102", "06 DMO 103"]
    drivers = client.get("/api/v1/drivers", headers=h).json()["items"]
    assert all(d["full_name"].startswith("Demo Sürücü") for d in drivers)
    assignments = client.get("/api/v1/assignments", headers=h).json()
    assert len([a for a in assignments if a["ended_at"] is None]) == 3

    # Data source is the simulator and counted every envelope as accepted.
    sources = client.get("/api/v1/integrations/data-sources", headers=h).json()
    assert [(s["kind"], s["accepted_count"], s["rejected_count"]) for s in sources] == [
        ("simulator", 540, 0)
    ]

    # Live map: one fresh active trip per vehicle; finished trips are completed.
    live = client.get("/api/v1/operations/live", headers=h).json()
    assert len(live) == 3
    assert not any(v["is_stale"] for v in live)
    trips = client.get("/api/v1/trips?limit=50", headers=h).json()
    assert sorted(t["status"] for t in trips) == ["active"] * 3 + ["completed"] * 6
    trail = client.get(f"/api/v1/trips/{trips[0]['id']}/trail", headers=h).json()
    assert len(trail) >= 40

    # Safety events: produced by the rule engine, all marked synthetic.
    events = client.get("/api/v1/safety-events?limit=100", headers=h).json()
    assert events["total"] == summary["safety_events"]
    types = {e["event_type"] for e in events["items"]}
    assert {"harsh_braking", "harsh_acceleration", "harsh_cornering", "speeding"} <= types
    assert {e["data_origin"] for e in events["items"]} == {"synthetic"}
    assert all(e["latitude"] is not None for e in events["items"])

    # Overview KPIs and analytics read the same data.
    risks = client.get("/api/v1/road-risks", headers=h).json()
    assert len(risks) == summary["road_risks"]
    scored = [
        client.get(f"/api/v1/drivers/{d['id']}/risk-score", headers=h).json() for d in drivers
    ]
    assert sum(1 for s in scored if s["has_sufficient_exposure"]) == 3

    # Tenant isolation: the other organization still sees an empty dashboard.
    oh = auth_headers(other)
    assert _vehicle_count(client, oh) == 0
    assert client.get("/api/v1/safety-events", headers=oh).json()["total"] == 0
    assert client.get("/api/v1/operations/live", headers=oh).json() == []


async def test_seeded_envelopes_carry_synthetic_markers_and_worker_does_not_reprocess(
    client: TestClient, test_settings: Settings
) -> None:
    owner = await verified_owner(client, test_settings, "demo-seed-markers")
    h = auth_headers(owner)
    with demo_environment(client, test_settings):
        assert client.post(SEED, headers=h).status_code == 200
    me = client.get("/api/v1/auth/me", headers=h).json()
    org_id = me["organization_id"]

    engine = build_engine(test_settings)
    try:
        async with build_session_factory(engine)() as session:
            await set_rls_bypass(session)
            rows = (
                await session.execute(
                    select(IngestEvent.status, IngestEvent.envelope).where(
                        IngestEvent.organization_id == org_id
                    )
                )
            ).all()
    finally:
        await engine.dispose()
    assert len(rows) == 540
    assert {status for status, _ in rows} == {"processed"}
    for _, envelope in rows:
        payload = envelope["payload"]
        assert (payload["data_origin"], payload["environment"]) == ("synthetic", "demo")

    # The ingestion outbox events are still delivered to the worker, which finds
    # them processed and must not create a second copy of any point.
    points_before = client.get("/api/v1/trips?limit=50", headers=h).json()
    worker = Worker(test_settings)
    try:
        for _ in range(30):
            if await worker.run_once() == 0:
                break
    finally:
        await worker._engine.dispose()
    points_after = client.get("/api/v1/trips?limit=50", headers=h).json()
    assert sorted(t["point_count"] for t in points_after) == sorted(
        t["point_count"] for t in points_before
    )
