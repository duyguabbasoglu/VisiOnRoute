"""Integration test infrastructure.

Creates a disposable ``visionroute_test`` database, migrates it to head via
Alembic (the real migration path, no create_all shortcuts), generates
throwaway JWT keys, and serves the real app through TestClient.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from visionroute.api.main import create_app
from visionroute.config.settings import Settings

BASE_URL = "postgresql+asyncpg://visionroute:visionroute@localhost:5433"
TEST_DB = "visionroute_test"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _sync_url(db: str) -> str:
    # psycopg not installed; use asyncpg through a sync driver trick is not
    # possible, so administrative statements run through psql instead.
    return f"{BASE_URL}/{db}"


def _psql(sql: str, db: str = "postgres") -> None:
    subprocess.run(  # noqa: S603 — fixed argv, test-only helper
        [
            "/opt/homebrew/opt/postgresql@17/bin/psql"
            if Path("/opt/homebrew/opt/postgresql@17/bin/psql").exists()
            else "psql",
            "-h",
            "localhost",
            "-p",
            "5433",
            "-U",
            "visionroute",
            "-d",
            db,
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "PGPASSWORD": "visionroute"},
    )


@pytest.fixture(scope="session")
def jwt_keys(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    key_dir = tmp_path_factory.mktemp("jwt")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = key_dir / "private.pem"
    public_path = key_dir / "public.pem"
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_path, public_path


@pytest.fixture(scope="session")
def test_database_url() -> Iterator[str]:
    _psql(f"DROP DATABASE IF EXISTS {TEST_DB}")
    _psql(f"CREATE DATABASE {TEST_DB} OWNER visionroute")
    url = _sync_url(TEST_DB)
    subprocess.run(  # noqa: S603 — fixed argv, test-only helper
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        env={**os.environ, "VISIONROUTE_DATABASE_URL": url},
    )
    yield url


TEST_FIELD_KEY = Fernet.generate_key().decode()


@pytest.fixture(scope="session")
def test_settings(test_database_url: str, jwt_keys: tuple[Path, Path]) -> Settings:
    private_path, public_path = jwt_keys
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=test_database_url,
        jwt_private_key_path=private_path,
        jwt_public_key_path=public_path,
        access_token_ttl_seconds=900,
        field_encryption_keys={"test-k1": TEST_FIELD_KEY},
        field_encryption_primary_key_id="test-k1",
        # The whole suite shares one client address; rate limiting has its own
        # tests with production-like limits (tests/integration/test_rate_limiting.py).
        login_rate_limit_per_minute=100_000,
        login_ip_rate_limit_per_minute=100_000,
        register_rate_limit_per_hour=100_000,
        token_rate_limit_per_minute=100_000,
        account_email_rate_limit_per_hour=100_000,
        ingest_rate_limit_per_minute=1_000_000,
    )


@pytest.fixture(scope="session")
def client(test_settings: Settings) -> Iterator[TestClient]:
    app = create_app(test_settings)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
