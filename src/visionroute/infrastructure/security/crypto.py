"""Application-level field encryption for secrets that must live in the database.

Stored format: ``enc1:<key_id>:<fernet_token>``.

Fernet (AES-128-CBC + HMAC-SHA256, authenticated, from ``cryptography``) is
used as-is — no custom cryptography. Keys are versioned by id: the primary
key encrypts new values, every configured key can decrypt, so keys rotate
without downtime (add new key → make it primary → re-encrypt with
``visionroute security reencrypt`` → remove the old key). Keys come from
configuration (AWS Secrets Manager in production), never from the database.

Error messages never include plaintext or ciphertext.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from cryptography.fernet import Fernet, InvalidToken

from visionroute.config.settings import Settings

_PREFIX = "enc1"
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class FieldEncryptionError(Exception):
    """Configuration or decryption failure (message is safe to log)."""


class FieldCipher:
    def __init__(self, keys: Mapping[str, str], primary_key_id: str) -> None:
        if not keys:
            msg = "Alan şifreleme anahtarı yapılandırılmamış."
            raise FieldEncryptionError(msg)
        if primary_key_id not in keys:
            msg = "Birincil alan şifreleme anahtar kimliği anahtar listesinde yok."
            raise FieldEncryptionError(msg)
        self._fernets: dict[str, Fernet] = {}
        for key_id, key in keys.items():
            if not _KEY_ID_RE.fullmatch(key_id):
                msg = f"Geçersiz anahtar kimliği: {key_id[:32]!r}"
                raise FieldEncryptionError(msg)
            try:
                self._fernets[key_id] = Fernet(key.encode())
            except (ValueError, TypeError) as exc:
                msg = f"Geçersiz alan şifreleme anahtarı ({key_id})."
                raise FieldEncryptionError(msg) from exc
        self._primary = primary_key_id

    @property
    def primary_key_id(self) -> str:
        return self._primary

    def encrypt(self, plaintext: str) -> str:
        token = self._fernets[self._primary].encrypt(plaintext.encode()).decode()
        return f"{_PREFIX}:{self._primary}:{token}"

    def decrypt(self, value: str) -> str:
        key_id, token = self._split(value)
        fernet = self._fernets.get(key_id)
        if fernet is None:
            msg = f"Şifreli alan bilinmeyen bir anahtarla şifrelenmiş ({key_id})."
            raise FieldEncryptionError(msg)
        try:
            return fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            msg = "Şifreli alan çözülemedi (anahtar veya veri uyuşmazlığı)."
            raise FieldEncryptionError(msg) from exc

    def key_id_of(self, value: str) -> str:
        return self._split(value)[0]

    def needs_rotation(self, value: str) -> bool:
        return self.key_id_of(value) != self._primary

    def rotate(self, value: str) -> str:
        """Re-encrypt ``value`` under the primary key (no-op if already)."""
        if not self.needs_rotation(value):
            return value
        return self.encrypt(self.decrypt(value))

    @staticmethod
    def _split(value: str) -> tuple[str, str]:
        parts = value.split(":", 2)
        if len(parts) != 3 or parts[0] != _PREFIX or not parts[1] or not parts[2]:
            msg = "Şifreli alan biçimi tanınmadı."
            raise FieldEncryptionError(msg)
        return parts[1], parts[2]


def build_field_cipher(settings: Settings) -> FieldCipher | None:
    """Return a cipher, or None when no keys are configured (local only;
    production-like environments refuse to start without keys)."""
    if not settings.field_encryption_keys:
        return None
    primary = settings.resolved_primary_key_id()
    if primary is None:
        msg = "Birden fazla anahtar var; birincil anahtar kimliği belirtilmeli."
        raise FieldEncryptionError(msg)
    keys = {
        key_id: secret.get_secret_value()
        for key_id, secret in settings.field_encryption_keys.items()
    }
    return FieldCipher(keys, primary)


def generate_field_key() -> str:
    return Fernet.generate_key().decode()
