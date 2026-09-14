"""S3 adapter contract test against a real S3-compatible server (MinIO).

Runs when VISIONROUTE_TEST_S3_ENDPOINT is set (CI starts a MinIO service;
locally: `minio server` + the variables below). It exercises the real wire
protocol: presigned POST with size/type conditions, presigned GET with forced
attachment disposition, HEAD, ranged GET and delete.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

from visionroute.domain.storage import StorageError
from visionroute.infrastructure.storage.s3 import S3ObjectStorage

ENDPOINT = os.environ.get("VISIONROUTE_TEST_S3_ENDPOINT")
BUCKET = os.environ.get("VISIONROUTE_TEST_S3_BUCKET", "visionroute-contract")

pytestmark = pytest.mark.skipif(
    ENDPOINT is None,
    reason="S3 uyumlu test sunucusu yapılandırılmadı (VISIONROUTE_TEST_S3_ENDPOINT)",
)


@pytest.fixture
async def storage() -> S3ObjectStorage:
    store = S3ObjectStorage(
        bucket=BUCKET,
        region="eu-central-1",
        endpoint_url=ENDPOINT,
        access_key_id=os.environ.get("VISIONROUTE_TEST_S3_ACCESS_KEY", "visionroute"),
        secret_access_key=os.environ.get("VISIONROUTE_TEST_S3_SECRET_KEY", "visionroute-dev-only"),
    )
    await store.ensure_bucket()
    return store


async def test_presigned_post_enforces_size_and_type(storage: S3ObjectStorage) -> None:
    key = f"orgs/{uuid.uuid4()}/evidence/{uuid.uuid4()}"
    body = b"\xff\xd8\xff" + b"0" * 997
    upload = await storage.presign_upload(
        key, ttl_seconds=120, content_type="image/jpeg", max_bytes=1000
    )
    async with httpx.AsyncClient() as http:
        too_big = await http.post(
            upload.url, data=upload.fields, files={"file": ("x.jpg", body + b"1", "image/jpeg")}
        )
        assert too_big.status_code in (400, 403)
        wrong_type = await http.post(
            upload.url,
            data={**upload.fields, "Content-Type": "text/html"},
            files={"file": ("x.html", body, "text/html")},
        )
        assert wrong_type.status_code in (400, 403)
        ok = await http.post(
            upload.url, data=upload.fields, files={"file": ("x.jpg", body, "image/jpeg")}
        )
        assert ok.status_code in (200, 201, 204), ok.text

    info = await storage.head(key)
    assert info is not None and info.size_bytes == 1000
    assert await storage.get_bytes(key, max_bytes=3) == b"\xff\xd8\xff"

    url = await storage.presign_download(
        key, ttl_seconds=60, filename="kanıt.jpg", content_type="image/jpeg"
    )
    async with httpx.AsyncClient() as http:
        downloaded = await http.get(url)
    assert downloaded.status_code == 200
    assert "attachment" in downloaded.headers["content-disposition"]
    assert downloaded.content == body

    await storage.delete(key)
    assert await storage.head(key) is None


async def test_bucket_is_not_publicly_readable(storage: S3ObjectStorage) -> None:
    key = f"orgs/{uuid.uuid4()}/evidence/{uuid.uuid4()}"
    await storage.put_bytes(key, b"\x89PNG\r\n\x1a\n", content_type="image/png")
    async with httpx.AsyncClient() as http:
        anonymous = await http.get(f"{ENDPOINT}/{BUCKET}/{key}")
    assert anonymous.status_code in (401, 403)
    await storage.delete(key)


async def test_invalid_keys_rejected(storage: S3ObjectStorage) -> None:
    with pytest.raises(StorageError):
        await storage.put_bytes("../escape", b"x", content_type="text/plain")
