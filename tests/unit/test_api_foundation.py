"""API foundation tests: health, error envelope, security headers."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from visionroute.api.main import create_app
from visionroute.config.settings import Settings


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_liveness(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_database_without_leaking_config(client: TestClient) -> None:
    response = client.get("/health/ready")
    body = response.json()
    assert set(body) == {"status", "checks"}
    assert "database" in body["checks"]
    # No connection strings, hosts or credentials in the payload.
    assert "postgresql" not in response.text
    assert "visionroute:" not in response.text


def test_unknown_route_returns_turkish_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/yok-boyle-bir-yol")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Kayıt bulunamadı."
    assert body["error"]["request_id"]


def test_request_id_is_propagated(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "test-korelasyon-42"})
    assert response.headers["X-Request-ID"] == "test-korelasyon-42"


def test_security_headers_present(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
