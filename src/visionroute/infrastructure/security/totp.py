"""TOTP (RFC 6238) and recovery codes via the established ``pyotp`` library.

- 30-second steps, 6 digits, ±1 step tolerance for clock skew;
- the caller persists the last accepted step and rejects any code whose step
  is not strictly newer (replay resistance);
- recovery codes are 80-bit random values; only SHA-256 digests are stored.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

import pyotp

TOTP_STEP_SECONDS = 30
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I ambiguity


def generate_totp_secret() -> str:
    return pyotp.random_base32(length=32)


def provisioning_uri(secret: str, *, account: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=issuer)


def matching_time_step(
    secret: str, code: str, *, now: datetime | None = None, window: int = 1
) -> int | None:
    """Return the time step ``code`` is valid for, or None."""
    normalized = "".join(code.split())
    if len(normalized) != 6 or not normalized.isdigit():
        return None
    totp = pyotp.TOTP(secret)
    current = int((now or datetime.now(UTC)).timestamp()) // TOTP_STEP_SECONDS
    for step in range(current - window, current + window + 1):
        if hmac.compare_digest(totp.at(step * TOTP_STEP_SECONDS), normalized):
            return step
    return None


def generate_recovery_codes(count: int = 10) -> list[str]:
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(16))
        codes.append("-".join(raw[i : i + 4] for i in range(0, 16, 4)))
    return codes


def normalize_recovery_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(normalize_recovery_code(code).encode()).hexdigest()


def looks_like_totp(code: str) -> bool:
    normalized = "".join(code.split())
    return len(normalized) == 6 and normalized.isdigit()
