"""Rate limiting on authentication endpoints and the Redis adapter."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from visionroute.api.main import create_app
from visionroute.config.settings import Settings
from visionroute.infrastructure.ratelimit import RedisRateLimiter


@pytest.fixture(scope="module")
def limited_client(test_settings: Settings) -> Iterator[TestClient]:
    settings = test_settings.model_copy(
        update={
            "login_rate_limit_per_minute": 3,
            "login_ip_rate_limit_per_minute": 5,
            "token_rate_limit_per_minute": 2,
        }
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


def test_login_limited_per_ip_and_email(limited_client: TestClient) -> None:
    body = {"email": "kaba-kuvvet@ornek.example", "password": "YanlisParola!!1"}
    statuses = [limited_client.post("/api/v1/auth/login", json=body).status_code for _ in range(4)]
    assert statuses[:3] == [401, 401, 401]
    assert statuses[3] == 429

    blocked = limited_client.post("/api/v1/auth/login", json=body)
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert "Çok fazla istek" in blocked.json()["error"]["message"]
    assert int(blocked.headers["Retry-After"]) >= 1


def test_login_ip_limit_applies_across_emails(limited_client: TestClient) -> None:
    # The per-IP budget (5) was partly consumed above; rotating e-mails does
    # not bypass it.
    responses = [
        limited_client.post(
            "/api/v1/auth/login",
            json={"email": f"u{i}@ornek.example", "password": "YanlisParola!!1"},
        ).status_code
        for i in range(6)
    ]
    assert 429 in responses


def test_refresh_endpoint_limited(limited_client: TestClient) -> None:
    statuses = [limited_client.post("/api/v1/auth/refresh").status_code for _ in range(3)]
    assert statuses[:2] == [401, 401]
    assert statuses[2] == 429


async def test_redis_limiter_shares_counters_between_instances() -> None:
    key = f"test:{uuid.uuid4()}"
    first = RedisRateLimiter.from_url("redis://localhost:6379/15")
    second = RedisRateLimiter.from_url("redis://localhost:6379/15")
    try:
        assert (await first.hit(key, limit=2, window_seconds=60)).allowed
        assert (await second.hit(key, limit=2, window_seconds=60)).allowed
        decision = await first.hit(key, limit=2, window_seconds=60)
        assert decision.allowed is False
        assert decision.retry_after_seconds >= 1
    finally:
        await first.close()
        await second.close()


async def test_redis_outage_fails_open() -> None:
    unreachable = RedisRateLimiter.from_url("redis://127.0.0.1:1/0")
    try:
        decision = await unreachable.hit("any", limit=1, window_seconds=60)
        assert decision.allowed is True
    finally:
        await unreachable.close()
