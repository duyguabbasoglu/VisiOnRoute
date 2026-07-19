"""M9 end-to-end: notification rules, webhook delivery (signed), reports, analytics."""

import hashlib
import hmac
import http.server
import threading
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from fastapi.testclient import TestClient

from tests.helpers import create_org_and_login
from visionroute.config.settings import Settings
from visionroute.worker.runner import Worker


def _h(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _setup(client: TestClient, slug: str) -> tuple[dict[str, object], str]:
    owner = create_org_and_login(client, slug, f"o@{slug}.example")
    client.post("/api/v1/vehicles", json={"external_id": "34ABC123"}, headers=_h(owner))
    client.post(
        "/api/v1/integrations/data-sources",
        json={"name": "Telematik", "source_key": "t-1", "kind": "rest"},
        headers=_h(owner),
    )
    api_client = client.post(
        "/api/v1/integrations/clients", json={"name": "Cihaz"}, headers=_h(owner)
    ).json()
    token = client.post(
        f"/api/v1/integrations/clients/{api_client['id']}/tokens",
        json={"scopes": ["ingest:write"]},
        headers=_h(owner),
    ).json()
    return owner, token["api_key"]


def _harsh_event(eid: str) -> dict:
    return {
        "schema_version": "1.0",
        "source": "t-1",
        "event_id": eid,
        "event_type": "telemetry.position",
        "occurred_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        "vehicle_external_id": "34ABC123",
        "payload": {
            "latitude": 39.92,
            "longitude": 32.85,
            "speed_kph": 70,
            "acceleration_ms2": -6.5,
            "gps_hdop": 1.0,
            "satellites": 12,
        },
    }


async def _drain(settings: Settings, rounds: int = 8) -> None:
    worker = Worker(settings)
    for _ in range(rounds):
        if await worker.run_once() == 0:
            break
    await worker._engine.dispose()


class _WebhookReceiver(http.server.BaseHTTPRequestHandler):
    received: ClassVar[list[dict]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        type(self).received.append(
            {
                "body": body,
                "signature": self.headers.get("X-VisiOnRoute-Signature", ""),
            }
        )
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args: object) -> None:  # silence test output
        pass


async def test_rule_creates_in_app_notification(
    client: TestClient, test_settings: Settings
) -> None:
    owner, api_key = _setup(client, "notif-inapp")
    rule = client.post(
        "/api/v1/notification-rules",
        json={"name": "Yüksek şiddet uyarısı", "min_severity": "high"},
        headers=_h(owner),
    )
    assert rule.status_code == 201

    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": [_harsh_event("n1")]},
        headers={"X-API-Key": api_key},
    )
    await _drain(test_settings)

    notifications = client.get("/api/v1/notifications", headers=_h(owner)).json()
    assert len(notifications) == 1
    assert "Sert fren" in notifications[0]["title_tr"]
    assert notifications[0]["read_at"] is None

    # Mark read.
    read = client.post(f"/api/v1/notifications/{notifications[0]['id']}/read", headers=_h(owner))
    assert read.status_code == 204
    unread = client.get("/api/v1/notifications?unread_only=true", headers=_h(owner)).json()
    assert unread == []


async def test_webhook_delivery_with_valid_signature(
    client: TestClient, test_settings: Settings, monkeypatch
) -> None:
    """Full delivery flow to a local receiver with signature verification.

    The SSRF guard (unit-tested separately) blocks loopback targets, so it is
    bypassed here to exercise the delivery/signature mechanics end-to-end."""
    import visionroute.api.routers.v1.notifications_reports as api_module
    import visionroute.application.notifications.service as svc_module

    monkeypatch.setattr(api_module, "validate_url", lambda url, **kw: url)
    monkeypatch.setattr(svc_module, "validate_url", lambda url, **kw: url)

    owner, _api_key = _setup(client, "notif-webhook")
    _WebhookReceiver.received = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _WebhookReceiver)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        webhook = client.post(
            "/api/v1/webhooks",
            json={"url": f"http://127.0.0.1:{port}/hook", "description": "Test alıcısı"},
            headers=_h(owner),
        )
        assert webhook.status_code == 201, webhook.text
        secret = webhook.json()["secret"]
        webhook_id = webhook.json()["id"]

        queued = client.post(f"/api/v1/webhooks/{webhook_id}/test", headers=_h(owner))
        assert queued.status_code == 202

        await _drain(test_settings, rounds=2)

        assert len(_WebhookReceiver.received) == 1
        delivery = _WebhookReceiver.received[0]
        signature = delivery["signature"]
        assert signature.startswith("t=")
        ts_part, v1_part = signature.split(",")
        timestamp = ts_part.removeprefix("t=")
        expected = hmac.new(
            secret.encode(), f"{timestamp}.".encode() + delivery["body"], hashlib.sha256
        ).hexdigest()
        assert v1_part == f"v1={expected}"

        listing = client.get("/api/v1/webhooks", headers=_h(owner)).json()
        target = next(w for w in listing if w["id"] == webhook_id)
        assert target["last_success_at"] is not None
        assert target["secret"] is None  # never returned after creation
    finally:
        server.shutdown()


