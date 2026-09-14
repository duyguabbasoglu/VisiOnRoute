"""Signed upload/download endpoints for the LOCAL storage backend only.

In production-like environments storage is S3 and browsers talk to S3
directly through presigned URLs; these endpoints then answer 404. Tokens are
HMAC-signed, short-lived, bound to one object key, operation, content type and
size; the request body limit is enforced here instead of the global middleware.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import FileResponse

from visionroute.api.errors import ApiError, NotFoundError
from visionroute.domain.storage import StorageError
from visionroute.infrastructure.storage.local import LocalObjectStorage

router = APIRouter(prefix="/storage/local", tags=["storage"], include_in_schema=False)

_INVALID = "Bağlantı geçersiz veya süresi dolmuş."


def _storage(request: Request) -> LocalObjectStorage:
    storage = getattr(request.app.state, "object_storage", None)
    if not isinstance(storage, LocalObjectStorage):
        raise NotFoundError
    return storage


@router.put("/objects", status_code=status.HTTP_204_NO_CONTENT)
async def upload_object(
    request: Request, token: Annotated[str, Query(max_length=2048)]
) -> Response:
    storage = _storage(request)
    try:
        grant = storage.verify(token, op="put")
    except StorageError as exc:
        raise ApiError(_INVALID, code="SIGNED_URL_INVALID", status_code=403) from exc
    if request.headers.get("content-type", "").split(";")[0].strip() != grant.content_type:
        raise ApiError("İçerik türü yükleme izniyle eşleşmiyor.", code="CONTENT_TYPE_MISMATCH")
    limit = grant.max_bytes or 0
    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > limit:
            raise ApiError(
                "Dosya izin verilen boyutu aşıyor.", code="PAYLOAD_TOO_LARGE", status_code=413
            )
        chunks.append(chunk)
    if received == 0:
        raise ApiError("Boş dosya yüklenemez.", code="EMPTY_UPLOAD")
    await storage.put_bytes(grant.key, b"".join(chunks), content_type=grant.content_type)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/objects")
async def download_object(
    request: Request, token: Annotated[str, Query(max_length=2048)]
) -> FileResponse:
    storage = _storage(request)
    try:
        grant = storage.verify(token, op="get")
    except StorageError as exc:
        raise ApiError(_INVALID, code="SIGNED_URL_INVALID", status_code=403) from exc
    path = storage.file_path(grant.key)
    if not os.path.isfile(path):
        raise NotFoundError("Dosya bulunamadı.")
    return FileResponse(
        path,
        media_type=grant.content_type,
        filename=grant.filename or "dosya",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
