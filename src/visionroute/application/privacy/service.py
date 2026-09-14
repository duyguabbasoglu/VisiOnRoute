"""KVKK requests (API side): creation, listing, cancellation, export download,
and organization retention settings. Processing happens in the worker
(``application.privacy.processor``)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
from visionroute.application.saas.service import SubscriptionService
from visionroute.config.settings import Settings
from visionroute.domain.ids import uuid7
from visionroute.domain.privacy import (
    PrivacyRequestKind,
    PrivacyRequestStatus,
    PrivacySubjectType,
    RetentionPolicy,
    resolve_retention,
    validate_retention_overrides,
)
from visionroute.domain.storage import StorageError
from visionroute.infrastructure.db.models.fleet import Driver
from visionroute.infrastructure.db.models.identity import Membership, OrganizationSettings, User
from visionroute.infrastructure.db.models.privacy import PrivacyRequest


@dataclass(frozen=True)
class RetentionView:
    plan_days: int
    overrides: dict[str, int | None]
    effective: RetentionPolicy


class PrivacyService:
    def __init__(self, session: AsyncSession, storage: ObjectStorage, settings: Settings) -> None:
        self._db = session
        self._storage = storage
        self._settings = settings

    # ------------------------------------------------------------ requests

    async def create_request(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        *,
        kind: PrivacyRequestKind,
        subject_type: PrivacySubjectType,
        subject_id: uuid.UUID,
        reason: str | None,
    ) -> PrivacyRequest:
        await self._check_subject(ctx, tenant_id, kind, subject_type, subject_id)
        if kind is PrivacyRequestKind.ERASURE and not (reason and len(reason.strip()) >= 10):
            raise ValidationFailedError(
                [
                    "Silme talebi için gerekçe (en az 10 karakter) zorunludur; "
                    "denetim kaydına yazılır."
                ]
            )
        request = PrivacyRequest(
            id=uuid7(),
            organization_id=tenant_id,
            kind=kind.value,
            subject_type=subject_type.value,
            subject_id=subject_id,
            requested_by_user_id=ctx.user_id,
            reason=reason.strip() if reason else None,
            status=PrivacyRequestStatus.PENDING.value,
        )
        try:
            async with self._db.begin_nested():
                self._db.add(request)
                await self._db.flush()
        except IntegrityError as exc:
            raise DomainConflictError(
                "Bu kişi için aynı türde işlemde olan bir talep zaten var."
            ) from exc
        await record_audit(
            self._db,
            ctx,
            action=f"privacy.{kind.value}_requested",
            resource_type="privacy_request",
            resource_id=str(request.id),
            data={"subject_type": subject_type.value, "subject_id": str(subject_id)},
        )
        return request

    async def list_requests(
        self, tenant_id: uuid.UUID, *, subject_user_id: uuid.UUID | None = None, limit: int = 100
    ) -> list[PrivacyRequest]:
        stmt = select(PrivacyRequest).where(PrivacyRequest.organization_id == tenant_id)
        if subject_user_id is not None:
            stmt = stmt.where(
                PrivacyRequest.subject_type == PrivacySubjectType.USER.value,
                PrivacyRequest.subject_id == subject_user_id,
            )
        rows = await self._db.execute(stmt.order_by(PrivacyRequest.created_at.desc()).limit(limit))
        return list(rows.scalars())

    async def subject_names(self, requests: list[PrivacyRequest]) -> dict[uuid.UUID, str]:
        driver_ids = [r.subject_id for r in requests if r.subject_type == "driver"]
        user_ids = [r.subject_id for r in requests if r.subject_type == "user"]
        names: dict[uuid.UUID, str] = {}
        if driver_ids:
            for driver_id, name in await self._db.execute(
                select(Driver.id, Driver.full_name).where(Driver.id.in_(driver_ids))
            ):
                names[driver_id] = name
        if user_ids:
            for user_id, name in await self._db.execute(
                select(User.id, User.full_name).where(User.id.in_(user_ids))
            ):
                names[user_id] = name
        return names

    async def cancel(
        self, ctx: RequestContext, tenant_id: uuid.UUID, request_id: uuid.UUID
    ) -> PrivacyRequest:
        request = await self._load(tenant_id, request_id)
        if request.status != PrivacyRequestStatus.PENDING.value:
            raise DomainConflictError("Yalnızca sırada bekleyen talepler iptal edilebilir.")
        request.status = PrivacyRequestStatus.CANCELED.value
        request.completed_at = datetime.now(UTC)
        await record_audit(
            self._db,
            ctx,
            action="privacy.request_canceled",
            resource_type="privacy_request",
            resource_id=str(request.id),
        )
        return request

    async def export_download_url(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        request_id: uuid.UUID,
        *,
        subject_user_id: uuid.UUID | None = None,
    ) -> tuple[str, int]:
        request = await self._load(tenant_id, request_id)
        if subject_user_id is not None and (
            request.subject_type != PrivacySubjectType.USER.value
            or request.subject_id != subject_user_id
        ):
            raise DomainNotFoundError("Talep bulunamadı.")
        now = datetime.now(UTC)
        if (
            request.kind != PrivacyRequestKind.EXPORT.value
            or request.status != PrivacyRequestStatus.COMPLETED.value
            or request.artifact_key is None
            or request.artifact_expires_at is None
            or request.artifact_expires_at <= now
        ):
            raise DomainConflictError(
                "Bu talep için indirilebilir bir dosya yok veya süresi doldu."
            )
        ttl = self._settings.signed_url_ttl_seconds
        try:
            url = await self._storage.presign_download(
                request.artifact_key,
                ttl_seconds=ttl,
                filename=f"kvkk-veri-disa-aktarim-{request.created_at:%Y%m%d}.zip",
                content_type="application/zip",
            )
        except StorageError as exc:
            raise ServiceNotConfiguredError("Dosya deposu şu anda kullanılamıyor.") from exc
        await record_audit(
            self._db,
            ctx,
            action="privacy.export_downloaded",
            resource_type="privacy_request",
            resource_id=str(request.id),
            data={"ttl_seconds": ttl},
        )
        return url, ttl

    # ------------------------------------------------------------ retention

    async def get_retention(self, tenant_id: uuid.UUID) -> RetentionView:
        plan_days = (await SubscriptionService(self._db).get_entitlements(tenant_id)).retention_days
        org_settings = await self._db.get(OrganizationSettings, tenant_id)
        raw = dict(org_settings.retention) if org_settings else {}
        overrides: dict[str, int | None] = {
            key: value if isinstance(value, int) and not isinstance(value, bool) else None
            for key, value in raw.items()
            if key in ("telemetry_days", "evidence_media_days")
        }
        return RetentionView(
            plan_days=plan_days,
            overrides=overrides,
            effective=resolve_retention(plan_days, raw),
        )

    async def update_retention(
        self, ctx: RequestContext, tenant_id: uuid.UUID, values: dict[str, int | None]
    ) -> RetentionView:
        plan_days = (await SubscriptionService(self._db).get_entitlements(tenant_id)).retention_days
        problems = validate_retention_overrides(values, plan_days)
        if problems:
            raise ValidationFailedError(problems)
        org_settings = await self._db.get(OrganizationSettings, tenant_id)
        if org_settings is None:  # pragma: no cover - created with the organization
            raise DomainNotFoundError("Organizasyon ayarları bulunamadı.")
        merged = dict(org_settings.retention)
        for key, value in values.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        org_settings.retention = merged
        await record_audit(
            self._db,
            ctx,
            action="organization.retention_updated",
            resource_type="organization",
            resource_id=str(tenant_id),
            data={"retention": merged},
        )
        return await self.get_retention(tenant_id)

    # ------------------------------------------------------------ internals

    async def _check_subject(
        self,
        ctx: RequestContext,
        tenant_id: uuid.UUID,
        kind: PrivacyRequestKind,
        subject_type: PrivacySubjectType,
        subject_id: uuid.UUID,
    ) -> None:
        if subject_type is PrivacySubjectType.DRIVER:
            driver = await self._db.get(Driver, subject_id)
            if driver is None or driver.organization_id != tenant_id:
                raise DomainNotFoundError("Sürücü bulunamadı.")
            if kind is PrivacyRequestKind.ERASURE and driver.erased_at is not None:
                raise DomainConflictError("Bu sürücünün verileri zaten silinmiş.")
            return
        membership = (
            await self._db.execute(
                select(Membership).where(
                    Membership.organization_id == tenant_id, Membership.user_id == subject_id
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise DomainNotFoundError("Kullanıcı bu organizasyonun üyesi değil.")
        if kind is PrivacyRequestKind.ERASURE:
            if subject_id == ctx.user_id:
                raise DomainConflictError(
                    "Kendi hesabınızı silme talebi başka bir yönetici tarafından oluşturulmalıdır."
                )
            if membership.role_key == "owner":
                raise DomainConflictError(
                    "Organizasyon sahibinin verileri silinemez; önce sahipliği devredin."
                )

    async def _load(self, tenant_id: uuid.UUID, request_id: uuid.UUID) -> PrivacyRequest:
        request = await self._db.get(PrivacyRequest, request_id)
        if request is None or request.organization_id != tenant_id:
            raise DomainNotFoundError("Talep bulunamadı.")
        return request
