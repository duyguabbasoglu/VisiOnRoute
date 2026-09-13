"""Fixed-window rate limiting arithmetic (framework-free)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


def window_index(now_seconds: float, window_seconds: int) -> int:
    return int(now_seconds // window_seconds)


def decide(count: int, *, limit: int, now_seconds: float, window_seconds: int) -> RateLimitDecision:
    """Decision after ``count`` hits (including the current one) in the window."""
    retry_after = window_seconds - int(now_seconds) % window_seconds
    return RateLimitDecision(
        allowed=count <= limit,
        remaining=max(0, limit - count),
        retry_after_seconds=max(1, retry_after),
    )
