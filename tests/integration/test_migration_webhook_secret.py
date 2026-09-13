"""Migration round-trip: existing plaintext webhook secrets are encrypted on
upgrade and restored on downgrade, on a separate disposable database."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

from tests.conftest import BASE_URL, REPO_ROOT
from visionroute.infrastructure.security.crypto import FieldCipher

_DB = "visionroute_migration_webhook"
_BEFORE = "6e3bcf315d54"
_PSQL = (
    "/opt/homebrew/opt/postgresql@17/bin/psql"
    if Path("/opt/homebrew/opt/postgresql@17/bin/psql").exists()
    else "psql"
)

# Values are passed as psql variables (:'name' is quoted by psql itself).
_SEED_SQL = """
SELECT set_config('app.rls_bypass', 'on', false);
INSERT INTO organizations (id, name, slug) VALUES (:'org', 'Göç Filo', :'slug');
INSERT INTO webhook_endpoints (id, organization_id, url, secret)
VALUES (:'hook', :'org', 'https://alici.example/h', :'secret');
"""
_READ_ENC_SQL = """
SELECT set_config('app.rls_bypass', 'on', false) \\g /dev/null
SELECT secret_enc FROM webhook_endpoints WHERE id = :'hook';
"""
_READ_PLAIN_SQL = """
SELECT set_config('app.rls_bypass', 'on', false) \\g /dev/null
SELECT secret FROM webhook_endpoints WHERE id = :'hook';
"""
_COLUMNS_SQL = """
SELECT string_agg(column_name, ',') FROM information_schema.columns
WHERE table_name = 'webhook_endpoints';
"""


def _psql(sql: str, db: str = "postgres", **variables: str) -> str:
    argv = [_PSQL, "-h", "localhost", "-p", "5433", "-U", "visionroute", "-d", db]
    argv += ["-v", "ON_ERROR_STOP=1", "-tA"]
    for name, value in variables.items():
        argv += ["-v", f"{name}={value}"]
    result = subprocess.run(  # noqa: S603 — fixed argv, test-only helper
        argv,
        input=sql,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PGPASSWORD": "visionroute"},
    )
    return result.stdout.strip()


def _recreate_database() -> None:
    _psql("DROP DATABASE IF EXISTS " + _DB)
    _psql("CREATE DATABASE " + _DB + " OWNER visionroute")


def _alembic(
    *args: str, env: dict[str, str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — fixed argv, test-only helper
        [sys.executable, "-m", "alembic", *args],
        check=check,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def _columns() -> list[str]:
    return _psql(_COLUMNS_SQL, db=_DB).split(",")


def test_webhook_secret_encryption_migration_roundtrip() -> None:
    key = Fernet.generate_key().decode()
    env = {
        **os.environ,
        "VISIONROUTE_DATABASE_URL": f"{BASE_URL}/{_DB}",
        "VISIONROUTE_FIELD_ENCRYPTION_KEYS": json.dumps({"mig": key}),
    }
    _recreate_database()
    try:
        _alembic("upgrade", _BEFORE, env=env)
        hook_id = str(uuid.uuid4())
        _psql(
            _SEED_SQL,
            db=_DB,
            org=str(uuid.uuid4()),
            slug="goc-filo",
            hook=hook_id,
            secret="whsec_duz-metin-sir",
        )

        _alembic("upgrade", "head", env=env)
        stored = _psql(_READ_ENC_SQL, db=_DB, hook=hook_id)
        assert stored.startswith("enc1:mig:")
        assert FieldCipher({"mig": key}, "mig").decrypt(stored) == "whsec_duz-metin-sir"
        assert "secret_enc" in _columns()
        assert "secret" not in _columns()

        _alembic("downgrade", _BEFORE, env=env)
        assert _psql(_READ_PLAIN_SQL, db=_DB, hook=hook_id) == "whsec_duz-metin-sir"
    finally:
        _psql("DROP DATABASE IF EXISTS " + _DB)


def test_encryption_migration_refuses_to_run_without_keys() -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("VISIONROUTE_FIELD_")}
    env["VISIONROUTE_DATABASE_URL"] = f"{BASE_URL}/{_DB}"
    _recreate_database()
    try:
        _alembic("upgrade", _BEFORE, env=env)
        _psql(
            _SEED_SQL,
            db=_DB,
            org=str(uuid.uuid4()),
            slug="anahtarsiz",
            hook=str(uuid.uuid4()),
            secret="whsec_x",
        )
        result = _alembic("upgrade", "head", env=env, check=False)
        assert result.returncode != 0
        assert "VISIONROUTE_FIELD_ENCRYPTION_KEYS" in result.stderr
        # The plaintext column must still exist: nothing was dropped.
        assert "secret" in _columns()
    finally:
        _psql("DROP DATABASE IF EXISTS " + _DB)
