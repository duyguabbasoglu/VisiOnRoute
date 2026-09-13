"""E-mail outbox: secret handling, idempotency, retries, leases, tenant isolation."""

from __future__ import annotations

import json
import uuid
from typing import Any

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.helpers import (
    auth_headers,
    create_org_and_login,
    deliver_mail,
    last_email_to,
    token_from,
)
from visionroute.application.mail.delivery import MailDeliveryService
from visionroute.application.mail.service import MailService
from visionroute.config.settings import Settings
from visionroute.domain.mail import MailDeliveryError, OutgoingEmail
from visionroute.infrastructure.db.engine import build_engine, build_session_factory
from visionroute.infrastructure.db.tenancy import set_rls_bypass
from visionroute.infrastructure.mail.memory import MemoryMailSender
from visionroute.infrastructure.security.crypto import FieldCipher, build_field_cipher

_RESET_CONTEXT = {"full_name": "Çağrı Işık", "ttl_minutes": "30"}


class _FailingSender:
    def __init__(self, *, permanent: bool) -> None:
        self.permanent = permanent
        self.calls = 0

    async def send(self, email: OutgoingEmail) -> str:
        self.calls += 1
        raise MailDeliveryError("SMTP sunucusu isteği reddetti (421).", permanent=self.permanent)


async def _enqueue(settings: Settings, **kwargs: Any) -> uuid.UUID | None:
    engine = build_engine(settings)
    try:
        async with build_session_factory(engine)() as session:
            await set_rls_bypass(session)
            message_id = await MailService(session, build_field_cipher(settings)).enqueue(**kwargs)
            await session.commit()
            return message_id
    finally:
        await engine.dispose()


