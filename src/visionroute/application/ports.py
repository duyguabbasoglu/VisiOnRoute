"""Application ports: interfaces the application layer depends on.

Infrastructure adapters satisfy these protocols structurally; composition
roots (api / worker / scheduler / cli) choose the implementation from
settings. Value objects exchanged through ports live in ``visionroute.domain``
so adapters never import the application layer.
"""

from __future__ import annotations

from typing import Protocol

from visionroute.domain.ratelimit import RateLimitDecision


class RateLimiter(Protocol):
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision: ...

    async def close(self) -> None: ...


class FieldEncryptor(Protocol):
    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, value: str) -> str: ...
