"""Application ports: interfaces the application layer depends on.

Infrastructure adapters satisfy these protocols structurally; composition
roots (api / worker / scheduler / cli) choose the implementation from
settings. Value objects exchanged through ports live in ``visionroute.domain``
so adapters never import the application layer.
"""

from __future__ import annotations

from typing import Protocol

from visionroute.domain.mail import OutgoingEmail
from visionroute.domain.ratelimit import RateLimitDecision
from visionroute.domain.storage import ObjectInfo, PresignedUpload


class RateLimiter(Protocol):
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision: ...

    async def close(self) -> None: ...


class FieldEncryptor(Protocol):
    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, value: str) -> str: ...


class ObjectStorage(Protocol):
    """Private object storage. Access for end users happens only through
    short-lived presigned URLs issued after authorization."""

    async def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None: ...

    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes: ...

    async def head(self, key: str) -> ObjectInfo | None: ...

    async def delete(self, key: str) -> None: ...

    async def delete_prefix(self, prefix: str) -> int: ...

    async def presign_download(
        self, key: str, *, ttl_seconds: int, filename: str, content_type: str
    ) -> str: ...

    async def presign_upload(
        self, key: str, *, ttl_seconds: int, content_type: str, max_bytes: int
    ) -> PresignedUpload: ...

    async def ensure_bucket(self) -> None: ...


class MailSender(Protocol):
    async def send(self, email: OutgoingEmail) -> str:
        """Deliver ``email``; return a provider reference. Raises
        ``visionroute.domain.mail.MailDeliveryError`` on failure."""
        ...
