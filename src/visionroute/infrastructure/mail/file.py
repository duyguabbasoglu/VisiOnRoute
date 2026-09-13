"""Local development mail adapter: writes each message as an ``.eml`` file.

Only for ``local``/``development`` environments (production-like startup
rejects it). Files are created with owner-only permissions because they
contain one-time links. Open them with any mail client, or grep for the link.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from visionroute.domain.mail import MailDeliveryError, OutgoingEmail
from visionroute.infrastructure.mail.mime import build_mime

_UNSAFE = re.compile(r"[^A-Za-z0-9-]")


class FileMailSender:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    async def send(self, email: OutgoingEmail) -> str:
        data = build_mime(email).as_bytes()
        stem = _UNSAFE.sub("", email.message_id)[:64]
        path = self._directory / f"{datetime.now(UTC):%Y%m%dT%H%M%S%f}-{stem}.eml"
        try:
            await asyncio.to_thread(self._write, path, data)
        except OSError as exc:
            msg = f"E-posta dosyası yazılamadı ({type(exc).__name__})."
            raise MailDeliveryError(msg, permanent=False) from exc
        return str(path)

    def _write(self, path: Path, data: bytes) -> None:
        self._directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
