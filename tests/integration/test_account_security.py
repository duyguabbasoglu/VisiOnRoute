"""Password reset, e-mail verification, TOTP two-factor authentication, and
organization MFA policy, end to end through the API and the mail outbox."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.helpers import (
    DEFAULT_PASSWORD,
    INVITEE_PASSWORD,
    auth_headers,
    create_org_and_login,
    deliver_mail,
    emails_to,
    invite_and_login,
    last_email_to,
    token_from,
)
from visionroute.api.main import create_app
from visionroute.config.settings import Settings
from visionroute.infrastructure.db.engine import build_engine

NEW_PASSWORD = "YeniGuvenliParola99!"


async def _sql(settings: Settings, statement: str, **params: Any) -> list[Any]:
    engine = build_engine(settings)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.rls_bypass', 'on', true)"))
            result = await conn.execute(text(statement), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


def _code(secret: str, steps_ahead: int = 0) -> str:
    return pyotp.TOTP(secret).at(int(datetime.now(UTC).timestamp()) + 30 * steps_ahead)


def _enable_mfa(
    client: TestClient, auth: dict[str, object], password: str
) -> tuple[str, list[str]]:
    setup = client.post(
        "/api/v1/auth/mfa/setup", json={"password": password}, headers=auth_headers(auth)
    )
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    confirm = client.post(
        "/api/v1/auth/mfa/confirm", json={"code": _code(secret)}, headers=auth_headers(auth)
    )
    assert confirm.status_code == 200, confirm.text
    return secret, confirm.json()["recovery_codes"]


def _login(client: TestClient, email: str, password: str) -> dict[str, Any]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# ------------------------------------------------------------------ password reset


async def test_password_reset_flow_revokes_old_sessions(
    client: TestClient, test_settings: Settings
) -> None:
    email = "reset@reset-flow.example"
    owner = create_org_and_login(client, "reset-flow", email)
    old_refresh = client.cookies.get("vr_refresh")
    assert old_refresh

    unknown = client.post("/api/v1/auth/password/forgot", json={"email": "yok@reset-flow.example"})
    known = client.post("/api/v1/auth/password/forgot", json={"email": email})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()

    await deliver_mail(test_settings)
    assert emails_to("yok@reset-flow.example") == []
    token = token_from(last_email_to(email, "parola sıfırlama"))

    weak = client.post("/api/v1/auth/password/reset", json={"token": token, "password": "kisa"})
    assert weak.status_code == 422  # the link is not consumed by a rejected password

    done = client.post(
        "/api/v1/auth/password/reset", json={"token": token, "password": NEW_PASSWORD}
    )
    assert done.status_code == 200, done.text
    assert "oturumlar kapatıldı" in done.json()["message"]

    reused = client.post(
        "/api/v1/auth/password/reset", json={"token": token, "password": "BaskaParola123!"}
    )
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "TOKEN_INVALID"

    # The pre-reset access token and refresh session no longer work.
    stale = client.get("/api/v1/organizations/current", headers=auth_headers(owner))
    assert stale.status_code == 401
    client.cookies.set("vr_refresh", old_refresh, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401
    client.cookies.clear()

    assert (
        client.post(
            "/api/v1/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
        ).status_code
        == 401
    )
    assert _login(client, email, NEW_PASSWORD)["access_token"]

    await deliver_mail(test_settings)
    assert "Parolanız değiştirildi" in last_email_to(email, "güvenlik bildirimi").subject
    client.cookies.clear()


async def test_expired_and_superseded_reset_links_rejected(
    client: TestClient, test_settings: Settings
) -> None:
    email = "reset@reset-expiry.example"
    create_org_and_login(client, "reset-expiry", email)
    client.cookies.clear()
    for _ in range(2):
        client.post("/api/v1/auth/password/forgot", json={"email": email})
    await deliver_mail(test_settings)
    tokens = [token_from(m) for m in emails_to(email) if "parola sıfırlama" in m.subject]
    first, second = tokens[-2], tokens[-1]

    superseded = client.post(
        "/api/v1/auth/password/reset", json={"token": first, "password": NEW_PASSWORD}
    )
    assert superseded.status_code == 400

    await _sql(
        test_settings,
        "UPDATE user_tokens SET expires_at = now() - interval '1 minute' "
        "WHERE token_hash IS NOT NULL AND used_at IS NULL AND purpose = 'password_reset' "
        "AND user_id = (SELECT id FROM users WHERE email = :email)",
        email=email,
    )
    expired = client.post(
        "/api/v1/auth/password/reset", json={"token": second, "password": NEW_PASSWORD}
    )
    assert expired.status_code == 400


# ------------------------------------------------------------------ e-mail verification


async def test_registration_verification_link(client: TestClient, test_settings: Settings) -> None:
    email = "v@verify-flow.example"
    owner = create_org_and_login(client, "verify-flow", email)
    assert owner["user"]["email_verified"] is False  # type: ignore[index]

    await deliver_mail(test_settings)
    token = token_from(last_email_to(email, "doğrulayın"))
    verified = client.post("/api/v1/auth/email/verify", json={"token": token})
    assert verified.status_code == 200
    me = client.get("/api/v1/auth/me", headers=auth_headers(owner)).json()
    assert me["email_verified"] is True

    assert client.post("/api/v1/auth/email/verify", json={"token": token}).status_code == 400
    resend = client.post("/api/v1/auth/email/resend-verification", headers=auth_headers(owner))
    assert resend.status_code == 202
    assert "zaten doğrulanmış" in resend.json()["message"]
    client.cookies.clear()


async def test_sensitive_actions_require_verified_email(test_settings: Settings) -> None:
    strict = test_settings.model_copy(update={"require_verified_email": True})
    with TestClient(create_app(strict), raise_server_exceptions=False) as strict_client:
        email = "p@verify-policy.example"
        owner = create_org_and_login(strict_client, "verify-policy", email)
        invite = {"email": "davetli@verify-policy.example", "role": "analyst"}

        denied = strict_client.post(
            "/api/v1/organizations/current/invitations", json=invite, headers=auth_headers(owner)
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"

        await deliver_mail(strict)
        token = token_from(last_email_to(email, "doğrulayın"))
        assert (
            strict_client.post("/api/v1/auth/email/verify", json={"token": token}).status_code
            == 200
        )
        allowed = strict_client.post(
            "/api/v1/organizations/current/invitations", json=invite, headers=auth_headers(owner)
        )
        assert allowed.status_code == 201, allowed.text


# ------------------------------------------------------------------ two-factor authentication


async def test_mfa_enrollment_login_replay_and_recovery(
    client: TestClient, test_settings: Settings
) -> None:
    email = "m@mfa-flow.example"
    owner = create_org_and_login(client, "mfa-flow", email)
    headers = auth_headers(owner)

    wrong_password = client.post(
        "/api/v1/auth/mfa/setup", json={"password": "YanlisParola!!1"}, headers=headers
    )
    assert wrong_password.status_code == 403
    assert wrong_password.json()["error"]["code"] == "REAUTH_FAILED"

    setup = client.post(
        "/api/v1/auth/mfa/setup", json={"password": DEFAULT_PASSWORD}, headers=headers
    )
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    bad_confirm = client.post("/api/v1/auth/mfa/confirm", json={"code": "000000"}, headers=headers)
    assert bad_confirm.status_code == 401
    confirm = client.post("/api/v1/auth/mfa/confirm", json={"code": _code(secret)}, headers=headers)
    assert confirm.status_code == 200
    recovery_codes = confirm.json()["recovery_codes"]
    assert len(recovery_codes) == 10

    stored = await _sql(
        test_settings, "SELECT mfa_totp_secret_enc FROM users WHERE email = :e", e=email
    )
    assert stored[0][0].startswith("enc1:")
    assert secret not in stored[0][0]
    client.cookies.clear()

    challenge_response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    challenge = challenge_response.json()
    assert challenge["mfa_required"] is True
    assert "access_token" not in challenge
    assert "vr_refresh" not in challenge_response.cookies

    wrong = client.post(
        "/api/v1/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": "123456"}
    )
    assert wrong.status_code == 401
    next_code = _code(secret, steps_ahead=1)
    success = client.post(
        "/api/v1/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": next_code}
    )
    assert success.status_code == 200, success.text
    assert success.json()["user"]["mfa_enabled"] is True

    # The same code cannot be replayed, even with a fresh challenge.
    replay_challenge = _login(client, email, DEFAULT_PASSWORD)
    replay = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": replay_challenge["mfa_token"], "code": next_code},
    )
    assert replay.status_code == 401

    # A consumed challenge cannot be reused either.
    reuse = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": challenge["mfa_token"], "code": _code(secret, steps_ahead=1)},
    )
    assert reuse.status_code == 401

    recovery_challenge = _login(client, email, DEFAULT_PASSWORD)
    with_recovery = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": recovery_challenge["mfa_token"], "recovery_code": recovery_codes[0]},
    )
    assert with_recovery.status_code == 200
    again = _login(client, email, DEFAULT_PASSWORD)
    reused_recovery = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": again["mfa_token"], "recovery_code": recovery_codes[0]},
    )
    assert reused_recovery.status_code == 401

    await deliver_mail(test_settings)
    subjects = [m.subject for m in emails_to(email)]
    assert any("İki adımlı doğrulama etkinleştirildi" in s for s in subjects)
    assert any("kurtarma kodu kullanıldı" in s for s in subjects)
    client.cookies.clear()


async def test_mfa_challenge_attempts_are_bounded(
    client: TestClient, test_settings: Settings
) -> None:
    email = "m@mfa-bounded.example"
    owner = create_org_and_login(client, "mfa-bounded", email)
    secret, _codes = _enable_mfa(client, owner, DEFAULT_PASSWORD)
    client.cookies.clear()

    challenge = _login(client, email, DEFAULT_PASSWORD)["mfa_token"]
    for _ in range(5):
        attempt = client.post(
            "/api/v1/auth/mfa/verify", json={"mfa_token": challenge, "code": "999999"}
        )
        assert attempt.status_code == 401
    exhausted = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": challenge, "code": _code(secret, steps_ahead=1)},
    )
    assert exhausted.status_code == 401
    client.cookies.clear()


async def test_disable_mfa_requires_password_and_second_factor(
    client: TestClient, test_settings: Settings
) -> None:
    email = "m@mfa-disable.example"
    owner = create_org_and_login(client, "mfa-disable", email)
    _secret, codes = _enable_mfa(client, owner, DEFAULT_PASSWORD)
    headers = auth_headers(owner)

    wrong_password = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": "YanlisParola!!1", "code": codes[0]},
        headers=headers,
    )
    assert wrong_password.status_code == 403
    wrong_code = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": DEFAULT_PASSWORD, "code": "ZZZZ-ZZZZ-ZZZZ-ZZZZ"},
        headers=headers,
    )
    assert wrong_code.status_code == 401
    disabled = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": DEFAULT_PASSWORD, "code": codes[1]},
        headers=headers,
    )
    assert disabled.status_code == 200
    client.cookies.clear()
    assert "access_token" in _login(client, email, DEFAULT_PASSWORD)
    client.cookies.clear()


async def test_organization_mfa_policy_requires_enrollment(
    client: TestClient, test_settings: Settings
) -> None:
    owner = create_org_and_login(client, "mfa-policy", "o@mfa-policy.example")
    member = await invite_and_login(
        client, test_settings, owner, "uye@mfa-policy.example", "analyst"
    )

    premature = client.patch(
        "/api/v1/organizations/current/security",
        json={"mfa_required": True},
        headers=auth_headers(owner),
    )
    assert premature.status_code == 409  # owner must enroll first

    _enable_mfa(client, owner, DEFAULT_PASSWORD)
    enabled = client.patch(
        "/api/v1/organizations/current/security",
        json={"mfa_required": True},
        headers=auth_headers(owner),
    )
    assert enabled.status_code == 200

    blocked = client.get("/api/v1/organizations/current", headers=auth_headers(member))
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "MFA_ENROLLMENT_REQUIRED"
    me = client.get("/api/v1/auth/me", headers=auth_headers(member))
    assert me.status_code == 200
    assert me.json()["mfa_required"] is True

    _enable_mfa(client, member, INVITEE_PASSWORD)
    assert (
        client.get("/api/v1/organizations/current", headers=auth_headers(member)).status_code == 200
    )
    client.cookies.clear()


async def test_owner_mfa_reset_rules(client: TestClient, test_settings: Settings) -> None:
    owner_a = create_org_and_login(client, "mfa-reset-a", "o@mfa-reset-a.example")
    owner_b = create_org_and_login(client, "mfa-reset-b", "o@mfa-reset-b.example")
    lost = await invite_and_login(
        client, test_settings, owner_a, "kayip@mfa-reset.example", "analyst"
    )
    shared = await invite_and_login(
        client, test_settings, owner_a, "ortak@mfa-reset.example", "analyst"
    )
    admin = await invite_and_login(
        client, test_settings, owner_a, "yonetici@mfa-reset.example", "admin"
    )
    _enable_mfa(client, lost, INVITEE_PASSWORD)
    _enable_mfa(client, shared, INVITEE_PASSWORD)

    # "shared" also joins organization B with the existing account.
    client.post(
        "/api/v1/organizations/current/invitations",
        json={"email": "ortak@mfa-reset.example", "role": "analyst"},
        headers=auth_headers(owner_b),
    )
    await deliver_mail(test_settings)
    joined = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token_from(last_email_to("ortak@mfa-reset.example", "davet etti"))},
    )
    assert joined.status_code == 201, joined.text

    members = client.get(
        "/api/v1/organizations/current/members", headers=auth_headers(owner_a)
    ).json()
    ids = {m["email"]: m["membership_id"] for m in members}
    assert (
        next(m for m in members if m["email"] == "kayip@mfa-reset.example")["mfa_enabled"] is True
    )

    def reset(auth: dict[str, object], membership_id: str) -> int:
        return client.delete(
            f"/api/v1/organizations/current/members/{membership_id}/mfa", headers=auth_headers(auth)
        ).status_code

    assert reset(admin, ids["kayip@mfa-reset.example"]) == 403  # owners only
    assert reset(owner_b, ids["kayip@mfa-reset.example"]) == 404  # other tenant
    assert reset(owner_a, ids["ortak@mfa-reset.example"]) == 409  # member of another org
    assert reset(owner_a, ids["kayip@mfa-reset.example"]) == 204

    # The reset user's existing access token is revoked immediately.
    revoked = client.get("/api/v1/organizations/current", headers=auth_headers(lost))
    assert revoked.status_code == 401
    client.cookies.clear()
    relogin = _login(client, "kayip@mfa-reset.example", INVITEE_PASSWORD)
    assert "access_token" in relogin
    assert relogin["user"]["mfa_enabled"] is False
    client.cookies.clear()
