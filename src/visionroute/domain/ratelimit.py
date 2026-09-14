"""Sliding-window rate limiting arithmetic (framework-free).

Counts are kept per fixed window, but a decision weighs the previous window by
the share of it that still overlaps the sliding interval:

    estimate = current + previous * (1 - elapsed_in_current / window)

A plain fixed window lets a client send ``2 * limit`` requests around a window
boundary (limit at the end of one window, limit again at the start of the
next); the weighted estimate closes that burst while needing only two counters
per key.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


def window_index(now_seconds: float, window_seconds: int) -> int:
    return int(now_seconds // window_seconds)


def sliding_estimate(
    current: int, previous: int, *, now_seconds: float, window_seconds: int
) -> float:
    elapsed = (now_seconds % window_seconds) / window_seconds
    return current + previous * (1.0 - elapsed)


def decide(
    estimate: float, *, limit: int, now_seconds: float, window_seconds: int
) -> RateLimitDecision:
    """Decision for a weighted hit count that includes the current request."""
    retry_after = window_seconds - int(now_seconds) % window_seconds
    return RateLimitDecision(
        allowed=estimate <= limit,
        remaining=max(0, int(limit - estimate)),
        retry_after_seconds=max(1, retry_after),
    )
