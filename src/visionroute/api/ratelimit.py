"""Rate limit enforcement helpers for route handlers.

Identities (IP addresses, e-mail addresses, API client ids) are hashed before
they become limiter keys so no personal data is written to Redis.
"""

from __future__ import annotations

import hashlib

from fastapi import Request

from visionroute.api.errors import RateLimitedError
from visionroute.application.ports import RateLimiter


def client_identity(request: Request) -> str:
    """Peer address as seen by the app. Behind the ALB uvicorn runs with
    ``--proxy-headers`` so this is the real client, not the load balancer."""
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(
    request: Request,
    *,
    scope: str,
    identity: str,
    limit: int,
    window_seconds: int,
) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    digest = hashlib.sha256(identity.strip().lower().encode()).hexdigest()[:32]
    decision = await limiter.hit(f"{scope}:{digest}", limit=limit, window_seconds=window_seconds)
    if not decision.allowed:
        raise RateLimitedError(headers={"Retry-After": str(decision.retry_after_seconds)})
