"""Deployment configuration: composed database URL, inline JWT keys, TLS policy."""

from __future__ import annotations

import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from visionroute.config.settings import Environment, Settings
from visionroute.infrastructure.realtime import asyncpg_dsn
from visionroute.infrastructure.security.tokens import JwtService


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg, arg-type]


def test_database_url_composed_from_parts_quotes_secret() -> None:
    settings = _settings(
        database_host="db.internal",
        database_port=6432,
        database_name="visionroute",
        database_user="app",
        database_password=SecretStr("p@ss:w/rd?#"),
        database_ssl=True,
    )
    assert settings.database_url == (
        "postgresql+asyncpg://app:p%40ss%3Aw%2Frd%3F%23@db.internal:6432/visionroute?ssl=require"
    )


def test_explicit_url_kept_without_parts() -> None:
    url = "postgresql+asyncpg://a:b@host:5432/x"
    assert _settings(database_url=url).database_url == url


def test_production_requires_database_tls() -> None:
    plain = _settings(
        environment=Environment.PRODUCTION, database_url="postgresql+asyncpg://a:b@db:5432/x"
    )
    assert any("TLS" in problem for problem in plain.validate_for_runtime())
    tls = _settings(
        environment=Environment.PRODUCTION,
        database_host="db",
        database_password=SecretStr("secret"),
        database_ssl=True,
    )
    assert not any("TLS" in problem for problem in tls.validate_for_runtime())


def test_asyncpg_dsn_translates_ssl_option() -> None:
    assert asyncpg_dsn("postgresql+asyncpg://a:b@db:5432/x?ssl=require") == (
        "postgresql://a:b@db:5432/x?sslmode=require"
    )
    assert asyncpg_dsn("postgresql+asyncpg://a:b@db:5432/x") == "postgresql://a:b@db:5432/x"


def test_jwt_keys_from_inline_pem_with_escaped_newlines() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    settings = _settings(
        # Env files often carry PEM on one line with literal "\n" sequences.
        jwt_private_key=SecretStr(private_pem.replace("\n", "\\n")),
        jwt_public_key=public_pem,
    )
    assert not any("JWT" in problem for problem in settings.validate_for_runtime())

    service = JwtService(settings)
    user_id = uuid.uuid4()
    token = service.issue_access_token(
        user_id=user_id, organization_id=None, role=None, is_platform_admin=False
    )
    assert service.verify_access_token(token).user_id == user_id
