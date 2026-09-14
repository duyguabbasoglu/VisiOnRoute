"""KVKK request processing and retention purge (worker / scheduler side).

Requests are claimed with FOR UPDATE SKIP LOCKED and a lease (like the mail
outbox), processed in their own transaction, and retried with backoff; an
expired lease makes a request claimable again if a worker dies mid-job.

The processor runs with the RLS bypass (it spans organizations and account
tables), so every tenant query below filters ``organization_id`` explicitly.
Logs carry request ids and counts only — never names, e-mails or locations.
"""

from __future__ import annotations

import csv
import io
import json
import secrets
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.mail.service import MailService
from visionroute.application.ports import FieldEncryptor, ObjectStorage
from visionroute.application.saas.service import SubscriptionService
from visionroute.domain.privacy import (
    EXPORT_AVAILABLE_FOR,
    EXPORT_TELEMETRY_ROW_LIMIT,
    MAX_ATTEMPTS,
    PROCESSING_LEASE,
    driver_pseudonym,
    resolve_retention,
    retry_delay,
    user_pseudonym,
)
from visionroute.domain.storage import StorageError, export_object_key
from visionroute.infrastructure.db.models.coaching import CoachingAction
from visionroute.infrastructure.db.models.fleet import Driver, DriverAssignment, Vehicle
from visionroute.infrastructure.db.models.identity import (
    Invitation,
    Membership,
    MfaChallenge,
    MfaRecoveryCode,
    Organization,
    OrganizationSettings,
    Session,
    User,
    UserToken,
)
from visionroute.infrastructure.db.models.mail import EmailMessage
from visionroute.infrastructure.db.models.privacy import PrivacyRequest
from visionroute.infrastructure.db.models.safety import EventEvidence, SafetyEvent
from visionroute.infrastructure.db.models.system import AuditLog
from visionroute.infrastructure.db.models.telemetry import TelemetryPoint, Trip
from visionroute.infrastructure.db.tenancy import set_rls_bypass
from visionroute.infrastructure.security.passwords import hash_password
from visionroute.observability.logging import get_logger

logger = get_logger("visionroute.privacy")

EXPORT_MEDIA_BYTES_LIMIT = 100 * 1024 * 1024
EMAIL_LOG_RETENTION = timedelta(days=90)
_TELEMETRY_PURGE_BATCH = 5000
_TELEMETRY_PURGE_MAX_BATCHES = 40
_EVIDENCE_PURGE_BATCH = 500
_MEDIA_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "video/mp4": "mp4"}

_README = """VISiOnRoute - Kişisel veri dışa aktarma (KVKK md. 11)

Bu arşiv, talep tarihinde ilgili organizasyonda sizinle ilişkilendirilmiş kişisel
verileri makine tarafından okunabilir biçimde (JSON/CSV) içerir.

- manifest.json: dosyaların listesi, kayıt sayıları ve kısaltılan bölümler.
- Zaman damgaları UTC'dir (ISO 8601).
- Konum/telemetri kayıtları organizasyonun saklama süresiyle sınırlıdır.
- Kanıt medyası, boyut sınırı aşılmadıkça media/ klasörüne eklenmiştir.

Sorularınız için veri sorumlusu olan organizasyonla iletişime geçin.
"""


class _PermanentFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class _Export:
    files: dict[str, Any]
    counts: dict[str, int]
    truncated: list[str]


