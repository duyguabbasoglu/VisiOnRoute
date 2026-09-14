"""JWT access tokens (RS256 only) and opaque secret handling (ADR-0003).

Refresh tokens and API keys are opaque 256-bit random values; only their
SHA-256 digests are persisted. JWTs enforce iss/aud/exp/nbf/jti/kid and an
explicit algorithm allowlist to prevent algorithm-confusion attacks.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt

from visionroute.config.settings import Settings

_ALLOWED_ALGORITHMS = ["RS256"]
_KEY_ID = "visionroute-2026-01"  # rotated via docs/operations/key-rotation.md


class TokenError(Exception):
    """Raised when a token is invalid, expired, or malformed."""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    organization_id: uuid.UUID | None
    role: str | None
    is_platform_admin: bool
    jti: str
    issued_at: datetime


def _pem(inline: str | None, path: Path | None) -> bytes | None:
    """PEM from an inline value (escaped newlines allowed) or a file path."""
    if inline:
        return inline.replace("\\n", "\n").encode()
    if path is not None:
        return path.read_bytes()
    return None


class JwtService:
    def __init__(self, settings: Settings) -> None:
        private_key = _pem(
            settings.jwt_private_key.get_secret_value() if settings.jwt_private_key else None,
            settings.jwt_private_key_path,
        )
        public_key = _pem(settings.jwt_public_key, settings.jwt_public_key_path)
        if private_key is None or public_key is None:
            msg = "JWT anahtarları yapılandırılmamış."
            raise TokenError(msg)
        self._private_key = private_key
        self._public_key = public_key
        self._issuer = settings.jwt_issuer
        self._audience = settings.jwt_audience
        self._ttl = timedelta(seconds=settings.access_token_ttl_seconds)

    def issue_access_token(
        self,
        *,
        user_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        role: str | None,
        is_platform_admin: bool,
    ) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(user_id),
            # Sub-second precision (RFC 7519 NumericDate may be non-integer) so
            # a revocation watermark set in the same second still rejects tokens
            # issued before it.
            "iat": now.timestamp(),
            "nbf": now,
            "exp": now + self._ttl,
            "jti": secrets.token_urlsafe(16),
        }
        if organization_id is not None:
            payload["org"] = str(organization_id)
        if role is not None:
            payload["role"] = role
        if is_platform_admin:
            payload["platform_admin"] = True
        return jwt.encode(payload, self._private_key, algorithm="RS256", headers={"kid": _KEY_ID})

    def verify_access_token(self, token: str) -> AccessTokenClaims:
        try:
            # Only tokens signed with the current key id are accepted (a foreign
            # or missing kid is rejected before signature verification).
            if jwt.get_unverified_header(token).get("kid") != _KEY_ID:
                msg = "Bilinmeyen imzalama anahtarı."
                raise TokenError(msg)
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=_ALLOWED_ALGORITHMS,
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "nbf", "sub", "jti"]},
            )
        except jwt.PyJWTError as exc:
            raise TokenError(str(exc)) from exc
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            organization_id=uuid.UUID(payload["org"]) if "org" in payload else None,
            role=payload.get("role"),
            is_platform_admin=bool(payload.get("platform_admin", False)),
            jti=payload["jti"],
            issued_at=datetime.fromtimestamp(float(payload["iat"]), tz=UTC),
        )


def generate_opaque_secret(prefix: str) -> tuple[str, str]:
    """Return (cleartext, sha256_hex). Cleartext is shown once, never stored."""
    cleartext = f"{prefix}_{secrets.token_urlsafe(32)}"
    return cleartext, hash_opaque_secret(cleartext)


def hash_opaque_secret(cleartext: str) -> str:
    return hashlib.sha256(cleartext.encode()).hexdigest()
