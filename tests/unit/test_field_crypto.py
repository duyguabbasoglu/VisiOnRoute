"""Field encryption: format, rotation, and failure behaviour."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from visionroute.config.settings import Settings
from visionroute.infrastructure.security.crypto import (
    FieldCipher,
    FieldEncryptionError,
    build_field_cipher,
    generate_field_key,
)

OLD_KEY = Fernet.generate_key().decode()
NEW_KEY = Fernet.generate_key().decode()


def test_roundtrip_and_format() -> None:
    cipher = FieldCipher({"k1": OLD_KEY}, "k1")
    stored = cipher.encrypt("whsec_gizli-deger")
    assert stored.startswith("enc1:k1:")
    assert "whsec_gizli-deger" not in stored
    assert cipher.decrypt(stored) == "whsec_gizli-deger"


def test_each_encryption_is_randomised() -> None:
    cipher = FieldCipher({"k1": OLD_KEY}, "k1")
    assert cipher.encrypt("ayni") != cipher.encrypt("ayni")


def test_rotation_keeps_old_values_readable() -> None:
    old = FieldCipher({"k1": OLD_KEY}, "k1")
    stored = old.encrypt("deger")

    rotated_ring = FieldCipher({"k1": OLD_KEY, "k2": NEW_KEY}, "k2")
    assert rotated_ring.decrypt(stored) == "deger"
    assert rotated_ring.needs_rotation(stored)

    rewritten = rotated_ring.rotate(stored)
    assert rotated_ring.key_id_of(rewritten) == "k2"
    assert not rotated_ring.needs_rotation(rewritten)
    assert rotated_ring.rotate(rewritten) == rewritten

    # After the old key is retired, rewritten values still decrypt.
    assert FieldCipher({"k2": NEW_KEY}, "k2").decrypt(rewritten) == "deger"


def test_wrong_key_fails_without_leaking_values() -> None:
    stored = FieldCipher({"k1": OLD_KEY}, "k1").encrypt("cok-gizli")
    impostor = FieldCipher({"k1": NEW_KEY}, "k1")
    with pytest.raises(FieldEncryptionError) as excinfo:
        impostor.decrypt(stored)
    assert "cok-gizli" not in str(excinfo.value)
    assert stored.split(":")[2] not in str(excinfo.value)


def test_unknown_key_id_and_tampering_rejected() -> None:
    cipher = FieldCipher({"k1": OLD_KEY}, "k1")
    stored = cipher.encrypt("x")
    with pytest.raises(FieldEncryptionError):
        cipher.decrypt(stored.replace("enc1:k1:", "enc1:k9:"))
    with pytest.raises(FieldEncryptionError):
        cipher.decrypt(stored[:-4] + "AAAA")
    for malformed in ("", "plain-text", "enc1::abc", "enc2:k1:abc"):
        with pytest.raises(FieldEncryptionError):
            cipher.decrypt(malformed)


def test_invalid_configuration_rejected() -> None:
    with pytest.raises(FieldEncryptionError):
        FieldCipher({}, "k1")
    with pytest.raises(FieldEncryptionError):
        FieldCipher({"k1": OLD_KEY}, "k2")
    with pytest.raises(FieldEncryptionError):
        FieldCipher({"k1": "kisa-anahtar"}, "k1")
    with pytest.raises(FieldEncryptionError):
        FieldCipher({"bad id!": OLD_KEY}, "bad id!")


def test_build_from_settings() -> None:
    assert build_field_cipher(Settings(_env_file=None)) is None  # type: ignore[call-arg]

    single = Settings(_env_file=None, field_encryption_keys={"only": OLD_KEY})  # type: ignore[call-arg]
    cipher = build_field_cipher(single)
    assert cipher is not None
    assert cipher.primary_key_id == "only"

    ambiguous = Settings(  # type: ignore[call-arg]
        _env_file=None, field_encryption_keys={"a": OLD_KEY, "b": NEW_KEY}
    )
    assert any("birincil" in p.lower() for p in ambiguous.validate_for_runtime())
    with pytest.raises(FieldEncryptionError):
        build_field_cipher(ambiguous)


def test_secret_values_are_masked_in_settings_repr() -> None:
    settings = Settings(_env_file=None, field_encryption_keys={"k1": OLD_KEY})  # type: ignore[call-arg]
    assert OLD_KEY not in repr(settings)


def test_generated_key_is_usable() -> None:
    key = generate_field_key()
    assert FieldCipher({"gen": key}, "gen").decrypt(FieldCipher({"gen": key}, "gen").encrypt("v"))
