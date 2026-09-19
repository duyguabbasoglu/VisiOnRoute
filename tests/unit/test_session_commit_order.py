"""Request sessions must commit before the response reaches the client.

With FastAPI's default ("request") dependency scope, code after ``yield`` runs
after the response is sent: a client could receive a 201 and immediately
issue a request that does not yet see the committed row (the intermittent E2E
"API istemcisi bulunamadı" 404). TestClient waits for teardown, so this is
checked through a real uvicorn server.
"""

from __future__ import annotations

import asyncio
import socket
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any, get_args

import httpx
import pytest
import uvicorn
from fastapi import Depends, FastAPI

from visionroute.api.deps import PlatformSession, TenantSession
from visionroute.api.ingest_deps import IngestSession


@pytest.mark.parametrize("alias", [TenantSession, PlatformSession, IngestSession])
def test_session_dependencies_are_function_scoped(alias: Any) -> None:
    depends = get_args(alias)[1]
    assert depends.scope == "function"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


_finished: list[float] = []


async def _slow_commit_session() -> AsyncIterator[None]:
    yield
    await asyncio.sleep(0.3)  # a slow commit
    _finished.append(time.monotonic())


_app = FastAPI()


@_app.post("/write")
async def _write(
    _: Annotated[None, Depends(_slow_commit_session, scope="function")],
) -> dict[str, str]:
    return {}


async def test_function_scoped_teardown_finishes_before_response_is_sent() -> None:
    _finished.clear()
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(_app, host="127.0.0.1", port=port, log_level="error"))
    serving = asyncio.create_task(server.serve())
    try:
        while not server.started:  # noqa: ASYNC110 — uvicorn exposes no startup event
            await asyncio.sleep(0.02)
        async with httpx.AsyncClient() as client:
            await client.post(f"http://127.0.0.1:{port}/write")
            received_at = time.monotonic()
        assert _finished, "commit had not finished when the client got the response"
        assert _finished[0] <= received_at
    finally:
        server.should_exit = True
        await serving
