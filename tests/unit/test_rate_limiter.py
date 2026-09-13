"""Rate limiter behaviour (in-memory adapter, pure window arithmetic)."""

from __future__ import annotations

from visionroute.config.settings import Environment, Settings
from visionroute.domain.ratelimit import decide
from visionroute.infrastructure.ratelimit import InMemoryRateLimiter


class FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


async def test_allows_until_limit_then_blocks_with_retry_after() -> None:
    clock = FakeClock(1_000_020.0)
    limiter = InMemoryRateLimiter(clock=clock)
    decisions = [await limiter.hit("login:abc", limit=3, window_seconds=60) for _ in range(4)]
    assert [d.allowed for d in decisions] == [True, True, True, False]
    assert decisions[-1].remaining == 0
    assert 1 <= decisions[-1].retry_after_seconds <= 60


async def test_window_rolls_over_and_keys_are_independent() -> None:
    clock = FakeClock(1_000_000.0)
    limiter = InMemoryRateLimiter(clock=clock)
    for _ in range(2):
        await limiter.hit("a", limit=2, window_seconds=60)
    assert (await limiter.hit("a", limit=2, window_seconds=60)).allowed is False
    assert (await limiter.hit("b", limit=2, window_seconds=60)).allowed is True

    clock.now += 60
    assert (await limiter.hit("a", limit=2, window_seconds=60)).allowed is True


def test_decide_never_reports_zero_retry_after() -> None:
    decision = decide(5, limit=1, now_seconds=120.0, window_seconds=60)
    assert decision.allowed is False
    assert decision.retry_after_seconds >= 1


def test_production_requires_redis_limiter() -> None:
    settings = Settings(_env_file=None, environment=Environment.PRODUCTION)  # type: ignore[call-arg]
    assert any("hız sınırlama" in p for p in settings.validate_for_runtime())
