"""Refresh-token retry window: a lost rotation response may be retried, while
every theft signal still revokes the whole token family."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.helpers import DEFAULT_PASSWORD, create_org_and_login
from visionroute.api.main import create_app
from visionroute.config.settings import Settings
from visionroute.infrastructure.db.engine import build_engine
from visionroute.infrastructure.security.tokens import hash_opaque_secret

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def retry_client(test_settings: Settings) -> Iterator[TestClient]:
    settings = test_settings.model_copy(update={"refresh_reuse_grace_seconds": 30})
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client


def _login(client: TestClient, slug: str) -> str:
    email = f"r@{slug}.example"
    create_org_and_login(client, slug, email)
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200
    token = response.cookies["vr_refresh"]
    client.cookies.clear()
    return token


def _refresh(client: TestClient, token: str, user_agent: str | None = None) -> tuple[int, str]:
    client.cookies.clear()
    client.cookies.set("vr_refresh", token, path="/api/v1/auth")
    headers = {"User-Agent": user_agent} if user_agent else {}
    response = client.post("/api/v1/auth/refresh", headers=headers)
    new_token = response.cookies.get("vr_refresh", "")
    client.cookies.clear()
    return response.status_code, new_token


def test_lost_rotation_response_can_be_retried(retry_client: TestClient) -> None:
    first = _login(retry_client, "yenileme-kayip")
    status, _lost = _refresh(retry_client, first)
    assert status == 200
    status, retried = _refresh(retry_client, first)
    assert status == 200 and retried not in (first, _lost)
    status, _ = _refresh(retry_client, retried)
    assert status == 200


def test_superseded_successor_revokes_family(retry_client: TestClient) -> None:
    first = _login(retry_client, "yenileme-eski")
    _, lost = _refresh(retry_client, first)
    _, retried = _refresh(retry_client, first)
    # The lost successor was replaced; presenting it later is a theft signal.
    assert _refresh(retry_client, lost)[0] == 401
    assert _refresh(retry_client, retried)[0] == 401


def test_reuse_after_successor_was_used_revokes_family(retry_client: TestClient) -> None:
    first = _login(retry_client, "yenileme-kullanilmis")
    _, second = _refresh(retry_client, first)
    status, third = _refresh(retry_client, second)
    assert status == 200
    assert _refresh(retry_client, first)[0] == 401
    assert _refresh(retry_client, third)[0] == 401


async def test_retry_outside_window_revokes_family(
    retry_client: TestClient, test_settings: Settings
) -> None:
    first = _login(retry_client, "yenileme-gec")
    _, second = _refresh(retry_client, first)
    engine = build_engine(test_settings)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE sessions SET revoked_at = revoked_at - interval '5 minutes' "
                    "WHERE refresh_token_hash = :digest"
                ),
                {"digest": hash_opaque_secret(first)},
            )
    finally:
        await engine.dispose()
    assert _refresh(retry_client, first)[0] == 401
    assert _refresh(retry_client, second)[0] == 401


def test_retry_from_another_user_agent_revokes_family(retry_client: TestClient) -> None:
    first = _login(retry_client, "yenileme-ajan")
    _, second = _refresh(retry_client, first)
    assert _refresh(retry_client, first, user_agent="baska-cihaz/1.0")[0] == 401
    assert _refresh(retry_client, second)[0] == 401


def test_logged_out_token_is_never_revived(retry_client: TestClient) -> None:
    first = _login(retry_client, "yenileme-cikis")
    _, second = _refresh(retry_client, first)
    retry_client.cookies.set("vr_refresh", second, path="/api/v1/auth")
    logout = retry_client.post("/api/v1/auth/logout")
    retry_client.cookies.clear()
    assert logout.status_code in (200, 204)
    assert _refresh(retry_client, first)[0] == 401
    assert _refresh(retry_client, second)[0] == 401