async def _sql(settings: Settings, statement: str, **params: Any) -> list[Any]:
    engine = build_engine(settings)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.rls_bypass', 'on', true)"))
            result = await conn.execute(text(statement), params)
            return list(result.mappings().all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _row(settings: Settings, message_id: uuid.UUID) -> dict[str, Any]:
    rows = await _sql(settings, "SELECT * FROM email_messages WHERE id = :id", id=message_id)
    return dict(rows[0])


async def _run(settings: Settings, sender: Any, cipher: Any = None) -> None:
    engine = build_engine(settings)
    try:
        service = MailDeliveryService(
            build_session_factory(engine),
            sender,
            cipher if cipher is not None else build_field_cipher(settings),
            settings,
        )
        await service.deliver_due(limit=50)
    finally:
        await engine.dispose()


async def _make_due(settings: Settings, message_id: uuid.UUID) -> None:
    await _sql(
        settings,
        "UPDATE email_messages SET next_attempt_at = now() - interval '1 second' WHERE id = :id",
        id=message_id,
    )


async def test_secret_encrypted_until_sent_then_wiped(test_settings: Settings) -> None:
    await deliver_mail(test_settings)
    message_id = await _enqueue(
        test_settings,
        template="password_reset",
        recipient="sir@outbox.example",
        context=_RESET_CONTEXT,
        secret_context={"token": "vra_gizli-token-degeri-123456"},
    )
    assert message_id is not None
    queued = await _row(test_settings, message_id)
    assert queued["status"] == "pending"
    assert queued["secret_context_enc"].startswith("enc1:test-k1:")
    assert "gizli-token" not in json.dumps(queued["context"])
    assert "gizli-token" not in queued["subject"]

    await deliver_mail(test_settings)
    sent = await _row(test_settings, message_id)
    assert sent["status"] == "sent"
    assert sent["secret_context_enc"] is None
    assert sent["sent_at"] is not None
    delivered = last_email_to("sir@outbox.example")
    assert token_from(delivered) == "vra_gizli-token-degeri-123456"
    assert delivered.message_id == f"<{message_id}@visionroute>"


async def test_idempotency_key_prevents_duplicates(test_settings: Settings) -> None:
    key = f"test:dup:{uuid.uuid4()}"
    first = await _enqueue(
        test_settings,
        template="password_reset",
        recipient="dup@outbox.example",
        context=_RESET_CONTEXT,
        secret_context={"token": "vra_" + "a" * 20},
        idempotency_key=key,
    )
    second = await _enqueue(
        test_settings,
        template="password_reset",
        recipient="dup@outbox.example",
        context=_RESET_CONTEXT,
        secret_context={"token": "vra_" + "b" * 20},
        idempotency_key=key,
    )
    assert first is not None
    assert second is None


async def test_transient_failures_back_off_then_dead_letter(test_settings: Settings) -> None:
    await deliver_mail(test_settings)
    message_id = await _enqueue(
        test_settings,
        template="password_reset",
        recipient="gecici@outbox.example",
        context=_RESET_CONTEXT,
        secret_context={"token": "vra_" + "c" * 20},
        max_attempts=2,
    )
    assert message_id is not None
    sender = _FailingSender(permanent=False)

    await _run(test_settings, sender)
    after_first = await _row(test_settings, message_id)
    assert after_first["status"] == "pending"
    assert after_first["attempts"] == 1
    assert "421" in after_first["last_error"]
    assert after_first["secret_context_enc"] is not None  # still needed for the retry

    await _make_due(test_settings, message_id)
    await _run(test_settings, sender)
    after_second = await _row(test_settings, message_id)
    assert after_second["status"] == "dead_letter"
    assert after_second["attempts"] == 2
    assert after_second["secret_context_enc"] is None
    assert "vra_" not in (after_second["last_error"] or "")


async def test_permanent_failure_dead_letters_immediately(test_settings: Settings) -> None:
    await deliver_mail(test_settings)
    message_id = await _enqueue(
        test_settings,
        template="password_reset",
        recipient="kalici@outbox.example",
        context=_RESET_CONTEXT,
        secret_context={"token": "vra_" + "d" * 20},
    )
    assert message_id is not None
    await _run(test_settings, _FailingSender(permanent=True))
    row = await _row(test_settings, message_id)
    assert row["status"] == "dead_letter"
    assert row["attempts"] == 1


async def test_expired_sending_lease_is_reclaimed(test_settings: Settings) -> None:
    await deliver_mail(test_settings)
    message_id = await _enqueue(
        test_settings,
        template="password_reset",
        recipient="kira@outbox.example",
        context=_RESET_CONTEXT,
        secret_context={"token": "vra_" + "e" * 20},
    )
    assert message_id is not None
    # Simulate a worker that crashed after claiming the message.
    await _sql(
        test_settings,
        "UPDATE email_messages SET status = 'sending', attempts = 1, "
        "next_attempt_at = now() - interval '1 minute' WHERE id = :id",
        id=message_id,
    )
    await deliver_mail(test_settings)
    row = await _row(test_settings, message_id)
    assert row["status"] == "sent"
    assert row["attempts"] == 2


async def test_wrong_decryption_key_retries_instead_of_losing_mail(test_settings: Settings) -> None:
    await deliver_mail(test_settings)
    message_id = await _enqueue(
        test_settings,
        template="password_reset",
        recipient="anahtar@outbox.example",
        context=_RESET_CONTEXT,
        secret_context={"token": "vra_" + "f" * 20},
    )
    assert message_id is not None
    wrong = FieldCipher({"test-k1": Fernet.generate_key().decode()}, "test-k1")
    await _run(test_settings, MemoryMailSender(), cipher=wrong)
    row = await _row(test_settings, message_id)
    assert row["status"] == "pending"
    assert "Şifre çözme" in row["last_error"]

    await _make_due(test_settings, message_id)
    await deliver_mail(test_settings)
    assert (await _row(test_settings, message_id))["status"] == "sent"


async def test_unknown_template_is_dead_lettered(test_settings: Settings) -> None:
    await deliver_mail(test_settings)
    message_id = uuid.uuid4()
    await _sql(
        test_settings,
        "INSERT INTO email_messages (id, recipient, template, subject, context) "
        "VALUES (:id, 'bozuk@outbox.example', 'kaldirilmis_sablon', 'x', '{}')",
        id=message_id,
    )
    await deliver_mail(test_settings)
    row = await _row(test_settings, message_id)
    assert row["status"] == "dead_letter"
    assert "Şablon" in row["last_error"]


async def test_email_rows_are_tenant_isolated(client: TestClient, test_settings: Settings) -> None:
    owner_a = create_org_and_login(client, "mail-rls-a", "a@mail-rls-a.example")
    owner_b = create_org_and_login(client, "mail-rls-b", "b@mail-rls-b.example")
    created = client.post(
        "/api/v1/organizations/current/invitations",
        json={"email": "davetli@mail-rls.example", "role": "analyst"},
        headers=auth_headers(owner_a),
    )
    assert created.status_code == 201

    engine = build_engine(test_settings)
    try:
        counts = {}
        for label, auth in (("a", owner_a), ("b", owner_b)):
            async with engine.begin() as conn:
                await conn.execute(
                    text("SELECT set_config('app.tenant_id', :tid, true)"),
                    {"tid": auth["user"]["organization_id"]},  # type: ignore[index]
                )
                counts[label] = (
                    await conn.execute(
                        text(
                            "SELECT count(*) FROM email_messages "
                            "WHERE recipient = 'davetli@mail-rls.example'"
                        )
                    )
                ).scalar_one()
    finally:
        await engine.dispose()
    assert counts == {"a": 1, "b": 0}
