"""Typed application settings.

All configuration comes from the environment (or AWS Secrets Manager in
production, injected as environment variables by the task definition).
Secrets must never be hardcoded. Validation failures abort startup with a
clear message instead of failing later at request time.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_production_like(self) -> bool:
        return self in (Environment.STAGING, Environment.PRODUCTION)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VISIONROUTE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.LOCAL
    debug: bool = False

    # --- Database ---
    database_url: str = "postgresql+asyncpg://visionroute:visionroute@localhost:5433/visionroute"
    database_pool_size: int = 10
    database_pool_max_overflow: int = 10

    # --- Redis (cache + rate limiting only; not a job broker, see ADR-0002) ---
    redis_url: str = "redis://localhost:6379/0"

    # --- JWT (RS256 only; see ADR-0003) ---
    jwt_private_key_path: Path | None = None
    jwt_public_key_path: Path | None = None
    jwt_issuer: str = "visionroute"
    jwt_audience: str = "visionroute-api"
    access_token_ttl_seconds: int = Field(default=900, le=3600)
    refresh_token_ttl_seconds: int = Field(default=14 * 24 * 3600)

    # --- Web ---
    cors_origins: list[str] = ["http://localhost:3000"]
    cookie_secure: bool = False
    cookie_domain: str | None = None
    # Base URL of the customer-facing web app; used to build links in e-mails.
    public_app_url: str = "http://localhost:3000"

    # --- Field encryption (docs/operations/key-rotation.md) ---
    # JSON object of key id -> Fernet key, e.g. {"k2026a": "<44 chars>"}.
    # Generate: poetry run visionroute keys generate-field-key
    field_encryption_keys: dict[str, SecretStr] = Field(default_factory=dict)
    field_encryption_primary_key_id: str | None = None

    # --- Mail ---
    # smtp: real delivery (Mailpit locally, provider in production)
    # file: local development, writes .eml files to mail_file_dir
    # memory: automated tests only
    mail_backend: Literal["smtp", "file", "memory"] = "file"
    mail_file_dir: Path = Path(".localdata/mail")
    mail_from_name: str = "VISiOnRoute"
    mail_max_attempts: int = Field(default=8, ge=1, le=20)
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "no-reply@visionroute.local"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: float = Field(default=15.0, gt=0, le=120)

    # --- Identity policy ---
    require_verified_email: bool = True
    invitation_ttl_days: int = Field(default=7, ge=1, le=30)
    password_reset_ttl_minutes: int = Field(default=30, ge=5, le=240)
    email_verification_ttl_hours: int = Field(default=48, ge=1, le=168)
    mfa_issuer: str = "VISiOnRoute"

    # --- Object storage (S3 / MinIO) ---
    s3_endpoint_url: str | None = None
    s3_bucket_evidence: str = "visionroute-evidence"
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_region: str = "eu-central-1"
    signed_url_ttl_seconds: int = Field(default=300, le=3600)

    # --- AI assistance (disabled by default; see ADR-0008) ---
    ai_assist_enabled: bool = False
    ai_provider: str | None = None
    ai_api_key: SecretStr | None = None
    ai_request_timeout_seconds: int = 30
    ai_max_output_tokens: int = 2048

    # --- Non-interactive bootstrap (optional; clear after first use) ---
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    # --- Rate limiting (Redis in production; memory only for local/tests) ---
    rate_limit_backend: Literal["redis", "memory"] = "memory"
    # Per (client IP, e-mail); account lockout additionally protects each account.
    login_rate_limit_per_minute: int = Field(default=10, ge=1)
    # Per client IP; generous so offices behind one NAT address are not blocked.
    login_ip_rate_limit_per_minute: int = Field(default=100, ge=1)
    register_rate_limit_per_hour: int = Field(default=20, ge=1)
    # Refresh, invitation acceptance, token verification (per client IP).
    token_rate_limit_per_minute: int = Field(default=60, ge=1)
    account_email_rate_limit_per_hour: int = Field(default=5, ge=1)
    ingest_rate_limit_per_minute: int = Field(default=6000, ge=1)

    # --- Request limits (DoS hardening; CSV import allows 10 MiB + multipart) ---
    max_request_body_bytes: int = Field(default=12 * 1024 * 1024, ge=1024)

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            msg = "database_url must use the postgresql+asyncpg:// scheme"
            raise ValueError(msg)
        return v

    def validate_for_runtime(self) -> list[str]:
        """Return human-readable problems that must block startup.

        Called by API/worker entrypoints, not at import time, so tests and
        tooling can construct Settings freely.
        """
        problems: list[str] = []
        if self.jwt_private_key_path is None or not self.jwt_private_key_path.exists():
            problems.append(
                "JWT özel anahtarı bulunamadı. Geliştirme için üretin: "
                "poetry run visionroute keys generate --out .dev/keys"
            )
        if self.jwt_public_key_path is None or not self.jwt_public_key_path.exists():
            problems.append("JWT açık anahtarı bulunamadı (VISIONROUTE_JWT_PUBLIC_KEY_PATH).")
        problems.extend(self._field_encryption_problems())
        if self.environment.is_production_like:
            if self.debug:
                problems.append("Üretim benzeri ortamda debug=true olamaz.")
            if not self.cookie_secure:
                problems.append("Üretim benzeri ortamda cookie_secure=true olmalıdır.")
            if "localhost" in self.database_url:
                problems.append("Üretim benzeri ortamda localhost veritabanı kullanılamaz.")
            if self.bootstrap_admin_password is not None:
                problems.append(
                    "Bootstrap parolası ortam değişkeninde bırakılmış; kurulumdan sonra silin."
                )
            if not self.field_encryption_keys:
                problems.append(
                    "Üretim benzeri ortamda alan şifreleme anahtarı "
                    "(VISIONROUTE_FIELD_ENCRYPTION_KEYS) zorunludur."
                )
            if self.mail_backend != "smtp":
                problems.append("Üretim benzeri ortamda e-posta arka ucu 'smtp' olmalıdır.")
            if self.mail_backend == "smtp" and self.smtp_host in ("localhost", "127.0.0.1"):
                problems.append("Üretim benzeri ortamda SMTP sunucusu localhost olamaz.")
            if self.smtp_username and self.smtp_password is None:
                problems.append("SMTP kullanıcı adı verilmiş ancak parola eksik.")
            if self.rate_limit_backend != "redis":
                problems.append("Üretim benzeri ortamda hız sınırlama arka ucu 'redis' olmalıdır.")
            if not self.public_app_url.startswith("https://"):
                problems.append("Üretim benzeri ortamda public_app_url https olmalıdır.")
        return problems

    def _field_encryption_problems(self) -> list[str]:
        if not self.field_encryption_keys:
            return []
        primary = self.resolved_primary_key_id()
        if primary is None:
            return [
                "Birden fazla alan şifreleme anahtarı var; birincil anahtar kimliği "
                "(VISIONROUTE_FIELD_ENCRYPTION_PRIMARY_KEY_ID) belirtilmelidir."
            ]
        if primary not in self.field_encryption_keys:
            return ["Birincil alan şifreleme anahtar kimliği anahtar listesinde yok."]
        return []

    def resolved_primary_key_id(self) -> str | None:
        if self.field_encryption_primary_key_id:
            return self.field_encryption_primary_key_id
        if len(self.field_encryption_keys) == 1:
            return next(iter(self.field_encryption_keys))
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
