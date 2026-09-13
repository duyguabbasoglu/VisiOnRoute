"""Request hardening: correlation-ID sanitisation and body size limits."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from visionroute.api.main import create_app
from visionroute.api.middleware import safe_request_id
from visionroute.config.settings import Settings


@pytest.fixture(scope="module")
def small_body_client() -> Iterator[TestClient]:
    settings = Settings(_env_file=None, max_request_body_bytes=2048)  # type: ignore[call-arg]
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


def test_safe_request_id_accepts_log_safe_values() -> None:
    assert safe_request_id("istek-42:a.b_c") == "istek-42:a.b_c"


@pytest.mark.parametrize("candidate", ["a" * 65, "<script>", "boşluk var", "", None])
def test_safe_request_id_replaces_unsafe_values(candidate: str | None) -> None:
    replaced = safe_request_id(candidate)
    assert replaced != candidate
    uuid.UUID(replaced)  # a fresh, valid UUID


def test_unsafe_request_id_header_is_not_echoed(small_body_client: TestClient) -> None:
    response = small_body_client.get("/health/live", headers={"X-Request-ID": "x" * 200})
    assert response.headers["X-Request-ID"] != "x" * 200


def test_declared_oversized_body_rejected(small_body_client: TestClient) -> None:
    response = small_body_client.post("/api/v1/auth/login", content=b"{" + b" " * 4096 + b"}")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_chunked_oversized_body_rejected(small_body_client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(10):
            yield b" " * 1024

    response = small_body_client.post(
        "/api/v1/auth/login",
        content=chunks(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
