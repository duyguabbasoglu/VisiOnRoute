"""Public ingestion API (machine-to-machine, X-API-Key authenticated)."""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Request, UploadFile, status
from pydantic import BaseModel, Field

from visionroute.api.errors import ApiError, NotFoundError
from visionroute.api.ingest_deps import IngestAuth, IngestSession, ingest_context
from visionroute.application.ingestion.service import IngestionService
from visionroute.domain.ingestion import SCHEMA_VERSION

router = APIRouter(prefix="/ingest", tags=["ingest"])

_MAX_BATCH = 1000
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB decompression-bomb guard


class IngestOutcomeOut(BaseModel):
    event_id: str
    status: str
    rejection_reason: str | None = None
    detail: str | None = None


class IngestResult(BaseModel):
    schema_version: str
    accepted: int
    duplicates: int
    quarantined: int
    outcomes: list[IngestOutcomeOut]


class BatchIngestRequest(BaseModel):
    source_key: str = Field(min_length=1, max_length=120)
    events: list[dict[str, Any]] = Field(min_length=1, max_length=_MAX_BATCH)


async def _run(
    db: IngestSession,
    principal: IngestAuth,
    request: Request,
    source_key: str,
    events: list[dict[str, Any]],
) -> IngestResult:
    service = IngestionService(db)
    data_source = await service.get_source_by_key(principal.organization_id, source_key)
    if data_source is None:
        raise NotFoundError(
            "Veri kaynağı bulunamadı. Önce bir veri kaynağı tanımlayın.",
            code="DATA_SOURCE_NOT_FOUND",
        )
    if data_source.status != "active":
        raise ApiError(
            "Veri kaynağı etkin değil.",
            code="DATA_SOURCE_INACTIVE",
            status_code=status.HTTP_409_CONFLICT,
        )
    _ = ingest_context(principal, request)  # reserved for future audit sampling
    result = await service.ingest_batch(principal.organization_id, data_source, events)
    return IngestResult(
        schema_version=SCHEMA_VERSION,
        accepted=result.accepted,
        duplicates=result.duplicates,
        quarantined=result.quarantined,
        outcomes=[
            IngestOutcomeOut(
                event_id=o.event_id,
                status=o.status,
                rejection_reason=o.rejection_reason,
                detail=o.detail,
            )
            for o in result.outcomes
        ],
    )


@router.post("/events", response_model=IngestResult)
async def ingest_events(
    body: BatchIngestRequest,
    db: IngestSession,
    principal: IngestAuth,
    request: Request,
) -> IngestResult:
    """Sözleşmeye uygun olay(lar)ı alır. Idempotency: (kaynak, event_id) tekildir."""
    return await _run(db, principal, request, body.source_key, body.events)


@router.post("/import/csv", response_model=IngestResult)
async def ingest_csv(
    source_key: str,
    file: UploadFile,
    db: IngestSession,
    principal: IngestAuth,
    request: Request,
) -> IngestResult:
    """CSV toplu içe aktarma. Kolonlar canonical zarf alanlarıyla eşleşmelidir;
    telemetri alanları `payload.` ön ekiyle verilir (ör. `payload.latitude`)."""
    raw = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise ApiError(
            "Dosya boyutu sınırı aşıldı.",
            code="FILE_TOO_LARGE",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    events = _csv_to_envelopes(raw)
    if not events:
        raise ApiError("CSV içinde geçerli satır bulunamadı.", code="EMPTY_CSV")
    if len(events) > _MAX_BATCH:
        raise ApiError(
            f"CSV tek seferde en fazla {_MAX_BATCH} satır içerebilir.",
            code="BATCH_TOO_LARGE",
        )
    return await _run(db, principal, request, source_key, events)


def _csv_to_envelopes(raw: bytes) -> list[dict[str, Any]]:
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    envelopes: list[dict[str, Any]] = []
    for row in reader:
        envelope: dict[str, Any] = {"payload": {}}
        for key, value in row.items():
            if key is None or value is None or value == "":
                continue
            if key.startswith("payload."):
                envelope["payload"][key.removeprefix("payload.")] = _coerce(value)
            else:
                envelope[key] = value
        envelopes.append(envelope)
    return envelopes


def _coerce(value: str) -> Any:
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
