"""Integration test infrastructure.

Creates a disposable ``visionroute_test`` database, migrates it to head via
Alembic (the real migration path, no create_all shortcuts), generates
throwaway JWT keys, and serves the real app through TestClient.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
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
# The application must never connect as a superuser: PostgreSQL lets superusers
# and BYPASSRLS roles skip row-level security, which would make every tenant
# isolation assertion pass without proving anything. Some PostgreSQL images make
# the bootstrap role a superuser (CI service containers do), so tests connect
# through a least-privilege role that inherits the owner's object rights but
# none of its role attributes — the same shape as the production runtime role.
APP_ROLE = "visionroute_test_app"
APP_PASSWORD = "visionroute_test_app"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _app_url(db: str) -> str:
    return f"postgresql+asyncpg://{APP_ROLE}:{APP_PASSWORD}@localhost:5433/{db}"


def _sync_url(db: str) -> str:
    # psycopg not installed; use asyncpg through a sync driver trick is not
    # possible, so administrative statements run through psql instead.
    return f"{BASE_URL}/{db}"


def _psql_path() -> str:
    brew = Path("/opt/homebrew/opt/postgresql@17/bin/psql")
    return str(brew) if brew.exists() else "psql"


def _psql_query(sql: str, db: str = "postgres") -> str:
    """Run a query as the owner role and return the single-value result."""
    result = subprocess.run(  # noqa: S603 — fixed argv, test-only helper
        [
            _psql_path(),
            "-h",
            "localhost",
            "-p",
            "5433",
            "-U",
            "visionroute",
            "-d",
            db,
            "-tA",
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "PGPASSWORD": "visionroute"},
    )
    return result.stdout.decode().strip()


def _try_psql(sql: str, db: str = "postgres") -> bool:
    """Run a statement, reporting failure instead of raising (optional setup)."""
    try:
        _psql(sql, db)
    except subprocess.CalledProcessError:
        return False
    return True


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
    owner_url = _sync_url(TEST_DB)
    subprocess.run(  # noqa: S603 — fixed argv, test-only helper
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        env={
            **os.environ,
            "VISIONROUTE_DATABASE_URL": owner_url,
            "VISIONROUTE_DISABLE_DOTENV": "1",
        },
    )
    # Create the least-privilege role when the owner may create roles (CI's
    # superuser can; a plain local role cannot) and fall back to the owner
    # otherwise — but never to a role that would bypass RLS.
    created = _try_psql(
        # Built from module constants only, never from test input.
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') "  # noqa: S608
        f"THEN CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}' "
        "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE; END IF; END $$;"
    )
    # Membership grants the owner's privileges on its objects (tables are FORCE
    # RLS, so policies still apply) but never its role attributes.
    if created and _try_psql(f"GRANT visionroute TO {APP_ROLE}"):
        yield _app_url(TEST_DB)
        return
    bypasses = _psql_query(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = 'visionroute'"
    )
    if bypasses == "t":
        pytest.fail(
            "The test database role bypasses row-level security, so tenant isolation "
            f"assertions would pass without enforcing anything. Grant CREATEROLE so the "
            f"'{APP_ROLE}' role can be created, or point the tests at a non-superuser role.",
            pytrace=False,
        )
    yield owner_url


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
        # Strict reuse detection by default; the retry window has its own tests
        # (tests/integration/test_refresh_retry.py).
        refresh_reuse_grace_seconds=0,
        field_encryption_keys={"test-k1": TEST_FIELD_KEY},
        field_encryption_primary_key_id="test-k1",
        mail_backend="memory",
        storage_backend="local",
        pdf_font_dir=(
            Path(os.environ["VISIONROUTE_TEST_PDF_FONT_DIR"])
            if os.environ.get("VISIONROUTE_TEST_PDF_FONT_DIR")
            else None
        ),
        local_storage_dir=Path(tempfile.mkdtemp(prefix="vr-objects-")),
        local_storage_signing_key="test-local-storage-signing-key",
        public_api_url="http://testserver",
        public_app_url="https://app.visionroute.test",
        # Most suites exercise features, not the verification policy; the
        # policy itself is tested with it enabled in test_account_security.py.
        require_verified_email=False,
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
