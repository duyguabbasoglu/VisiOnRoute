"""Shared test helpers."""

from __future__ import annotations

import re
from urllib.parse import unquote

from fastapi.testclient import TestClient

from visionroute.application.mail.delivery import MailDeliveryService
from visionroute.config.settings import Settings
from visionroute.domain.mail import OutgoingEmail
from visionroute.infrastructure.db.engine import build_engine, build_session_factory
from visionroute.infrastructure.mail.memory import SENT_MESSAGES, MemoryMailSender
from visionroute.infrastructure.security.crypto import build_field_cipher

DEFAULT_PASSWORD = "GuvenliParola42!"
INVITEE_PASSWORD = "DavetliParola7!"
_TOKEN_RE = re.compile(r"#token=([A-Za-z0-9_.~%-]+)")


def auth_headers(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def create_org_and_login(
    client: TestClient, slug: str, email: str, password: str = DEFAULT_PASSWORD
) -> dict[str, object]:
    """Register an organization and return the AuthResponse payload."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"Test Filo {slug}",
            "slug": slug,
            "email": email,
            "full_name": "Test Kullanıcı",
            "password": password,
        },
    )
    assert response.status_code == 201, response.text
    payload: dict[str, object] = response.json()
    return payload


async def deliver_mail(settings: Settings) -> int:
    """Run the real delivery service (in-memory sender) until the queue is idle."""
    engine = build_engine(settings)
    try:
        service = MailDeliveryService(
            build_session_factory(engine),
            MemoryMailSender(),
            build_field_cipher(settings),
            settings,
        )
        total = 0
        while True:
            stats = await service.deliver_due(limit=50)
            total += stats.handled
            if stats.handled == 0:
                return total
    finally:
        await engine.dispose()


def last_email_to(address: str, subject_contains: str | None = None) -> OutgoingEmail:
    for email in reversed(SENT_MESSAGES):
        if email.to_address == address and (
            subject_contains is None or subject_contains in email.subject
        ):
            return email
    msg = f"{address} adresine beklenen e-posta gönderilmedi"
    raise AssertionError(msg)


def emails_to(address: str) -> list[OutgoingEmail]:
    return [email for email in SENT_MESSAGES if email.to_address == address]


def token_from(email: OutgoingEmail) -> str:
    match = _TOKEN_RE.search(email.text_body)
    assert match, "e-postada tek kullanımlık bağlantı yok"
    return unquote(match.group(1))


async def invite_and_login(
    client: TestClient,
    settings: Settings,
    owner: dict[str, object],
    email: str,
    role: str,
    password: str = INVITEE_PASSWORD,
) -> dict[str, object]:
    """Invite ``email`` with ``role``, accept via the delivered e-mail link, log in."""
    invitation = client.post(
        "/api/v1/organizations/current/invitations",
        json={"email": email, "role": role},
        headers=auth_headers(owner),
    )
    assert invitation.status_code == 201, invitation.text
    assert "invitation_token" not in invitation.json()
    await deliver_mail(settings)
    token = token_from(last_email_to(email, "davet etti"))

    accepted = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "full_name": "Davetli Kişi", "password": password},
    )
    assert accepted.status_code == 201, accepted.text

    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    payload: dict[str, object] = login.json()
    return payload
