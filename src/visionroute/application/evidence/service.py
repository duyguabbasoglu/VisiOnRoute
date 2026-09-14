"""Evidence media: upload, verification, signed access, deletion.

Flow: request an upload slot (authorization, type/size limits, opaque key) →
client uploads directly to object storage with a short-lived presigned URL →
complete (the object is inspected: size and magic bytes must match; otherwise
it is deleted and the evidence rejected) → authorized users request a
short-lived download URL; every access is audit-logged without the URL.

Automatic anonymization (face/plate blurring) is NOT implemented: it requires
an external computer-vision service and a product/legal decision on
thresholds. Media is marked ``redaction_status="not_processed"`` and raw
access is limited to ``events.evidence.raw_media``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.errors import (
    DomainConflictError,
    DomainNotFoundError,
    ServiceNotConfiguredError,
    ValidationFailedError,
)
from visionroute.application.ports import ObjectStorage
from visionroute.config.settings import Settings
from visionroute.domain.ids import uuid7
from visionroute.domain.storage import (
    EVIDENCE_MEDIA_TYPES,
    PresignedUpload,
    StorageError,
    evidence_object_key,
    safe_download_filename,
    sniff_media_type,
)
from visionroute.infrastructure.db.models.safety import EventEvidence, SafetyEvent

_SNIFF_BYTES = 16


@dataclass(frozen=True)
class UploadSlot:
    evidence: EventEvidence
    upload: PresignedUpload
    max_bytes: int


class EvidenceService:
    def __init__(self, session: AsyncSession, storage: ObjectStorage, settings: Settings) -> None:
        self._db = session
        self._storage = storage
        self._settings = settings

    async def create_upload(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        safety_event_id: uuid.UUID,
        *,
        content_type: str,
        size_bytes: int,
        filename: str | None,
        api_client_id: uuid.UUID | None = None,
    ) -> UploadSlot:
        kind = EVIDENCE_MEDIA_TYPES.get(content_type)
        if kind is None:
            raise ValidationFailedError(
                ["Desteklenmeyen dosya türü. İzin verilenler: JPEG, PNG görüntü ve MP4 video."]
            )
        max_bytes = self._settings.evidence_max_bytes
        if size_bytes <= 0 or size_bytes > max_bytes:
            raise ValidationFailedError(
                [f"Dosya boyutu 1 bayt ile {max_bytes // (1024 * 1024)} MB arasında olmalıdır."]
            )
        event = await self._db.get(SafetyEvent, safety_event_id)
        if event is None or event.organization_id != tenant_id:
            raise DomainNotFoundError("Güvenlik olayı bulunamadı.")

        evidence_id = uuid7()
        evidence = EventEvidence(
            id=evidence_id,
            organization_id=tenant_id,
            safety_event_id=safety_event_id,
            kind=kind,
            storage_key=evidence_object_key(tenant_id, evidence_id),
            content_type=content_type,
            size_bytes=size_bytes,
            original_filename=safe_download_filename(filename, kind) if filename else None,
            captured_at=datetime.now(UTC),
            status="pending_upload",
            redaction_status="not_processed",
            uploaded_by_user_id=ctx.user_id,
            uploaded_by_api_client_id=api_client_id,
        )
        self._db.add(evidence)
        await self._db.flush()
        try:
            upload = await self._storage.presign_upload(
                evidence.storage_key or "",
                ttl_seconds=self._settings.evidence_upload_ttl_seconds,
                content_type=content_type,
                max_bytes=size_bytes,
            )
        except StorageError as exc:
            raise ServiceNotConfiguredError("Kanıt depolama şu anda kullanılamıyor.") from exc
        await record_audit(
            self._db,
            ctx,
            action="evidence.upload_started",
            resource_type="event_evidence",
            resource_id=str(evidence.id),
            data={"safety_event_id": str(safety_event_id), "content_type": content_type},
        )
        return UploadSlot(evidence=evidence, upload=upload, max_bytes=size_bytes)

    async def complete_upload(
        self, ctx: RequestContext, tenant_id: uuid.UUID, evidence_id: uuid.UUID
    ) -> EventEvidence:
        evidence = await self._load(tenant_id, evidence_id)
        if evidence.status == "available":
            return evidence  # idempotent
        if evidence.status != "pending_upload" or evidence.storage_key is None:
            raise DomainConflictError("Bu kanıt için yükleme tamamlanamaz.")
        try:
            info = await self._storage.head(evidence.storage_key)
        except StorageError as exc:
            raise ServiceNotConfiguredError("Kanıt depolama şu anda kullanılamıyor.") from exc
        if info is None:
            raise DomainConflictError("Dosya henüz yüklenmemiş.")

        problem: str | None = None
        if (
            info.size_bytes != evidence.size_bytes
            or info.size_bytes > self._settings.evidence_max_bytes
        ):
            problem = "Yüklenen dosyanın boyutu bildirilen boyutla eşleşmiyor."
        else:
            head = await self._storage.get_bytes(evidence.storage_key, max_bytes=_SNIFF_BYTES)
            if sniff_media_type(head) != evidence.content_type:
                problem = "Dosya içeriği bildirilen dosya türüyle eşleşmiyor."
        if problem is not None:
            await self._storage.delete(evidence.storage_key)
            evidence.status = "rejected"
            await record_audit(
                self._db,
                ctx,
                action="evidence.upload_rejected",
                resource_type="event_evidence",
                resource_id=str(evidence.id),
                data={"reason": problem},
            )
            # The rejection must persist even though the request fails.
            await self._db.commit()
            raise ValidationFailedError([problem])

        evidence.status = "available"
        await record_audit(
            self._db,
            ctx,
            action="evidence.uploaded",
            resource_type="event_evidence",
            resource_id=str(evidence.id),
            data={"size_bytes": info.size_bytes},
        )
        return evidence

    async def access_url(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        safety_event_id: uuid.UUID,
        evidence_id: uuid.UUID,
    ) -> tuple[str, int]:
        evidence = await self._load(tenant_id, evidence_id)
        if evidence.safety_event_id != safety_event_id:
            raise DomainNotFoundError("Kanıt bulunamadı.")
        if evidence.status != "available" or evidence.storage_key is None:
            raise DomainConflictError("Bu kanıt dosyası erişilebilir durumda değil.")
        ttl = self._settings.signed_url_ttl_seconds
        extension = {"image/jpeg": "jpg", "image/png": "png", "video/mp4": "mp4"}.get(
            evidence.content_type or "", "bin"
        )
        try:
            url = await self._storage.presign_download(
                evidence.storage_key,
                ttl_seconds=ttl,
                filename=f"kanit-{evidence.id}.{extension}",
                content_type=evidence.content_type or "application/octet-stream",
            )
        except StorageError as exc:
            raise ServiceNotConfiguredError("Kanıt depolama şu anda kullanılamıyor.") from exc
        await record_audit(
            self._db,
            ctx,
            action="evidence.media_accessed",
            resource_type="event_evidence",
            resource_id=str(evidence.id),
            data={"safety_event_id": str(safety_event_id), "ttl_seconds": ttl},
        )
        return url, ttl

    async def delete(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        safety_event_id: uuid.UUID,
        evidence_id: uuid.UUID,
        *,
        reason: str = "manual",
    ) -> EventEvidence:
        evidence = await self._load(tenant_id, evidence_id)
        if evidence.safety_event_id != safety_event_id:
            raise DomainNotFoundError("Kanıt bulunamadı.")
        if evidence.kind == "telemetry_window":
            raise DomainConflictError("Telemetri kanıtı silinemez; olay kaydının parçasıdır.")
        await self.remove_media(evidence)
        await record_audit(
            self._db,
            ctx,
            action="evidence.deleted",
            resource_type="event_evidence",
            resource_id=str(evidence.id),
            data={"reason": reason},
        )
        return evidence

    async def remove_media(self, evidence: EventEvidence) -> None:
        """Delete the stored object and mark the row deleted (idempotent)."""
        if evidence.storage_key is not None:
            try:
                await self._storage.delete(evidence.storage_key)
            except StorageError as exc:
                raise ServiceNotConfiguredError("Kanıt depolama şu anda kullanılamıyor.") from exc
        evidence.status = "deleted"
        evidence.deleted_at = datetime.now(UTC)
        evidence.storage_key = None

    async def _load(self, tenant_id: uuid.UUID, evidence_id: uuid.UUID) -> EventEvidence:
        evidence = await self._db.get(EventEvidence, evidence_id)
        if evidence is None or evidence.organization_id != tenant_id:
            raise DomainNotFoundError("Kanıt bulunamadı.")
        return evidence
