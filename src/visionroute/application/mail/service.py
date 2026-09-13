"""Enqueue transactional e-mail into the ``email_messages`` outbox.

E-mail is written in the same database transaction as the business change
that triggers it (an invitation, a reset request) and delivered later by the
worker, so a slow or failing SMTP server never breaks the business
transaction and a rolled-back transaction never sends mail.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.errors import ServiceNotConfiguredError
from visionroute.application.mail.templates import TEMPLATES, render_subject
from visionroute.application.ports import FieldEncryptor
from visionroute.domain.ids import uuid7
from visionroute.infrastructure.db.models.mail import EmailMessage


class MailService:
    def __init__(self, session: AsyncSession, cipher: FieldEncryptor | None) -> None:
        self._db = session
        self._cipher = cipher

    async def enqueue(
        self,
        *,
        template: str,
        recipient: str,
        context: dict[str, str],
        secret_context: dict[str, str] | None = None,
        organization_id: uuid.UUID | None = None,
        related: tuple[str, str] | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 8,
    ) -> uuid.UUID | None:
        """Queue a message. Returns its id, or None when ``idempotency_key``
        was already used (duplicate request)."""
        if template not in TEMPLATES:
            msg = f"Bilinmeyen e-posta şablonu: {template}"
            raise ValueError(msg)
        secret_context_enc: str | None = None
        if secret_context:
            if self._cipher is None:
                raise ServiceNotConfiguredError(
                    "E-posta bağlantısı oluşturulamadı: alan şifreleme anahtarı yapılandırılmamış."
                )
            secret_context_enc = self._cipher.encrypt(json.dumps(secret_context))
        stmt = (
            pg_insert(EmailMessage)
            .values(
                id=uuid7(),
                organization_id=organization_id,
                recipient=recipient,
                template=template,
                subject=render_subject(template, context),
                context=context,
                secret_context_enc=secret_context_enc,
                related_type=related[0] if related else None,
                related_id=related[1] if related else None,
                max_attempts=max_attempts,
                idempotency_key=idempotency_key,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(EmailMessage.id)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()