class PrivacyProcessor:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
        cipher: FieldEncryptor | None,
    ) -> None:
        self._factory = factory
        self._storage = storage
        self._cipher = cipher

    # ------------------------------------------------------------ requests

    async def process_due(self, *, limit: int = 5, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        handled = 0
        for request_id in await self._claim(limit, now):
            await self._process(request_id, now)
            handled += 1
        return handled

    async def _claim(self, limit: int, now: datetime) -> list[uuid.UUID]:
        async with self._factory() as session:
            await set_rls_bypass(session)
            rows = await session.execute(
                select(PrivacyRequest)
                .where(
                    PrivacyRequest.status.in_(("pending", "processing")),
                    PrivacyRequest.next_attempt_at <= now,
                )
                .order_by(PrivacyRequest.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            claimed: list[uuid.UUID] = []
            for request in rows.scalars():
                request.status = "processing"
                request.attempts += 1
                request.next_attempt_at = now + PROCESSING_LEASE
                claimed.append(request.id)
            await session.commit()
        return claimed

    async def _process(self, request_id: uuid.UUID, now: datetime) -> None:
        artifact_key: str | None = None
        try:
            async with self._factory() as session:
                await set_rls_bypass(session)
                request = await session.get(PrivacyRequest, request_id)
                if request is None or request.status != "processing":
                    return
                if request.kind == "export":
                    artifact_key = export_object_key(request.organization_id, request.id)
                    counts = await self._export(session, request, artifact_key, now)
                else:
                    counts = await self._erase(session, request, now)
                request.status = "completed"
                request.result = dict(counts)
                request.error_code = None
                request.completed_at = now
                await record_audit(
                    session,
                    _system_context(request.organization_id),
                    action=f"privacy.{request.kind}_completed",
                    resource_type="privacy_request",
                    resource_id=str(request.id),
                    data=dict(counts),
                )
                await session.commit()
            logger.info("privacy_request_completed", request_id=str(request_id))
        except Exception as exc:
            if artifact_key is not None:
                try:
                    await self._storage.delete(artifact_key)
                except StorageError:
                    logger.warning("privacy_artifact_cleanup_failed", request_id=str(request_id))
            await self._record_failure(request_id, exc, now)

    async def _record_failure(self, request_id: uuid.UUID, exc: Exception, now: datetime) -> None:
        permanent = isinstance(exc, _PermanentFailure)
        code = exc.code if isinstance(exc, _PermanentFailure) else type(exc).__name__[:60]
        async with self._factory() as session:
            await set_rls_bypass(session)
            request = await session.get(PrivacyRequest, request_id)
            if request is None:
                return
            request.error_code = code
            if permanent or request.attempts >= MAX_ATTEMPTS:
                request.status = "failed"
                request.completed_at = now
                await record_audit(
                    session,
                    _system_context(request.organization_id),
                    action=f"privacy.{request.kind}_failed",
                    resource_type="privacy_request",
                    resource_id=str(request.id),
                    data={"error_code": code},
                )
            else:
                request.status = "pending"
                request.next_attempt_at = now + retry_delay(request.attempts)
            await session.commit()
        logger.warning(
            "privacy_request_failed",
            request_id=str(request_id),
            error_code=code,
            permanent=permanent,
        )

    # ------------------------------------------------------------ export

    async def _export(
        self, session: AsyncSession, request: PrivacyRequest, key: str, now: datetime
    ) -> dict[str, int]:
        org_id = request.organization_id
        if request.subject_type == "driver":
            export = await self._collect_driver(session, org_id, request.subject_id)
        else:
            export = await self._collect_user(session, org_id, request.subject_id)

        media_total = 0
        buffer = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)  # noqa: SIM115
        try:
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("BENIOKU.txt", _README)
                for name, content in export.files.items():
                    if name.endswith(".csv"):
                        archive.writestr(name, content)
                    else:
                        archive.writestr(
                            name, json.dumps(content, ensure_ascii=False, indent=2, default=str)
                        )
                if request.subject_type == "driver":
                    media_total = await self._add_media(
                        session, archive, org_id, request.subject_id, export
                    )
                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "generated_at": now.isoformat(),
                            "organization_id": str(org_id),
                            "request_id": str(request.id),
                            "subject_type": request.subject_type,
                            "counts": export.counts,
                            "truncated_sections": export.truncated,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
            buffer.seek(0)
            data = buffer.read()
        finally:
            buffer.close()

        await self._storage.put_bytes(key, data, content_type="application/zip")
        request.artifact_key = key
        request.artifact_size_bytes = len(data)
        request.artifact_expires_at = now + EXPORT_AVAILABLE_FOR
        if request.subject_type == "user":
            await self._notify_export_ready(session, request)
        return {**export.counts, "media_bytes": media_total, "archive_bytes": len(data)}

    async def _collect_driver(
        self, session: AsyncSession, org_id: uuid.UUID, driver_id: uuid.UUID
    ) -> _Export:
        driver = await session.get(Driver, driver_id)
        if driver is None or driver.organization_id != org_id:
            raise _PermanentFailure("SUBJECT_NOT_FOUND")
        license_number: str | None = None
        if driver.license_number_enc:
            license_number = (
                self._cipher.decrypt(driver.license_number_enc)
                if self._cipher is not None
                else "(şifreli; anahtar yapılandırılmamış)"
            )
        files: dict[str, Any] = {
            "surucu.json": {
                "id": str(driver.id),
                "external_id": driver.external_id,
                "full_name": driver.full_name,
                "phone": driver.phone,
                "license_number": license_number,
                "status": driver.status,
                "created_at": driver.created_at,
                "erased_at": driver.erased_at,
            }
        }
        assignments = await session.execute(
            select(DriverAssignment, Vehicle.external_id)
            .join(Vehicle, Vehicle.id == DriverAssignment.vehicle_id)
            .where(
                DriverAssignment.organization_id == org_id, DriverAssignment.driver_id == driver_id
            )
            .order_by(DriverAssignment.started_at)
        )
        files["arac_atamalari.json"] = [
            {"vehicle": plate, "started_at": a.started_at, "ended_at": a.ended_at}
            for a, plate in assignments
        ]
        trips = await session.execute(
            select(Trip)
            .where(Trip.organization_id == org_id, Trip.driver_id == driver_id)
            .order_by(Trip.started_at)
        )
        files["seferler.json"] = [
            {
                "id": str(t.id),
                "vehicle_id": str(t.vehicle_id),
                "status": t.status,
                "started_at": t.started_at,
                "ended_at": t.ended_at,
                "distance_km": t.distance_km,
                "max_speed_kph": t.max_speed_kph,
            }
            for t in trips.scalars()
        ]
        events = await session.execute(
            select(SafetyEvent)
            .where(SafetyEvent.organization_id == org_id, SafetyEvent.driver_id == driver_id)
            .order_by(SafetyEvent.occurred_at)
        )
        files["guvenlik_olaylari.json"] = [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "severity": e.severity,
                "occurred_at": e.occurred_at,
                "latitude": e.latitude,
                "longitude": e.longitude,
                "reason": e.reason_tr,
                "review_status": e.review_status,
                "resolution": e.resolution,
                "reviewer_notes": e.reviewer_notes,
            }
            for e in events.scalars()
        ]
        coaching = await session.execute(
            select(CoachingAction)
            .where(CoachingAction.organization_id == org_id, CoachingAction.driver_id == driver_id)
            .order_by(CoachingAction.created_at)
        )
        files["kocluk.json"] = [_coaching_row(c) for c in coaching.scalars()]

        rows = await session.execute(
            select(TelemetryPoint)
            .where(TelemetryPoint.organization_id == org_id, TelemetryPoint.driver_id == driver_id)
            .order_by(TelemetryPoint.occurred_at)
            .limit(EXPORT_TELEMETRY_ROW_LIMIT + 1)
        )
        points = list(rows.scalars())
        truncated: list[str] = []
        if len(points) > EXPORT_TELEMETRY_ROW_LIMIT:
            points = points[:EXPORT_TELEMETRY_ROW_LIMIT]
            truncated.append("telemetri.csv")
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            ["occurred_at", "vehicle_id", "latitude", "longitude", "speed_kph", "heading_deg"]
        )
        for p in points:
            writer.writerow(
                [
                    p.occurred_at.isoformat(),
                    p.vehicle_id,
                    p.latitude,
                    p.longitude,
                    p.speed_kph,
                    p.heading_deg,
                ]
            )
        files["telemetri.csv"] = out.getvalue()

        counts = {
            "assignments": len(files["arac_atamalari.json"]),
            "trips": len(files["seferler.json"]),
            "safety_events": len(files["guvenlik_olaylari.json"]),
            "coaching_actions": len(files["kocluk.json"]),
            "telemetry_points": len(points),
        }
        return _Export(files=files, counts=counts, truncated=truncated)

    async def _add_media(
        self,
        session: AsyncSession,
        archive: zipfile.ZipFile,
        org_id: uuid.UUID,
        driver_id: uuid.UUID,
        export: _Export,
    ) -> int:
        rows = await session.execute(
            select(EventEvidence)
            .join(SafetyEvent, SafetyEvent.id == EventEvidence.safety_event_id)
            .where(
                EventEvidence.organization_id == org_id,
                SafetyEvent.driver_id == driver_id,
                EventEvidence.status == "available",
                EventEvidence.storage_key.is_not(None),
            )
            .order_by(EventEvidence.created_at)
        )
        total = 0
        included = 0
        for evidence in rows.scalars():
            size = evidence.size_bytes or 0
            if total + size > EXPORT_MEDIA_BYTES_LIMIT:
                if "media/" not in export.truncated:
                    export.truncated.append("media/")
                continue
            data = await self._storage.get_bytes(evidence.storage_key or "")
            extension = _MEDIA_EXTENSIONS.get(evidence.content_type or "", "bin")
            archive.writestr(f"media/{evidence.safety_event_id}-{evidence.id}.{extension}", data)
            total += len(data)
            included += 1
        export.counts["media_files"] = included
        return total

    async def _collect_user(
        self, session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> _Export:
        user = await session.get(User, user_id)
        membership = (
            await session.execute(
                select(Membership).where(
                    Membership.organization_id == org_id, Membership.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if user is None or membership is None:
            raise _PermanentFailure("SUBJECT_NOT_FOUND")
        files: dict[str, Any] = {
            "hesap.json": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "locale": user.locale,
                "status": user.status,
                "created_at": user.created_at,
                "email_verified_at": user.email_verified_at,
                "mfa_enabled": user.mfa_enabled_at is not None,
                "password_changed_at": user.password_changed_at,
                "membership": {
                    "role": membership.role_key,
                    "status": membership.status,
                    "joined_at": membership.created_at,
                },
            }
        }
        sessions = await session.execute(
            select(Session)
            .where(Session.user_id == user_id, Session.organization_id == org_id)
            .order_by(Session.created_at)
        )
        files["oturumlar.json"] = [
            {
                "created_at": s.created_at,
                "last_used_at": s.last_used_at,
                "revoked_at": s.revoked_at,
                "ip_address": str(s.ip_address) if s.ip_address else None,
                "user_agent": s.user_agent,
            }
            for s in sessions.scalars()
        ]
        audit = await session.execute(
            select(AuditLog)
            .where(AuditLog.organization_id == org_id, AuditLog.actor_user_id == user_id)
            .order_by(AuditLog.created_at)
        )
        files["islem_kayitlari.json"] = [
            {
                "action": a.action,
                "resource_type": a.resource_type,
                "created_at": a.created_at,
                "ip_address": str(a.ip_address) if a.ip_address else None,
            }
            for a in audit.scalars()
        ]
        coaching = await session.execute(
            select(CoachingAction)
            .where(
                CoachingAction.organization_id == org_id,
                (CoachingAction.assignee_user_id == user_id)
                | (CoachingAction.created_by_user_id == user_id),
            )
            .order_by(CoachingAction.created_at)
        )
        files["kocluk_gorevleri.json"] = [_coaching_row(c) for c in coaching.scalars()]
        reviews = await session.execute(
            select(SafetyEvent.id, SafetyEvent.reviewed_at, SafetyEvent.review_status)
            .where(SafetyEvent.organization_id == org_id, SafetyEvent.reviewer_user_id == user_id)
            .order_by(SafetyEvent.reviewed_at)
        )
        files["olay_incelemeleri.json"] = [
            {"safety_event_id": str(i), "reviewed_at": at, "decision": decision}
            for i, at, decision in reviews
        ]
        emails = await session.execute(
            select(EmailMessage)
            .where(
                EmailMessage.organization_id == org_id,
                func.lower(EmailMessage.recipient) == user.email.lower(),
            )
            .order_by(EmailMessage.created_at)
        )
        files["e_postalar.json"] = [
            {
                "template": m.template,
                "subject": m.subject,
                "status": m.status,
                "created_at": m.created_at,
                "sent_at": m.sent_at,
            }
            for m in emails.scalars()
        ]
        counts = {
            "sessions": len(files["oturumlar.json"]),
            "audit_entries": len(files["islem_kayitlari.json"]),
            "coaching_actions": len(files["kocluk_gorevleri.json"]),
            "reviews": len(files["olay_incelemeleri.json"]),
            "emails": len(files["e_postalar.json"]),
        }
        return _Export(files=files, counts=counts, truncated=[])

    async def _notify_export_ready(self, session: AsyncSession, request: PrivacyRequest) -> None:
        user = await session.get(User, request.subject_id)
        organization = await session.get(Organization, request.organization_id)
        if user is None or organization is None or request.artifact_expires_at is None:
            return
        await MailService(session, self._cipher).enqueue(
            template="privacy_export_ready",
            recipient=user.email,
            context={
                "full_name": user.full_name,
                "organization_name": organization.name,
                "expires_at": request.artifact_expires_at.isoformat(),
            },
            organization_id=request.organization_id,
            related=("privacy_request", str(request.id)),
            idempotency_key=f"privacy-export-ready:{request.id}",
        )

    # ------------------------------------------------------------ erasure

    async def _erase(
        self, session: AsyncSession, request: PrivacyRequest, now: datetime
    ) -> dict[str, int]:
        if request.subject_type == "driver":
            return await self._erase_driver(
                session, request.organization_id, request.subject_id, now
            )
        return await self._erase_user(session, request.organization_id, request.subject_id, now)

    async def _erase_driver(
        self, session: AsyncSession, org_id: uuid.UUID, driver_id: uuid.UUID, now: datetime
    ) -> dict[str, int]:
        driver = await session.get(Driver, driver_id)
        if driver is None or driver.organization_id != org_id:
            raise _PermanentFailure("SUBJECT_NOT_FOUND")
        driver.full_name, driver.external_id = driver_pseudonym(driver.id)
        driver.phone = None
        driver.license_number_enc = None
        driver.user_id = None
        driver.status = "erased"
        driver.erased_at = now

        telemetry = await session.execute(
            delete(TelemetryPoint).where(
                TelemetryPoint.organization_id == org_id, TelemetryPoint.driver_id == driver_id
            )
        )
        trips = await session.execute(
            update(Trip)
            .where(Trip.organization_id == org_id, Trip.driver_id == driver_id)
            .values(last_latitude=None, last_longitude=None)
        )
        media_removed = 0
        evidence_rows = await session.execute(
            select(EventEvidence)
            .join(SafetyEvent, SafetyEvent.id == EventEvidence.safety_event_id)
            .where(EventEvidence.organization_id == org_id, SafetyEvent.driver_id == driver_id)
        )
        for evidence in evidence_rows.scalars():
            if evidence.storage_key is not None:
                await self._storage.delete(evidence.storage_key)
                media_removed += 1
            evidence.storage_key = None
            evidence.telemetry_window = None
            evidence.status = "deleted"
            evidence.deleted_at = now
        events = await session.execute(
            update(SafetyEvent)
            .where(SafetyEvent.organization_id == org_id, SafetyEvent.driver_id == driver_id)
            .values(latitude=None, longitude=None, reviewer_notes=None)
        )
        coaching = await session.execute(
            update(CoachingAction)
            .where(CoachingAction.organization_id == org_id, CoachingAction.driver_id == driver_id)
            .values(description=None, notes=None, outcome_notes=None)
        )
        return {
            "telemetry_points_deleted": _rowcount(telemetry),
            "trips_pseudonymized": _rowcount(trips),
            "safety_events_pseudonymized": _rowcount(events),
            "evidence_media_deleted": media_removed,
            "coaching_actions_redacted": _rowcount(coaching),
        }

    async def _erase_user(
        self, session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, now: datetime
    ) -> dict[str, int]:
        user = await session.get(User, user_id)
        membership = (
            await session.execute(
                select(Membership).where(
                    Membership.organization_id == org_id, Membership.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if user is None:
            raise _PermanentFailure("SUBJECT_NOT_FOUND")
        if membership is not None and membership.role_key == "owner":
            raise _PermanentFailure("OWNER_CANNOT_BE_ERASED")
        email = user.email.lower()
        if membership is not None:
            await session.delete(membership)
        unassigned = await session.execute(
            update(CoachingAction)
            .where(
                CoachingAction.organization_id == org_id,
                CoachingAction.assignee_user_id == user_id,
                CoachingAction.status.in_(("open", "in_progress")),
            )
            .values(assignee_user_id=None)
        )
        await session.execute(
            update(Driver)
            .where(Driver.organization_id == org_id, Driver.user_id == user_id)
            .values(user_id=None)
        )
        emails = await session.execute(
            delete(EmailMessage).where(
                EmailMessage.organization_id == org_id,
                func.lower(EmailMessage.recipient) == email,
                EmailMessage.status != "sending",
            )
        )
        invitations = await session.execute(
            delete(Invitation).where(
                Invitation.organization_id == org_id, func.lower(Invitation.email) == email
            )
        )
        await session.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        user.sessions_revoked_at = now
        await session.flush()

        other_memberships = (
            await session.execute(
                select(func.count()).select_from(Membership).where(Membership.user_id == user_id)
            )
        ).scalar_one()
        account_erased = other_memberships == 0 and user.platform_role is None
        if account_erased:
            user.full_name, user.email = user_pseudonym(user.id)
            # Unusable credential: a hash of a random value nobody knows.
            user.password_hash = hash_password(secrets.token_urlsafe(48))
            user.status = "erased"
            user.email_verified_at = None
            user.mfa_totp_secret_enc = None
            user.mfa_pending_secret_enc = None
            user.mfa_enabled_at = None
            user.mfa_last_used_step = None
            for model in (UserToken, MfaRecoveryCode, MfaChallenge):
                await session.execute(delete(model).where(model.user_id == user_id))
            await session.execute(delete(Session).where(Session.user_id == user_id))
        return {
            "membership_removed": int(membership is not None),
            "account_erased": int(account_erased),
            "account_retained_for_other_organizations": int(not account_erased),
            "coaching_actions_unassigned": _rowcount(unassigned),
            "emails_deleted": _rowcount(emails),
            "invitations_deleted": _rowcount(invitations),
        }

    # ------------------------------------------------------------ retention

    async def purge_expired(
        self,
        *,
        now: datetime | None = None,
        organization_ids: list[uuid.UUID] | None = None,
    ) -> dict[str, int]:
        now = now or datetime.now(UTC)
        stats = {
            "telemetry_points": 0,
            "evidence_media": 0,
            "export_artifacts": 0,
            "emails": 0,
            "expired_tokens": 0,
        }
        async with self._factory() as session:
            await set_rls_bypass(session)
            stmt = select(Organization.id)
            if organization_ids is not None:
                stmt = stmt.where(Organization.id.in_(organization_ids))
            org_ids = list((await session.execute(stmt)).scalars())

        for org_id in org_ids:
            telemetry, media = await self._purge_organization(org_id, now)
            stats["telemetry_points"] += telemetry
            stats["evidence_media"] += media

        async with self._factory() as session:
            await set_rls_bypass(session)
            expired = await session.execute(
                select(PrivacyRequest).where(
                    PrivacyRequest.artifact_key.is_not(None),
                    PrivacyRequest.artifact_expires_at <= now,
                )
            )
            for request in expired.scalars():
                await self._storage.delete(request.artifact_key or "")
                request.artifact_key = None
                stats["export_artifacts"] += 1
            if organization_ids is None:
                emails = await session.execute(
                    delete(EmailMessage).where(
                        EmailMessage.status.in_(("sent", "dead_letter", "canceled")),
                        EmailMessage.created_at < now - EMAIL_LOG_RETENTION,
                    )
                )
                stats["emails"] = _rowcount(emails)
                token_cutoff = now - timedelta(days=7)
                for model in (UserToken, MfaChallenge):
                    result = await session.execute(
                        delete(model).where(model.expires_at < token_cutoff)
                    )
                    stats["expired_tokens"] += _rowcount(result)
            await session.commit()
        if any(stats.values()):
            logger.info("retention_purge", **stats)
        return stats

    async def _purge_organization(self, org_id: uuid.UUID, now: datetime) -> tuple[int, int]:
        async with self._factory() as session:
            await set_rls_bypass(session)
            plan_days = (await SubscriptionService(session).get_entitlements(org_id)).retention_days
            org_settings = await session.get(OrganizationSettings, org_id)
            policy = resolve_retention(
                plan_days, dict(org_settings.retention) if org_settings else {}
            )

            telemetry_cutoff = now - timedelta(days=policy.telemetry_days)
            telemetry = 0
            for _ in range(_TELEMETRY_PURGE_MAX_BATCHES):
                batch = (
                    select(TelemetryPoint.id, TelemetryPoint.occurred_at)
                    .where(
                        TelemetryPoint.organization_id == org_id,
                        TelemetryPoint.occurred_at < telemetry_cutoff,
                    )
                    .limit(_TELEMETRY_PURGE_BATCH)
                )
                result = await session.execute(
                    delete(TelemetryPoint).where(
                        tuple_(TelemetryPoint.id, TelemetryPoint.occurred_at).in_(batch)
                    )
                )
                deleted = _rowcount(result)
                telemetry += deleted
                await session.commit()
                await set_rls_bypass(session)
                if deleted < _TELEMETRY_PURGE_BATCH:
                    break

            media_cutoff = now - timedelta(days=policy.evidence_media_days)
            rows = await session.execute(
                select(EventEvidence)
                .where(
                    EventEvidence.organization_id == org_id,
                    EventEvidence.status.in_(("available", "rejected", "pending_upload")),
                    EventEvidence.kind.in_(("snapshot", "clip")),
                    EventEvidence.created_at < media_cutoff,
                )
                .limit(_EVIDENCE_PURGE_BATCH)
            )
            media = 0
            for evidence in rows.scalars():
                if evidence.storage_key is not None:
                    await self._storage.delete(evidence.storage_key)
                evidence.storage_key = None
                evidence.status = "deleted"
                evidence.deleted_at = now
                media += 1
            if media:
                await record_audit(
                    session,
                    _system_context(org_id),
                    action="retention.evidence_media_purged",
                    resource_type="organization",
                    resource_id=str(org_id),
                    data={"count": media, "retention_days": policy.evidence_media_days},
                )
            await session.commit()
        return telemetry, media


def _system_context(organization_id: uuid.UUID) -> RequestContext:
    return RequestContext(
        user_id=None,
        organization_id=organization_id,
        role=None,
        is_platform_admin=False,
        actor_label="system:privacy",
    )


def _coaching_row(action: CoachingAction) -> dict[str, object]:
    return {
        "id": str(action.id),
        "title": action.title,
        "description": action.description,
        "status": action.status,
        "due_at": action.due_at,
        "notes": action.notes,
        "outcome": action.outcome,
        "outcome_notes": action.outcome_notes,
        "created_at": action.created_at,
        "completed_at": action.completed_at,
    }


def _rowcount(result: object) -> int:
    return int(getattr(result, "rowcount", 0) or 0)
