"""Settings validation unit tests."""

from pathlib import Path

import pytest

from visionroute.config.settings import Environment, Settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_database_url_scheme_enforced() -> None:
    with pytest.raises(ValueError, match="asyncpg"):
        _settings(database_url="postgresql://x:y@localhost/db")


def test_runtime_validation_flags_missing_jwt_keys() -> None:
    problems = _settings().validate_for_runtime()
    assert any("JWT özel anahtarı" in p for p in problems)


def test_production_rejects_debug_and_insecure_cookies(tmp_path: Path) -> None:
    private = tmp_path / "private.pem"
    public = tmp_path / "public.pem"
    private.write_text("x")
    public.write_text("x")
    problems = _settings(
        environment=Environment.PRODUCTION,
        debug=True,
        cookie_secure=False,
        jwt_private_key_path=private,
        jwt_public_key_path=public,
        database_url="postgresql+asyncpg://u:p@db.internal/visionroute",
    ).validate_for_runtime()
    assert any("debug" in p for p in problems)
    assert any("cookie_secure" in p for p in problems)


def test_local_defaults_are_valid_apart_from_keys() -> None:
    problems = _settings().validate_for_runtime()
    assert all("JWT" in p for p in problems)
