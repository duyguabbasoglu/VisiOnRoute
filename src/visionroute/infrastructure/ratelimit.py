"""Rate limiter adapters.

- ``RedisRateLimiter`` — production: shared counters across API replicas
  (Redis is reserved for cache and rate limiting, ADR-0002).
- ``InMemoryRateLimiter`` — local development and tests only; counters are
  per process, which is why production-like environments refuse it.

Keys are expected to be pre-hashed by the caller (no raw e-mail addresses or
IPs in Redis). On a Redis outage the limiter fails open and logs: account
lockout and authentication remain in force, and a cache outage must not take
login down with it.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError

from visionroute.config.settings import Settings
from visionroute.domain.ratelimit import RateLimitDecision, decide, window_index
from visionroute.observability.logging import get_logger

logger = get_logger(__name__)

_MAX_TRACKED_KEYS = 50_000


class InMemoryRateLimiter:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._counters: dict[tuple[str, int], int] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        now = self._clock()
        index = window_index(now, window_seconds)
        async with self._lock:
            if len(self._counters) > _MAX_TRACKED_KEYS:
                self._counters = {k: v for k, v in self._counters.items() if k[1] >= index}
            count = self._counters.get((key, index), 0) + 1
            self._counters[(key, index)] = count
        return decide(count, limit=limit, now_seconds=now, window_seconds=window_seconds)

    async def close(self) -> None:
        return None


class RedisRateLimiter:
    def __init__(self, redis: Redis, clock: Callable[[], float] = time.time) -> None:
        self._redis = redis
        self._clock = clock

    @classmethod
    def from_url(cls, url: str) -> RedisRateLimiter:
        return cls(Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5))

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        now = self._clock()
        redis_key = f"vr:rl:{key}:{window_index(now, window_seconds)}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(redis_key)
                pipe.expire(redis_key, window_seconds + 1, nx=True)
                count, _ = await pipe.execute()
        except (RedisError, OSError) as exc:
            logger.warning("rate_limiter_unavailable", error_type=type(exc).__name__)
            return RateLimitDecision(allowed=True, remaining=limit, retry_after_seconds=0)
        return decide(int(count), limit=limit, now_seconds=now, window_seconds=window_seconds)

    async def close(self) -> None:
        await self._redis.aclose()


def build_rate_limiter(settings: Settings) -> InMemoryRateLimiter | RedisRateLimiter:
    if settings.rate_limit_backend == "redis":
        return RedisRateLimiter.from_url(settings.redis_url)
    return InMemoryRateLimiter()
