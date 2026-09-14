"""S3-compatible object storage (AWS S3 in production, MinIO locally).

- Buckets are private; objects are only reachable through short-lived
  presigned URLs issued after authorization in the application layer.
- Uploads use presigned POST with a content-length range and a fixed
  Content-Type condition, so clients cannot exceed limits or change the type.
- Downloads force ``Content-Disposition: attachment`` with a sanitized name.
- Presigning is a local computation; when the API reaches the store through
  an internal hostname (e.g. ``minio:9000`` in Compose), a separate public
  endpoint is used for URLs handed to browsers.
- Server-side encryption is enforced by the bucket's default encryption
  (SSE-KMS in Terraform), not per request, so MinIO and S3 behave the same.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from visionroute.domain.storage import (
    ObjectInfo,
    PresignedUpload,
    StorageError,
    is_valid_object_key,
    safe_download_filename,
)

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def _client(
    *,
    endpoint_url: str | None,
    region: str,
    access_key_id: str | None,
    secret_access_key: str | None,
) -> S3Client:
    client: S3Client = boto3.client(
        "s3",
        region_name=region,
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if endpoint_url else "auto"},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=30,
        ),
    )
    return client


class S3ObjectStorage:
    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None = None,
        public_endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._region = region
        credentials: dict[str, Any] = {
            "region": region,
            "access_key_id": access_key_id,
            "secret_access_key": secret_access_key,
        }
        self._client = _client(endpoint_url=endpoint_url, **credentials)
        self._presigner = (
            _client(endpoint_url=public_endpoint_url, **credentials)
            if public_endpoint_url
            else self._client
        )

    @staticmethod
    def _check_key(key: str) -> None:
        if not is_valid_object_key(key):
            msg = "Geçersiz nesne anahtarı."
            raise StorageError(msg)

    async def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        self._check_key(key)
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            msg = f"Nesne yazılamadı ({type(exc).__name__})."
            raise StorageError(msg) from exc

    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes:
        self._check_key(key)
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
        if max_bytes is not None:
            params["Range"] = f"bytes=0-{max_bytes - 1}"
        try:
            response = await asyncio.to_thread(self._client.get_object, **params)
            body: bytes = await asyncio.to_thread(response["Body"].read)
        except (BotoCoreError, ClientError) as exc:
            msg = f"Nesne okunamadı ({type(exc).__name__})."
            raise StorageError(msg) from exc
        return body

    async def head(self, key: str) -> ObjectInfo | None:
        self._check_key(key)
        try:
            response = await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            msg = f"Nesne bilgisi alınamadı ({type(exc).__name__})."
            raise StorageError(msg) from exc
        except BotoCoreError as exc:
            msg = f"Nesne bilgisi alınamadı ({type(exc).__name__})."
            raise StorageError(msg) from exc
        return ObjectInfo(
            key=key,
            size_bytes=int(response["ContentLength"]),
            content_type=response.get("ContentType"),
        )

    async def delete(self, key: str) -> None:
        self._check_key(key)
        try:
            await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            msg = f"Nesne silinemedi ({type(exc).__name__})."
            raise StorageError(msg) from exc

    async def delete_prefix(self, prefix: str) -> int:
        """Delete every object (all versions are left to bucket lifecycle rules)."""
        self._check_key(prefix.rstrip("/") or "x")
        deleted = 0
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            pages = await asyncio.to_thread(
                lambda: list(paginator.paginate(Bucket=self._bucket, Prefix=prefix))
            )
            for page in pages:
                keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if keys:
                    await asyncio.to_thread(
                        self._client.delete_objects,
                        Bucket=self._bucket,
                        Delete={"Objects": keys, "Quiet": True},  # type: ignore[typeddict-item]
                    )
                    deleted += len(keys)
        except (BotoCoreError, ClientError) as exc:
            msg = f"Nesneler silinemedi ({type(exc).__name__})."
            raise StorageError(msg) from exc
        return deleted

    async def presign_download(
        self, key: str, *, ttl_seconds: int, filename: str, content_type: str
    ) -> str:
        self._check_key(key)
        safe = safe_download_filename(filename, "dosya")
        try:
            url: str = self._presigner.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ResponseContentDisposition": f'attachment; filename="{safe}"',
                    "ResponseContentType": content_type,
                },
                ExpiresIn=ttl_seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            msg = f"İndirme bağlantısı üretilemedi ({type(exc).__name__})."
            raise StorageError(msg) from exc
        return url

    async def presign_upload(
        self, key: str, *, ttl_seconds: int, content_type: str, max_bytes: int
    ) -> PresignedUpload:
        self._check_key(key)
        try:
            post = self._presigner.generate_presigned_post(
                Bucket=self._bucket,
                Key=key,
                Fields={"Content-Type": content_type},
                Conditions=[
                    {"Content-Type": content_type},
                    ["content-length-range", 1, max_bytes],
                ],
                ExpiresIn=ttl_seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            msg = f"Yükleme bağlantısı üretilemedi ({type(exc).__name__})."
            raise StorageError(msg) from exc
        return PresignedUpload(
            url=post["url"],
            method="POST",
            fields={str(k): str(v) for k, v in post["fields"].items()},
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )

    async def ensure_bucket(self) -> None:
        """Create the bucket if missing (local MinIO convenience; production
        buckets are provisioned by Terraform with public access blocked)."""
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)
        except ClientError:
            try:
                if self._region == "us-east-1":
                    await asyncio.to_thread(self._client.create_bucket, Bucket=self._bucket)
                else:
                    await asyncio.to_thread(
                        self._client.create_bucket,
                        Bucket=self._bucket,
                        CreateBucketConfiguration={
                            "LocationConstraint": self._region,  # type: ignore[typeddict-item]
                        },
                    )
            except (BotoCoreError, ClientError) as exc:
                msg = f"Bucket oluşturulamadı ({type(exc).__name__})."
                raise StorageError(msg) from exc
