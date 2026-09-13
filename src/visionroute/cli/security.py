"""Security maintenance: re-encrypt field-encrypted columns after key rotation."""

from __future__ import annotations

from sqlalchemy import select

from visionroute.config.settings import get_settings
from visionroute.infrastructure.db.engine import build_engine, build_session_factory, session_scope
from visionroute.infrastructure.db.models.notifications import WebhookEndpoint
from visionroute.infrastructure.db.tenancy import set_rls_bypass
from visionroute.infrastructure.security.crypto import FieldEncryptionError, build_field_cipher


async def reencrypt_all() -> dict[str, int]:
    """Rewrite every encrypted value not under the primary key. Idempotent."""
    settings = get_settings()
    cipher = build_field_cipher(settings)
    if cipher is None:
        msg = "Alan şifreleme anahtarları yapılandırılmamış."
        raise FieldEncryptionError(msg)
    engine = build_engine(settings)
    counts: dict[str, int] = {"webhook_endpoints.secret_enc": 0}
    try:
        async with session_scope(build_session_factory(engine)) as db:
            await set_rls_bypass(db)
            for endpoint in (await db.execute(select(WebhookEndpoint))).scalars():
                if cipher.needs_rotation(endpoint.secret_enc):
                    endpoint.secret_enc = cipher.rotate(endpoint.secret_enc)
                    counts["webhook_endpoints.secret_enc"] += 1
    finally:
        await engine.dispose()
    return counts
