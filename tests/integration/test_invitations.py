"""Invitation lifecycle: e-mail-only links, resend rotation, revocation,
tenant scoping, existing accounts, and plan limits at acceptance."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import (
    INVITEE_PASSWORD,
    auth_headers,
    create_org_and_login,
    deliver_mail,
    last_email_to,
    token_from,
)
from visionroute.config.settings import Settings

_INVITATIONS = "/api/v1/organizations/current/invitations"


def _invite(client: TestClient, owner: dict[str, object], email: str) -> dict[str, object]:
    response = client.post(
        _INVITATIONS, json={"email": email, "role": "analyst"}, headers=auth_headers(owner)
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def _accept(client: TestClient, token: str) -> int:
    return client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "full_name": "Davetli Kişi", "password": INVITEE_PASSWORD},
    ).status_code


async def test_link_only_in_email_and_resend_rotates_token(
    client: TestClient, test_settings: Settings
) -> None:
    owner = create_org_and_login(client, "inv-resend", "o@inv-resend.example")
    email = "d@inv-resend.example"
    invitation = _invite(client, owner, email)
    assert not any("token" in key for key in invitation)
    assert invitation["status"] == "pending"

    await deliver_mail(test_settings)
    first_token = token_from(last_email_to(email, "davet etti"))
    preview = client.post("/api/v1/auth/invitations/preview", json={"token": first_token})
    assert preview.status_code == 200
    assert preview.json()["organization_name"] == "Test Filo inv-resend"
    assert preview.json()["account_exists"] is False

    duplicate = client.post(
        _INVITATIONS, json={"email": email, "role": "analyst"}, headers=auth_headers(owner)
    )
    assert duplicate.status_code == 409

    resent = client.post(f"{_INVITATIONS}/{invitation['id']}/resend", headers=auth_headers(owner))
    assert resent.status_code == 200
    await deliver_mail(test_settings)
    second_token = token_from(last_email_to(email, "davet etti"))
    assert second_token != first_token

    assert _accept(client, first_token) == 404
    assert _accept(client, second_token) == 201

    listed = client.get(_INVITATIONS, headers=auth_headers(owner)).json()
    row = next(i for i in listed if i["id"] == invitation["id"])
    assert row["status"] == "accepted"
    assert row["email_status"] == "sent"


async def test_revoked_invitation_cannot_be_used(
    client: TestClient, test_settings: Settings
) -> None:
    owner = create_org_and_login(client, "inv-revoke", "o@inv-revoke.example")
    email = "d@inv-revoke.example"
    invitation = _invite(client, owner, email)
    await deliver_mail(test_settings)
    token = token_from(last_email_to(email, "davet etti"))

    assert (
        client.delete(f"{_INVITATIONS}/{invitation['id']}", headers=auth_headers(owner)).status_code
        == 204
    )
    assert _accept(client, token) == 404
    assert client.post("/api/v1/auth/invitations/preview", json={"token": token}).status_code == 404
    resend = client.post(f"{_INVITATIONS}/{invitation['id']}/resend", headers=auth_headers(owner))
    assert resend.status_code == 409
    listed = client.get(_INVITATIONS, headers=auth_headers(owner)).json()
    assert next(i for i in listed if i["id"] == invitation["id"])["status"] == "revoked"


def test_invitation_management_is_tenant_scoped(client: TestClient) -> None:
    owner_a = create_org_and_login(client, "inv-scope-a", "o@inv-scope-a.example")
    owner_b = create_org_and_login(client, "inv-scope-b", "o@inv-scope-b.example")
    invitation = _invite(client, owner_a, "d@inv-scope.example")

    headers_b = auth_headers(owner_b)
    assert (
        client.post(f"{_INVITATIONS}/{invitation['id']}/resend", headers=headers_b).status_code
        == 404
    )
    assert client.delete(f"{_INVITATIONS}/{invitation['id']}", headers=headers_b).status_code == 404
    assert all(
        i["id"] != invitation["id"] for i in client.get(_INVITATIONS, headers=headers_b).json()
    )


async def test_existing_account_accepts_without_new_password(
    client: TestClient, test_settings: Settings
) -> None:
    create_org_and_login(client, "inv-exist-a", "ortak@inv-exist.example")
    owner_b = create_org_and_login(client, "inv-exist-b", "o@inv-exist-b.example")
    _invite(client, owner_b, "ortak@inv-exist.example")
    await deliver_mail(test_settings)
    token = token_from(last_email_to("ortak@inv-exist.example", "davet etti"))

    preview = client.post("/api/v1/auth/invitations/preview", json={"token": token})
    assert preview.json()["account_exists"] is True
    accepted = client.post("/api/v1/auth/invitations/accept", json={"token": token})
    assert accepted.status_code == 201, accepted.text
    members = client.get(
        "/api/v1/organizations/current/members", headers=auth_headers(owner_b)
    ).json()
    assert any(m["email"] == "ortak@inv-exist.example" for m in members)


async def test_plan_user_limit_enforced_at_acceptance(
    client: TestClient, test_settings: Settings
) -> None:
    owner = create_org_and_login(client, "inv-limit", "o@inv-limit.example")
    emails = [f"u{i}@inv-limit.example" for i in range(5)]
    for email in emails:  # pending invitations do not consume seats yet
        _invite(client, owner, email)
    await deliver_mail(test_settings)
    tokens = [token_from(last_email_to(email, "davet etti")) for email in emails]

    assert [_accept(client, token) for token in tokens[:4]] == [201, 201, 201, 201]
    over = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": tokens[4], "full_name": "Fazla Kişi", "password": INVITEE_PASSWORD},
    )
    assert over.status_code == 409
    assert "Kullanıcı limiti aşıldı" in over.json()["error"]["message"]
