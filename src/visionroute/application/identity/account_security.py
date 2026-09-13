"""Account security use cases: password reset, e-mail verification, and
two-factor authentication (TOTP + recovery codes).

- Account tokens are opaque 256-bit values; only SHA-256 digests are stored.
  They are single-use and short-lived; issuing a new one invalidates older
  unused tokens of the same purpose.
- Reset requests never reveal whether an account exists.
- TOTP secrets are field-encrypted; the last accepted time step is stored so
  a code cannot be replayed; login challenges allow a bounded number of tries.
- Every security-relevant change is audit-logged and the account owner is
  notified by e-mail.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.errors import (
    DomainConflictError,
    DomainNotFoundError,
    InvalidAccountTokenError,
    InvalidMfaCodeError,
    PermissionDeniedError,
    ReauthenticationFailedError,
    ServiceNotConfiguredError,
    ValidationFailedError,
)
from visionroute.application.mail.service import MailService
from visionroute.application.ports import FieldEncryptor
from visionroute.config.settings import Settings
from visionroute.domain.passwords import password_problems
from visionroute.domain.permissions import RoleKey
from visionroute.infrastructure.db.models.identity import (
    Membership,
    MfaChallenge,
    MfaRecoveryCode,
    Session,
    User,
    UserToken,
)
from visionroute.infrastructure.security.crypto import FieldEncryptionError
from visionroute.infrastructure.security.passwords import hash_password, verify_password
from visionroute.infrastructure.security.tokens import generate_opaque_secret, hash_opaque_secret
from visionroute.infrastructure.security.totp import (
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    looks_like_totp,
    matching_time_step,
    provisioning_uri,
)

RESET_PURPOSE = "password_reset"
VERIFICATION_PURPOSE = "email_verification"
MFA_CHALLENGE_TTL = timedelta(minutes=5)
MFA_MAX_ATTEMPTS = 5
RECOVERY_CODE_COUNT = 10


class AccountSecurityService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        cipher: FieldEncryptor | None,
        mail: MailService,
    ) -> None:
        self._db = session
        self._settings = settings
        self._cipher = cipher
        self._mail = mail

    # ------------------------------------------------------------ password reset

    async def request_password_reset(self, ctx: RequestContext, *, email: str) -> None:
        """Queue a reset link if an active account exists. Callers must return
        the same response either way (no account enumeration)."""
        user = await self._user_by_email(email)
        if user is None or user.status != "active":
            return
        minutes = self._settings.password_reset_ttl_minutes
        token = await self._issue_token(ctx, user, RESET_PURPOSE, timedelta(minutes=minutes))
        await self._mail.enqueue(
            template="password_reset",
            recipient=user.email,
            context={"full_name": user.full_name, "ttl_minutes": str(minutes)},
            secret_context={"token": token},
            related=("user", str(user.id)),
        )
        await record_audit(
            self._db,
            ctx,
            action="auth.password_reset_requested",
            resource_type="user",
            resource_id=str(user.id),
        )

    async def reset_password(self, ctx: RequestContext, *, token: str, new_password: str) -> User:
        problems = password_problems(new_password)
        if problems:
            # Validated before consuming, so a weak password does not burn the link.
            raise ValidationFailedError(problems)
        record = await self._consume_token(token, RESET_PURPOSE)
        user = await self._db.get(User, record.user_id, with_for_update=True)
        if user is None or user.status != "active":
            raise InvalidAccountTokenError
        now = datetime.now(UTC)
        user.password_hash = hash_password(new_password)
        user.password_changed_at = now
        user.failed_login_count = 0
        user.locked_until = None
        await self._invalidate_tokens(user.id, RESET_PURPOSE, now)
        # Anyone holding an old session (possibly the reason for the reset) is logged out.
        await self.revoke_all_sessions(user.id, now)
        await record_audit(
            self._db,
            ctx,
            action="auth.password_reset_completed",
            resource_type="user",
            resource_id=str(user.id),
        )
        await self._notify(user, "password_changed", now)
        return user

    # ------------------------------------------------------------ e-mail verification

    async def send_email_verification(self, ctx: RequestContext, user: User) -> bool:
        if user.email_verified_at is not None:
            return False
        hours = self._settings.email_verification_ttl_hours
        token = await self._issue_token(ctx, user, VERIFICATION_PURPOSE, timedelta(hours=hours))
        await self._mail.enqueue(
            template="email_verification",
            recipient=user.email,
            context={"full_name": user.full_name, "ttl_hours": str(hours)},
            secret_context={"token": token},
            related=("user", str(user.id)),
        )
        return True

    async def resend_email_verification(self, ctx: RequestContext, *, user_id: uuid.UUID) -> bool:
        return await self.send_email_verification(ctx, await self._require_user(user_id))

    async def verify_email(self, ctx: RequestContext, *, token: str) -> User:
        record = await self._consume_token(token, VERIFICATION_PURPOSE)
        user = await self._db.get(User, record.user_id)
        if user is None:
            raise InvalidAccountTokenError
        if user.email_verified_at is None:
            user.email_verified_at = datetime.now(UTC)
            await record_audit(
                self._db,
                ctx,
                action="auth.email_verified",
                resource_type="user",
                resource_id=str(user.id),
            )
        return user

    # ------------------------------------------------------------ MFA enrollment

    async def begin_mfa_setup(
        self, ctx: RequestContext, *, user_id: uuid.UUID, password: str
    ) -> tuple[str, str]:
        """Return (secret, otpauth URI) for the authenticator app. MFA is not
        active until a valid code is confirmed."""
        user = await self._require_user(user_id)
        self._reauthenticate(user, password)
        if user.mfa_enabled_at is not None:
            raise DomainConflictError("İki adımlı doğrulama zaten etkin.")
        secret = generate_totp_secret()
        user.mfa_pending_secret_enc = self._require_cipher().encrypt(secret)
        await record_audit(
            self._db,
            ctx,
            action="auth.mfa_setup_started",
            resource_type="user",
            resource_id=str(user.id),
        )
        uri = provisioning_uri(secret, account=user.email, issuer=self._settings.mfa_issuer)
        return secret, uri

    async def confirm_mfa(self, ctx: RequestContext, *, user_id: uuid.UUID, code: str) -> list[str]:
        user = await self._require_user(user_id, for_update=True)
        if user.mfa_enabled_at is not None:
            raise DomainConflictError("İki adımlı doğrulama zaten etkin.")
        if user.mfa_pending_secret_enc is None:
            raise DomainConflictError("Önce iki adımlı doğrulama kurulumunu başlatın.")
        secret = self._decrypt(user.mfa_pending_secret_enc)
        step = matching_time_step(secret, code)
        if step is None:
            raise InvalidMfaCodeError
        now = datetime.now(UTC)
        user.mfa_totp_secret_enc = user.mfa_pending_secret_enc
        user.mfa_pending_secret_enc = None
        user.mfa_enabled_at = now
        user.mfa_last_used_step = step
        codes = await self._replace_recovery_codes(user.id)
        await record_audit(
            self._db, ctx, action="auth.mfa_enabled", resource_type="user", resource_id=str(user.id)
        )
        await self._notify(user, "mfa_enabled", now)
        return codes

    async def disable_mfa(
        self, ctx: RequestContext, *, user_id: uuid.UUID, password: str, code: str
    ) -> None:
        user = await self._require_user(user_id, for_update=True)
        self._reauthenticate(user, password)
        if user.mfa_enabled_at is None:
            raise DomainConflictError("İki adımlı doğrulama zaten kapalı.")
        now = datetime.now(UTC)
        await self._verify_second_factor(ctx, user, submitted=code, now=now)
        self._clear_mfa(user)
        await self._db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
        await record_audit(
            self._db,
            ctx,
            action="auth.mfa_disabled",
            resource_type="user",
            resource_id=str(user.id),
        )
        await self._notify(user, "mfa_disabled", now)

    async def regenerate_recovery_codes(
        self, ctx: RequestContext, *, user_id: uuid.UUID, password: str, code: str
    ) -> list[str]:
        user = await self._require_user(user_id, for_update=True)
        self._reauthenticate(user, password)
        if user.mfa_enabled_at is None:
            raise DomainConflictError("Önce iki adımlı doğrulamayı etkinleştirin.")
        now = datetime.now(UTC)
        await self._verify_second_factor(ctx, user, submitted=code, now=now)
        codes = await self._replace_recovery_codes(user.id)
        await record_audit(
            self._db,
            ctx,
            action="auth.mfa_recovery_codes_regenerated",
            resource_type="user",
            resource_id=str(user.id),
        )
        await self._notify(user, "recovery_codes_regenerated", now)
        return codes

    # ------------------------------------------------------------ MFA login

    async def create_mfa_challenge(self, ctx: RequestContext, user: User) -> tuple[str, int]:
        cleartext, digest = generate_opaque_secret("vrm")
        self._db.add(
            MfaChallenge(
                user_id=user.id,
                token_hash=digest,
                expires_at=datetime.now(UTC) + MFA_CHALLENGE_TTL,
                ip_address=ctx.ip_address,
            )
        )
        await self._db.flush()
        return cleartext, int(MFA_CHALLENGE_TTL.total_seconds())

    async def verify_mfa_challenge(
        self,
        ctx: RequestContext,
        *,
        token: str,
        code: str | None,
        recovery_code: str | None,
    ) -> User:
        challenge = (
            await self._db.execute(
                select(MfaChallenge)
                .where(MfaChallenge.token_hash == hash_opaque_secret(token))
                .with_for_update()
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if (
            challenge is None
            or challenge.consumed_at is not None
            or challenge.expires_at <= now
            or challenge.attempts >= MFA_MAX_ATTEMPTS
        ):
            raise InvalidMfaCodeError
        user = await self._db.get(User, challenge.user_id, with_for_update=True)
        if user is None or user.status != "active" or user.mfa_enabled_at is None:
            raise InvalidMfaCodeError
        submitted = code or recovery_code or ""
        try:
            await self._verify_second_factor(ctx, user, submitted=submitted, now=now)
        except InvalidMfaCodeError:
            challenge.attempts += 1
            await record_audit(
                self._db,
                ctx,
                action="auth.mfa_challenge_failed",
                resource_type="user",
                resource_id=str(user.id),
            )
            # The attempt counter is a security control: it must survive the
            # error-path rollback of the request transaction.
            await self._db.commit()
            raise
        challenge.consumed_at = now
        return user

    # ------------------------------------------------------------ administration

    async def admin_reset_mfa(self, ctx: RequestContext, *, membership_id: uuid.UUID) -> User:
        """Organization owner resets a member's MFA (lost device).

        Runs on an RLS-bypass session on purpose: the "member of other
        organizations" check must see memberships outside the caller's tenant.
        MFA is account-wide, so one tenant must not weaken a user's security in
        another tenant; such cases go to platform support.
        """
        if ctx.organization_id is None:
            raise DomainNotFoundError("Organizasyon bağlamı bulunamadı.")
        membership = (
            await self._db.execute(
                select(Membership).where(
                    Membership.id == membership_id,
                    Membership.organization_id == ctx.organization_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise DomainNotFoundError("Üyelik bulunamadı.")
        if not ctx.is_platform_admin and ctx.role != RoleKey.OWNER:
            raise PermissionDeniedError
        if membership.user_id == ctx.user_id:
            raise DomainConflictError(
                "Kendi iki adımlı doğrulamanızı bu ekrandan sıfırlayamazsınız."
            )
        other_memberships = (
            await self._db.execute(
                select(func.count()).where(
                    Membership.user_id == membership.user_id,
                    Membership.organization_id != ctx.organization_id,
                )
            )
        ).scalar_one()
        if int(other_memberships) > 0:
            raise DomainConflictError(
                "Kullanıcı başka organizasyonlara da üye; iki adımlı doğrulama sıfırlaması "
                "için platform desteğine başvurun."
            )
        user = await self._require_user(membership.user_id, for_update=True)
        if user.mfa_enabled_at is None:
            raise DomainConflictError("Kullanıcının iki adımlı doğrulaması etkin değil.")
        now = datetime.now(UTC)
        self._clear_mfa(user)
        await self._db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
        await self.revoke_all_sessions(user.id, now)
        await record_audit(
            self._db,
            ctx,
            action="auth.mfa_reset_by_admin",
            resource_type="user",
            resource_id=str(user.id),
            organization_id=ctx.organization_id,
        )
        await self._notify(user, "mfa_reset", now)
        return user

    async def revoke_all_sessions(self, user_id: uuid.UUID, now: datetime) -> None:
        """Revoke refresh sessions and invalidate already-issued access tokens."""
        await self._db.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await self._db.execute(
            update(User).where(User.id == user_id).values(sessions_revoked_at=now)
        )

    # ------------------------------------------------------------ internals

    async def _verify_second_factor(
        self, ctx: RequestContext, user: User, *, submitted: str, now: datetime
    ) -> str:
        if not submitted:
            raise InvalidMfaCodeError
        if looks_like_totp(submitted):
            if user.mfa_totp_secret_enc is None:
                raise InvalidMfaCodeError
            step = matching_time_step(self._decrypt(user.mfa_totp_secret_enc), submitted, now=now)
            if step is None or (
                user.mfa_last_used_step is not None and step <= user.mfa_last_used_step
            ):
                raise InvalidMfaCodeError
            user.mfa_last_used_step = step
            return "totp"
        row = (
            await self._db.execute(
                select(MfaRecoveryCode)
                .where(
                    MfaRecoveryCode.user_id == user.id,
                    MfaRecoveryCode.code_hash == hash_recovery_code(submitted),
                    MfaRecoveryCode.used_at.is_(None),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise InvalidMfaCodeError
        row.used_at = now
        await record_audit(
            self._db,
            ctx,
            action="auth.mfa_recovery_code_used",
            resource_type="user",
            resource_id=str(user.id),
        )
        await self._notify(user, "mfa_recovery_code_used", now)
        return "recovery"

    async def _replace_recovery_codes(self, user_id: uuid.UUID) -> list[str]:
        await self._db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id))
        codes = generate_recovery_codes(RECOVERY_CODE_COUNT)
        for code in codes:
            self._db.add(MfaRecoveryCode(user_id=user_id, code_hash=hash_recovery_code(code)))
        await self._db.flush()
        return codes

    async def _issue_token(
        self, ctx: RequestContext, user: User, purpose: str, ttl: timedelta
    ) -> str:
        now = datetime.now(UTC)
        await self._invalidate_tokens(user.id, purpose, now)
        cleartext, digest = generate_opaque_secret("vra")
        self._db.add(
            UserToken(
                user_id=user.id,
                purpose=purpose,
                token_hash=digest,
                expires_at=now + ttl,
                requested_ip=ctx.ip_address,
            )
        )
        await self._db.flush()
        return cleartext

    async def _invalidate_tokens(self, user_id: uuid.UUID, purpose: str, now: datetime) -> None:
        await self._db.execute(
            update(UserToken)
            .where(
                UserToken.user_id == user_id,
                UserToken.purpose == purpose,
                UserToken.used_at.is_(None),
            )
            .values(used_at=now)
        )

    async def _consume_token(self, token: str, purpose: str) -> UserToken:
        record = (
            await self._db.execute(
                select(UserToken)
                .where(
                    UserToken.token_hash == hash_opaque_secret(token),
                    UserToken.purpose == purpose,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if record is None or record.used_at is not None or record.expires_at <= now:
            raise InvalidAccountTokenError
        record.used_at = now
        return record

    async def _notify(self, user: User, event: str, now: datetime) -> None:
        await self._mail.enqueue(
            template="security_notice",
            recipient=user.email,
            context={"full_name": user.full_name, "event": event, "occurred_at": now.isoformat()},
            related=("user", str(user.id)),
        )

    async def _user_by_email(self, email: str) -> User | None:
        return (
            await self._db.execute(
                select(User).where(func.lower(User.email) == email.strip().lower())
            )
        ).scalar_one_or_none()

    async def _require_user(self, user_id: uuid.UUID, *, for_update: bool = False) -> User:
        user = await self._db.get(User, user_id, with_for_update=for_update)
        if user is None or user.status != "active":
            raise DomainNotFoundError("Kullanıcı bulunamadı.")
        return user

    def _reauthenticate(self, user: User, password: str) -> None:
        if not verify_password(user.password_hash, password):
            raise ReauthenticationFailedError

    def _require_cipher(self) -> FieldEncryptor:
        if self._cipher is None:
            raise ServiceNotConfiguredError(
                "İki adımlı doğrulama için alan şifreleme anahtarı yapılandırılmamış."
            )
        return self._cipher

    def _decrypt(self, value: str) -> str:
        try:
            return self._require_cipher().decrypt(value)
        except FieldEncryptionError as exc:
            raise ServiceNotConfiguredError(
                "İki adımlı doğrulama sırrı çözülemedi; sistem yöneticisine başvurun."
            ) from exc

    @staticmethod
    def _clear_mfa(user: User) -> None:
        user.mfa_totp_secret_enc = None
        user.mfa_pending_secret_enc = None
        user.mfa_enabled_at = None
        user.mfa_last_used_step = None
