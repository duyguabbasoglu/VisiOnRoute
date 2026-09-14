"""Object storage adapters (S3-compatible and local development storage)."""

from __future__ import annotations

import os

from visionroute.config.settings import Settings
from visionroute.infrastructure.storage.local import LocalObjectStorage
from visionroute.infrastructure.storage.s3 import S3ObjectStorage


def build_object_storage(settings: Settings) -> S3ObjectStorage | LocalObjectStorage:
    if settings.storage_backend == "s3":
        return S3ObjectStorage(
            bucket=settings.s3_bucket_evidence,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            public_endpoint_url=settings.s3_public_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=(
                settings.s3_secret_access_key.get_secret_value()
                if settings.s3_secret_access_key
                else None
            ),
        )
    signing_key = (
        settings.local_storage_signing_key.get_secret_value().encode()
        if settings.local_storage_signing_key
        else os.urandom(32)
    )
    return LocalObjectStorage(
        settings.local_storage_dir, signing_key=signing_key, public_api_url=settings.public_api_url
    )
