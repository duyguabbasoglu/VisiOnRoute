#!/usr/bin/env bash
# Prepare a disposable environment for the Playwright end-to-end suite:
# fresh database migrated to head, throwaway JWT/field/storage keys and empty
# mail/object directories under .localdata/e2e (gitignored).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
E2E_DIR="$ROOT/.localdata/e2e"
PGHOST="${E2E_PGHOST:-localhost}"
PGPORT="${E2E_PGPORT:-5433}"
PGUSER="${E2E_PGUSER:-visionroute}"
export PGPASSWORD="${E2E_PGPASSWORD:-visionroute}"
DB="${E2E_DB:-visionroute_e2e}"

if command -v psql >/dev/null 2>&1; then
  PSQL="psql"
elif [ -x /opt/homebrew/opt/postgresql@17/bin/psql ]; then
  PSQL="/opt/homebrew/opt/postgresql@17/bin/psql"
else
  echo "psql bulunamadı; PostgreSQL istemcisini kurun." >&2
  exit 1
fi

rm -rf "$E2E_DIR"
mkdir -p "$E2E_DIR/mail" "$E2E_DIR/objects"

"$PSQL" -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -v ON_ERROR_STOP=1 -q \
  -c "DROP DATABASE IF EXISTS $DB WITH (FORCE)" \
  -c "CREATE DATABASE $DB OWNER $PGUSER"

cd "$ROOT"
export VISIONROUTE_DISABLE_DOTENV=1
export VISIONROUTE_DATABASE_URL="postgresql+asyncpg://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$DB"
poetry run alembic upgrade head >/dev/null
poetry run visionroute keys generate --out "$E2E_DIR/keys" >/dev/null
poetry run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" \
  > "$E2E_DIR/field-key"
poetry run python -c "import secrets; print(secrets.token_urlsafe(32))" > "$E2E_DIR/storage-key"
chmod 600 "$E2E_DIR/field-key" "$E2E_DIR/storage-key"
echo "E2E ortamı hazır: $DB"
