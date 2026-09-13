"""Deliver queued e-mail (worker side).

Delivery is at-least-once:
1. claim due messages with FOR UPDATE SKIP LOCKED, mark them ``sending`` with a
   lease, commit (no row locks are held during network I/O);
2. render and send outside any transaction;
3. record the outcome in a short transaction.

A worker that crashes mid-send leaves the message ``sending``; once the lease
expires another worker retries it. Retries reuse the same Message-ID so
receivers can de-duplicate. Decrypted one-time secrets are wiped once the
message is sent or dead-lettered; ``last_error`` never contains message bodies.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from visionroute.application.mail.templates import TemplateRenderError, render
from visionroute.application.ports import FieldEncryptor, MailSender
from visionroute.config.settings import Settings
from visionroute.domain.mail import MailDeliveryError, OutgoingEmail
from visionroute.infrastructure.db.models.mail import EmailMessage
from visionroute.infrastructure.db.tenancy import set_rls_bypass
from visionroute.infrastructure.security.crypto import FieldEncryptionError
from visionroute.observability.logging import get_logger

logger = get_logger(__name__)

SENDING_LEASE = timedelta(minutes=5)
_MAX_BACKOFF_SECONDS = 3600


@dataclass
class DeliveryStats:
    sent: int = 0
    retried: int = 0
    dead_lettered: int = 0
    message_ids: list[uuid.UUID] = field(default_factory=list)

    @property
    def handled(self) -> int:
        return self.sent + self.retried + self.dead_lettered


@dataclass(frozen=True, slots=True)
class _Claimed:
    id: uuid.UUID
    recipient: str
    template: str
    context: dict[str, str]
    secret_context_enc: str | None
    attempts: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class _Outcome:
    status: str  # sent | retry | dead_letter
    error: str | None = None


def backoff_for(attempts: int) -> timedelta:
    return timedelta(seconds=min(60 * 2 ** max(attempts - 1, 0), _MAX_BACKOFF_SECONDS))


class MailDeliveryService:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        sender: MailSender,
        cipher: FieldEncryptor | None,
        settings: Settings,
    ) -> None:
        self._factory = factory
        self._sender = sender
        self._cipher = cipher
        self._settings = settings

    async def deliver_due(self, *, limit: int = 20, now: datetime | None = None) -> DeliveryStats:
        stats = DeliveryStats()
        for claimed in await self._claim(limit, now or datetime.now(UTC)):
            outcome = await self._attempt(claimed)
            await self._record(claimed, outcome)
            stats.message_ids.append(claimed.id)
            if outcome.status == "sent":
                stats.sent += 1
            elif outcome.status == "retry":
                stats.retried += 1
            else:
                stats.dead_lettered += 1
        return stats

    async def _claim(self, limit: int, now: datetime) -> list[_Claimed]:
        async with self._factory() as session:
            await set_rls_bypass(session)
            rows = await session.execute(
                select(EmailMessage)
                .where(
                    or_(
                        and_(EmailMessage.status == "pending", EmailMessage.next_attempt_at <= now),
                        # Lease expired: the previous worker died mid-send.
                        and_(EmailMessage.status == "sending", EmailMessage.next_attempt_at <= now),
                    )
                )
                .order_by(EmailMessage.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            claimed: list[_Claimed] = []
            for message in rows.scalars():
                message.status = "sending"
                message.attempts += 1
                message.next_attempt_at = now + SENDING_LEASE
                claimed.append(
                    _Claimed(
                        id=message.id,
                        recipient=message.recipient,
                        template=message.template,
                        context={str(k): str(v) for k, v in message.context.items()},
                        secret_context_enc=message.secret_context_enc,
                        attempts=message.attempts,
                        max_attempts=message.max_attempts,
                    )
                )
            await session.commit()
        return claimed

    async def _attempt(self, claimed: _Claimed) -> _Outcome:
        try:
            secret_context = self._decrypt(claimed.secret_context_enc)
        except FieldEncryptionError as exc:
            # Missing/rotated key is an operator-fixable configuration problem.
            return self._retry_or_dead(claimed, f"Şifre çözme başarısız: {exc}")
        try:
            rendered = render(
                claimed.template,
                claimed.context,
                secret_context,
                app_url=self._settings.public_app_url,
            )
        except TemplateRenderError as exc:
            return _Outcome("dead_letter", f"Şablon hatası: {exc}")

        email = OutgoingEmail(
            message_id=f"<{claimed.id}@visionroute>",
            from_address=self._settings.smtp_from,
            from_name=self._settings.mail_from_name,
            to_address=claimed.recipient,
            subject=rendered.subject,
            text_body=rendered.text,
            html_body=rendered.html,
        )
        try:
            await self._sender.send(email)
        except MailDeliveryError as exc:
            logger.warning(
                "email_delivery_failed",
                email_message_id=str(claimed.id),
                template=claimed.template,
                attempts=claimed.attempts,
                permanent=exc.permanent,
            )
            if exc.permanent:
                return _Outcome("dead_letter", exc.reason[:1000])
            return self._retry_or_dead(claimed, exc.reason)
        logger.info("email_sent", email_message_id=str(claimed.id), template=claimed.template)
        return _Outcome("sent")

    def _decrypt(self, value: str | None) -> dict[str, str]:
        if value is None:
            return {}
        if self._cipher is None:
            msg = "Alan şifreleme anahtarı yapılandırılmamış."
            raise FieldEncryptionError(msg)
        loaded = json.loads(self._cipher.decrypt(value))
        return {str(k): str(v) for k, v in loaded.items()}

    @staticmethod
    def _retry_or_dead(claimed: _Claimed, error: str) -> _Outcome:
        if claimed.attempts >= claimed.max_attempts:
            return _Outcome("dead_letter", error[:1000])
        return _Outcome("retry", error[:1000])

    async def _record(self, claimed: _Claimed, outcome: _Outcome) -> None:
        now = datetime.now(UTC)
        async with self._factory() as session:
            await set_rls_bypass(session)
            message = await session.get(EmailMessage, claimed.id, with_for_update=True)
            if message is None or message.status != "sending":
                return  # canceled or already handled elsewhere
            if outcome.status == "sent":
                message.status = "sent"
                message.sent_at = now
                message.last_error = None
                message.provider_message_id = f"<{claimed.id}@visionroute>"
                message.secret_context_enc = None
            elif outcome.status == "retry":
                message.status = "pending"
                message.last_error = outcome.error
                message.next_attempt_at = now + backoff_for(claimed.attempts)
            else:
                message.status = "dead_letter"
                message.last_error = outcome.error
                message.secret_context_enc = None
            await session.commit()
