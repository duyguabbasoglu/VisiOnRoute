"""Live update fan-out over PostgreSQL LISTEN/NOTIFY.

Writers call :func:`notify_live` inside their transaction; PostgreSQL delivers
the notification only when that transaction commits, so subscribers never see
changes that were rolled back. Every API replica keeps one listening
connection and fans notifications out to the server-sent-event streams of the
matching tenant. Payloads carry only the organization id and a change kind —
clients re-read data through RLS-protected queries.

Delivery is best effort: a dropped listener connection reconnects with backoff
and streams fall back to periodic refreshes, so a missed notification delays
an update by at most one refresh interval.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections import defaultdict
from typing import Any

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.observability.logging import get_logger

logger = get_logger("visionroute.realtime")

LIVE_CHANNEL = "visionroute_live"
LIVE_KINDS = frozenset({"positions", "safety_event"})
_QUEUE_SIZE = 64


async def notify_live(session: AsyncSession, organization_id: uuid.UUID, kind: str) -> None:
    if kind not in LIVE_KINDS:
        msg = f"unknown live kind: {kind}"
        raise ValueError(msg)
    payload = json.dumps({"o": str(organization_id), "k": kind})
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"), {"channel": LIVE_CHANNEL, "payload": payload}
    )


class LiveEventHub:
    def __init__(self, database_url: str) -> None:
        self._dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self._subscribers: dict[uuid.UUID, set[asyncio.Queue[str]]] = defaultdict(set)
        self._task: asyncio.Task[None] | None = None
        self._closing = False
        self.connected = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="live-event-hub")

    async def close(self) -> None:
        self._closing = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def subscribe(self, organization_id: uuid.UUID) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_SIZE)
        self._subscribers[organization_id].add(queue)
        return queue

    def unsubscribe(self, organization_id: uuid.UUID, queue: asyncio.Queue[str]) -> None:
        queues = self._subscribers.get(organization_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            self._subscribers.pop(organization_id, None)

    def subscriber_count(self) -> int:
        return sum(len(queues) for queues in self._subscribers.values())

    async def _run(self) -> None:
        backoff = 1.0
        while not self._closing:
            connection: Any = None
            try:
                connection = await asyncpg.connect(self._dsn)
                lost = asyncio.Event()
                connection.add_termination_listener(lambda _connection, lost=lost: lost.set())
                await connection.add_listener(LIVE_CHANNEL, self._on_notification)
                self.connected.set()
                backoff = 1.0
                logger.info("live_hub_listening")
                # Until the server drops the connection; close() cancels the task.
                await lost.wait()
                logger.warning("live_hub_connection_lost")
            except asyncio.CancelledError:
                raise
            except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as exc:
                logger.warning("live_hub_connection_failed", error_type=type(exc).__name__)
            finally:
                self.connected.clear()
                if connection is not None and not connection.is_closed():
                    with contextlib.suppress(Exception):
                        await connection.close()
            if not self._closing:
                await asyncio.sleep(backoff)
                backoff = min(30.0, backoff * 2)

    def _on_notification(self, _connection: object, _pid: int, _channel: str, payload: str) -> None:
        try:
            message = json.loads(payload)
            organization_id = uuid.UUID(str(message["o"]))
            kind = str(message["k"])
        except (ValueError, KeyError, TypeError):
            return
        if kind not in LIVE_KINDS:
            return
        for queue in list(self._subscribers.get(organization_id, ())):
            with contextlib.suppress(asyncio.QueueFull):
                # A slow consumer only misses coalesced updates; it re-reads state.
                queue.put_nowait(kind)
