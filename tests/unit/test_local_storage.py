"""Local storage adapter: signed URL integrity, expiry, key safety."""

from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from visionroute.domain.storage import (
    StorageError,
    evidence_object_key,
    is_valid_object_key,
    safe_download_filename,
    sniff_media_type,
)
from visionroute.infrastructure.storage.local import LocalObjectStorage


def _storage(tmp_path: Path, key: bytes = b"k" * 32) -> LocalObjectStorage:
    return LocalObjectStorage(tmp_path, signing_key=key, public_api_url="http://api.test")


def _token(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


async def test_roundtrip_and_head(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    await storage.put_bytes("orgs/a/evidence/1", b"\xff\xd8\xffdata", content_type="image/jpeg")
    info = await storage.head("orgs/a/evidence/1")
    assert info is not None and info.size_bytes == 7 and info.content_type == "image/jpeg"
    assert await storage.get_bytes("orgs/a/evidence/1", max_bytes=3) == b"\xff\xd8\xff"
    await storage.delete("orgs/a/evidence/1")
    assert await storage.head("orgs/a/evidence/1") is None


async def test_signed_download_is_bound_and_expires(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    url = await storage.presign_download(
        "orgs/a/evidence/1", ttl_seconds=60, filename="../../ç kanıt.jpg", content_type="image/jpeg"
    )
    grant = storage.verify(_token(url), op="get")
    assert grant.key == "orgs/a/evidence/1"
    assert grant.filename is not None and "/" not in grant.filename

    with pytest.raises(StorageError):
        storage.verify(_token(url), op="put")  # operation is bound
    with pytest.raises(StorageError):
        _storage(tmp_path, key=b"x" * 32).verify(_token(url), op="get")  # other key
    token = _token(url)
    payload, signature = token.split(".")
    with pytest.raises(StorageError):
        storage.verify(payload[:-2] + "AA." + signature, op="get")  # tampered

    expired = await storage.presign_download(
        "orgs/a/evidence/1", ttl_seconds=-1, filename="x.jpg", content_type="image/jpeg"
    )
    with pytest.raises(StorageError):
        storage.verify(_token(expired), op="get")


async def test_path_traversal_keys_rejected(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    for key in ("../etc/passwd", "orgs/../../x", "/abs/path", ""):
        with pytest.raises(StorageError):
            await storage.put_bytes(key, b"x", content_type="text/plain")


def test_media_sniffing_and_key_helpers() -> None:
    assert sniff_media_type(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert sniff_media_type(b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert sniff_media_type(b"\x00\x00\x00\x18ftypmp42") == "video/mp4"
    assert sniff_media_type(b"<html>") is None
    key = evidence_object_key(uuid.uuid4(), uuid.uuid4())
    assert is_valid_object_key(key)
    assert safe_download_filename("Şoför görüntüsü (1).jpg", "x") == "Sofor-goruntusu-1-.jpg"
    assert "/" not in safe_download_filename("a/b/../c.png", "x")