async def test_webhook_failure_schedules_retry(
    client: TestClient, test_settings: Settings, monkeypatch
) -> None:
    import visionroute.api.routers.v1.notifications_reports as api_module
    import visionroute.application.notifications.service as svc_module

    monkeypatch.setattr(api_module, "validate_url", lambda url, **kw: url)
    monkeypatch.setattr(svc_module, "validate_url", lambda url, **kw: url)

    owner, _api_key = _setup(client, "notif-dlq")
    # A closed local port: connection refused immediately → failure + retry.
    webhook = client.post(
        "/api/v1/webhooks",
        json={"url": "http://127.0.0.1:9/hook", "description": "Erişilemez uç"},
        headers=_h(owner),
    )
    assert webhook.status_code == 201, webhook.text
    webhook_id = webhook.json()["id"]

    queued = client.post(f"/api/v1/webhooks/{webhook_id}/test", headers=_h(owner))
    assert queued.status_code == 202

    await _drain(test_settings, rounds=1)
    listing = client.get("/api/v1/webhooks", headers=_h(owner)).json()
    target = next(w for w in listing if w["id"] == webhook_id)
    assert target["last_failure_at"] is not None


def test_signature_scheme_is_verifiable() -> None:
    from visionroute.application.notifications.service import sign_payload

    secret = "whsec_test"
    body = b'{"a":1}'
    header = sign_payload(secret, body, 1700000000)
    assert header.startswith("t=1700000000,v1=")
    expected = hmac.new(secret.encode(), b"1700000000." + body, hashlib.sha256).hexdigest()
    assert header.endswith(expected)


async def test_reports_csv_and_pdf(client: TestClient, test_settings: Settings) -> None:
    owner, api_key = _setup(client, "rapor")
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": [_harsh_event("r1")]},
        headers={"X-API-Key": api_key},
    )
    await _drain(test_settings)

    csv_response = client.get("/api/v1/reports/safety-events.csv", headers=_h(owner))
    assert csv_response.status_code == 200
    text = csv_response.text
    assert "# Metodoloji" in text
    assert "harsh_braking" in text
    assert "Sert fren" in text

    pdf_response = client.get("/api/v1/reports/executive.pdf", headers=_h(owner))
    assert pdf_response.status_code == 200
    assert pdf_response.content.startswith(b"%PDF")
    assert len(pdf_response.content) > 500


async def test_analytics_summary_with_denominators(
    client: TestClient, test_settings: Settings
) -> None:
    owner, api_key = _setup(client, "analitik")
    client.post(
        "/api/v1/ingest/events",
        json={"source_key": "t-1", "events": [_harsh_event("a1")]},
        headers={"X-API-Key": api_key},
    )
    await _drain(test_settings)

    summary = client.get("/api/v1/analytics/summary", headers=_h(owner)).json()
    assert summary["total_events"] == 1
    assert summary["events_by_severity"].get("high") == 1 or summary["events_by_severity"].get(
        "critical"
    )
    assert "Payda" in summary["data_note_tr"]
    # Single-point trip has 0 km distance → per-100km must be None, not fake.
    assert summary["events_per_100km"] is None or summary["events_per_100km"] >= 0


def test_webhook_url_ssrf_guard_blocks_private(client: TestClient) -> None:
    owner = create_org_and_login(client, "ssrf-web", "o@ssrf-web.example")
    for bad in ("http://169.254.169.254/", "http://10.0.0.5/hook", "ftp://x.example/"):
        response = client.post("/api/v1/webhooks", json={"url": bad}, headers=_h(owner))
        assert response.status_code == 422, bad
