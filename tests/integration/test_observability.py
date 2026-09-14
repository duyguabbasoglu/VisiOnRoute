"""Metrics endpoint protection/content and readiness semantics."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from visionroute.api.main import create_app
from visionroute.config.settings import Settings

TOKEN = "metrik-okuma-anahtari-" + "x" * 20


@pytest.fixture(scope="module")
def metrics_client(test_settings: Settings) -> Iterator[TestClient]:
    settings = test_settings.model_copy(update={"metrics_token": SecretStr(TOKEN)})
    with TestClient(create_app(settings)) as client:
        yield client


def test_metrics_disabled_without_token(client: TestClient) -> None:
    assert client.get("/metrics").status_code == 404


def test_metrics_require_bearer_token(metrics_client: TestClient) -> None:
    assert metrics_client.get("/metrics").status_code == 401
    wrong = metrics_client.get("/metrics", headers={"Authorization": "Bearer yanlis"})
    assert wrong.status_code == 401


def test_metrics_expose_http_and_queue_series(metrics_client: TestClient) -> None:
    metrics_client.get("/health/live")
    metrics_client.get("/api/v1/safety-events/00000000-0000-0000-0000-000000000000")
    response = metrics_client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert 'visionroute_http_requests_total{method="GET",route="/health/live",status="200"}' in body
    # Route templates (router-relative), never raw identifiers, as label values.
    assert 'route="/safety-events/{event_id}"' in body
    assert "00000000-0000-0000-0000-000000000000" not in body
    for series in (
        'visionroute_queue_depth{queue="outbox",state="pending"}',
        'visionroute_queue_depth{queue="privacy",state="failed"}',
        'visionroute_queue_oldest_pending_seconds{queue="email"}',
        "visionroute_live_hub_connected",
    ):
        assert series in body
    assert TOKEN not in body


def test_readiness_checks_database_and_migration_head(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] is True
    assert body["checks"]["migrations"] is True
    assert body["checks"]["rate_limiter"] is True


def test_production_rejects_short_metrics_token() -> None:
    from visionroute.config.settings import Environment

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, environment=Environment.PRODUCTION, metrics_token=SecretStr("kisa")
    )
    assert any("Metrik erişim anahtarı" in p for p in settings.validate_for_runtime())
