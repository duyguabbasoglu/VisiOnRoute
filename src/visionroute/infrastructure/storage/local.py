"""Local filesystem object storage for development and tests.

Mirrors the S3 adapter's contract: objects are private files, and access is
only possible through short-lived URLs signed with HMAC-SHA256 that point at
the API's ``/api/v1/storage/local`` endpoints (mounted only for this backend).
Production-like environments refuse this backend at startup.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from visionroute.domain.storage import (
    ObjectInfo,
    PresignedUpload,
    StorageError,
    is_valid_object_key,
    safe_download_filename,
)

_META_SUFFIX = ".meta.json"


@dataclass(frozen=True, slots=True)
class LocalGrant:
    op: str  # "get" | "put"
    key: str
    content_type: str
    filename: str | None
    max_bytes: int | None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class LocalObjectStorage:
    def __init__(self, root: Path, *, signing_key: bytes, public_api_url: str) -> None:
        self._root = root
        self._key = signing_key
        self._api_url = public_api_url.rstrip("/")

    # ------------------------------------------------------------ files

    def _path(self, key: str) -> Path:
        if not is_valid_object_key(key):
            msg = "Geçersiz nesne anahtarı."
            raise StorageError(msg)
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            msg = "Geçersiz nesne anahtarı."
            raise StorageError(msg)
        return path

    def _write(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = path.with_suffix(path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        tmp.replace(path)
        Path(str(path) + _META_SUFFIX).write_text(json.dumps({"content_type": content_type}))

    async def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        await asyncio.to_thread(self._write, key, data, content_type)

    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes:
        path = self._path(key)

        def read() -> bytes:
            with path.open("rb") as handle:
                return handle.read(max_bytes if max_bytes is not None else -1)

        try:
            return await asyncio.to_thread(read)
        except FileNotFoundError as exc:
            msg = "Nesne bulunamadı."
            raise StorageError(msg) from exc

    async def head(self, key: str) -> ObjectInfo | None:
        path = self._path(key)
        if not path.is_file():
            return None
        meta_path = Path(str(path) + _META_SUFFIX)
        content_type = None
        if meta_path.is_file():
            content_type = json.loads(meta_path.read_text()).get("content_type")
        return ObjectInfo(key=key, size_bytes=path.stat().st_size, content_type=content_type)

    def file_path(self, key: str) -> Path:
        return self._path(key)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        for candidate in (path, Path(str(path) + _META_SUFFIX)):
            candidate.unlink(missing_ok=True)

    async def delete_prefix(self, prefix: str) -> int:
        directory = self._path(prefix.rstrip("/"))
        if not directory.is_dir():
            return 0
        count = sum(
            1 for p in directory.rglob("*") if p.is_file() and not p.name.endswith(_META_SUFFIX)
        )
        await asyncio.to_thread(shutil.rmtree, directory)
        return count

    # ------------------------------------------------------------ signed URLs

    def _sign(self, claims: dict[str, object]) -> str:
        payload = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
        signature = _b64(hmac.new(self._key, payload.encode(), hashlib.sha256).digest())
        return f"{payload}.{signature}"

    def verify(self, token: str, *, op: str) -> LocalGrant:
        try:
            payload, signature = token.split(".", 1)
        except ValueError as exc:
            raise StorageError("Geçersiz bağlantı.") from exc
        expected = _b64(hmac.new(self._key, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature):
            raise StorageError("Geçersiz bağlantı.")
        try:
            claims = json.loads(_unb64(payload))
        except (ValueError, json.JSONDecodeError) as exc:
            raise StorageError("Geçersiz bağlantı.") from exc
        if claims.get("op") != op or int(claims.get("exp", 0)) < int(time.time()):
            raise StorageError("Bağlantının süresi dolmuş veya geçersiz.")
        key = str(claims["key"])
        self._path(key)
        return LocalGrant(
            op=op,
            key=key,
            content_type=str(claims.get("ct") or "application/octet-stream"),
            filename=claims.get("fn") if isinstance(claims.get("fn"), str) else None,
            max_bytes=int(claims["max"]) if claims.get("max") is not None else None,
        )

    async def presign_download(
        self, key: str, *, ttl_seconds: int, filename: str, content_type: str
    ) -> str:
        self._path(key)
        token = self._sign(
            {
                "op": "get",
                "key": key,
                "exp": int(time.time()) + ttl_seconds,
                "fn": safe_download_filename(filename, "dosya"),
                "ct": content_type,
            }
        )
        return f"{self._api_url}/api/v1/storage/local/objects?token={quote(token)}"

    async def presign_upload(
        self, key: str, *, ttl_seconds: int, content_type: str, max_bytes: int
    ) -> PresignedUpload:
        self._path(key)
        token = self._sign(
            {
                "op": "put",
                "key": key,
                "exp": int(time.time()) + ttl_seconds,
                "ct": content_type,
                "max": max_bytes,
            }
        )
        return PresignedUpload(
            url=f"{self._api_url}/api/v1/storage/local/objects?token={quote(token)}",
            method="PUT",
            headers={"Content-Type": content_type},
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._root.mkdir, parents=True, exist_ok=True, mode=0o700)
