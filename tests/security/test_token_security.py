"""Security regression tests: JWT hardening, forged and expired tokens."""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from visionroute.config.settings import Settings
from visionroute.infrastructure.security.tokens import _KEY_ID as KEY_ID
from visionroute.infrastructure.security.tokens import JwtService, TokenError

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def jwt_service(test_settings: Settings) -> JwtService:
    return JwtService(test_settings)


def test_algorithm_confusion_hs256_rejected(client: TestClient, test_settings: Settings) -> None:
    """A token signed with HS256 using the *public* key as secret must fail."""
    assert test_settings.jwt_public_key_path is not None
    public_pem = Path(test_settings.jwt_public_key_path).read_bytes()
    now = int(datetime.now(UTC).timestamp())

    # PyJWT itself refuses to HMAC-sign with a PEM key, so build the forged
    # token by hand exactly as an attacker would.
    def b64(data: bytes) -> bytes:
        return base64.urlsafe_b64encode(data).rstrip(b"=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64(
        json.dumps(
            {
                "iss": test_settings.jwt_issuer,
                "aud": test_settings.jwt_audience,
                "sub": str(uuid.uuid4()),
                "iat": now,
                "nbf": now,
                "exp": now + 600,
                "jti": "forged",
                "platform_admin": True,
            }
        ).encode()
    )
    signing_input = header + b"." + payload
    signature = b64(hmac.new(public_pem, signing_input, hashlib.sha256).digest())
    forged = (signing_input + b"." + signature).decode()
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_alg_none_rejected(client: TestClient, test_settings: Settings) -> None:
    now = datetime.now(UTC)
    unsigned = pyjwt.encode(
        {
            "iss": test_settings.jwt_issuer,
            "aud": test_settings.jwt_audience,
            "sub": str(uuid.uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=10),
            "jti": "none-alg",
        },
        key=None,  # type: ignore[arg-type]
        algorithm="none",
    )
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {unsigned}"})
    assert response.status_code == 401


def test_expired_token_rejected(jwt_service: JwtService, client: TestClient) -> None:
    # Issue a token, then verify with a service whose clock already passed it:
    # simplest honest approach — craft an already-expired token with real key.
    private_pem = jwt_service._private_key
    now = datetime.now(UTC)
    expired = pyjwt.encode(
        {
            "iss": "visionroute",
            "aud": "visionroute-api",
            "sub": str(uuid.uuid4()),
            "iat": now - timedelta(hours=2),
            "nbf": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "jti": "expired",
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )
    with pytest.raises(TokenError):
        jwt_service.verify_access_token(expired)
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_wrong_audience_rejected(jwt_service: JwtService) -> None:
    private_pem = jwt_service._private_key
    now = datetime.now(UTC)
    wrong_aud = pyjwt.encode(
        {
            "iss": "visionroute",
            "aud": "baska-servis",
            "sub": str(uuid.uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=10),
            "jti": "wrong-aud",
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )
    with pytest.raises(TokenError):
        jwt_service.verify_access_token(wrong_aud)


def test_missing_required_claims_rejected(jwt_service: JwtService) -> None:
    private_pem = jwt_service._private_key
    now = datetime.now(UTC)
    no_jti = pyjwt.encode(
        {
            "iss": "visionroute",
            "aud": "visionroute-api",
            "sub": str(uuid.uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=10),
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )
    with pytest.raises(TokenError):
        jwt_service.verify_access_token(no_jti)


def test_sql_injection_strings_handled(client: TestClient) -> None:
    payloads = ["' OR 1=1 --", '"; DROP TABLE users; --', "admin'--"]
    for payload in payloads:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": f"{payload}@x.example", "password": payload},
        )
        # Parametrized queries: injection collapses to a failed login or 422.
        assert response.status_code in (401, 422)


def test_oversized_login_body_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "a@b.example", "password": "x" * 10_000},
    )
    assert response.status_code == 422


def _valid_claims() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "iss": "visionroute",
        "aud": "visionroute-api",
        "sub": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=10),
        "jti": "kid-check",
    }


def test_unknown_or_missing_kid_rejected(jwt_service: JwtService, client: TestClient) -> None:
    private_pem = jwt_service._private_key
    foreign_kid = pyjwt.encode(
        _valid_claims(), private_pem, algorithm="RS256", headers={"kid": "baska-anahtar"}
    )
    no_kid = pyjwt.encode(_valid_claims(), private_pem, algorithm="RS256")
    for token in (foreign_kid, no_kid):
        with pytest.raises(TokenError):
            jwt_service.verify_access_token(token)
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    # Control: the same claims with the expected kid pass signature checks.
    valid = pyjwt.encode(_valid_claims(), private_pem, algorithm="RS256", headers={"kid": KEY_ID})
    assert jwt_service.verify_access_token(valid).jti == "kid-check"
