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

from pydantic import Field, field_validator
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

    # --- Mail ---
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "no-reply@visionroute.local"
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False

    # --- Object storage (S3 / MinIO) ---
    s3_endpoint_url: str | None = None
    s3_bucket_evidence: str = "visionroute-evidence"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "eu-central-1"
    signed_url_ttl_seconds: int = Field(default=300, le=3600)

    # --- AI assistance (disabled by default; see ADR-0008) ---
    ai_assist_enabled: bool = False
    ai_provider: str | None = None
    ai_api_key: str | None = None
    ai_request_timeout_seconds: int = 30
    ai_max_output_tokens: int = 2048

    # --- Non-interactive bootstrap (optional; clear after first use) ---
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    # --- Rate limiting ---
    login_rate_limit_per_minute: int = 10
    ingest_rate_limit_per_minute: int = 6000

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
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
