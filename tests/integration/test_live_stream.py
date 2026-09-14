"""Live operations stream (SSE) and the LISTEN/NOTIFY hub."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi.testclient import TestClient

from tests.helpers import auth_headers, invite_and_login
from tests.integration.test_coaching import _org_with_event
from visionroute.config.settings import Settings
from visionroute.infrastructure.db.engine import build_engine, build_session_factory
from visionroute.infrastructure.realtime import LiveEventHub, notify_live


def _events(body: str) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for block in body.split("\n\n"):
        event, data = "message", []
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data.append(line.removeprefix("data: "))
        if data:
            parsed.append((event, "\n".join(data)))
    return parsed


async def test_stream_sends_snapshot_and_ends(client: TestClient, test_settings: Settings) -> None:
    owner, _, _ = await _org_with_event(client, test_settings, "sse-snap")
    with client.stream(
        "GET", "/api/v1/operations/stream?max_seconds=1", headers=auth_headers(owner)
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-store"
        body = "".join(response.iter_text())

    events = _events(body)
    assert events[0][0] == "live"
    vehicles = json.loads(events[0][1])
    assert len(vehicles) == 1 and vehicles[0]["is_stale"] in (True, False)
    assert events[-1] == ("end", '{"reason": "timeout"}')


async def test_stream_requires_authentication_and_permission(
    client: TestClient, test_settings: Settings
) -> None:
    owner, _, _ = await _org_with_event(client, test_settings, "sse-auth")
    assert client.get("/api/v1/operations/stream?max_seconds=1").status_code == 401
    coach = await invite_and_login(client, test_settings, owner, "koc@sse-auth.example", "coach")
    denied = client.get("/api/v1/operations/stream?max_seconds=1", headers=auth_headers(coach))
    assert denied.status_code == 403
    too_long = client.get("/api/v1/operations/stream?max_seconds=4000", headers=auth_headers(owner))
    assert too_long.status_code == 422


async def test_hub_delivers_committed_notifications_per_tenant(test_settings: Settings) -> None:
    hub = LiveEventHub(test_settings.database_url)
    engine = build_engine(test_settings)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    try:
        await hub.start()
        await asyncio.wait_for(hub.connected.wait(), timeout=10)
        queue_a = hub.subscribe(org_a)
        queue_b = hub.subscribe(org_b)
        factory = build_session_factory(engine)

        # Rolled-back notifications are never delivered.
        async with factory() as session:
            await notify_live(session, org_a, "positions")
            await session.rollback()
        async with factory() as session:
            await notify_live(session, org_a, "safety_event")
            await session.commit()

        assert await asyncio.wait_for(queue_a.get(), timeout=5) == "safety_event"
        assert queue_a.empty()
        assert queue_b.empty()  # other tenants are not notified

        hub.unsubscribe(org_a, queue_a)
        hub.unsubscribe(org_b, queue_b)
        assert hub.subscriber_count() == 0
    finally:
        await hub.close()
        await engine.dispose()
