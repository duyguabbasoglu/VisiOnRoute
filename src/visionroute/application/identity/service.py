"""Identity & tenancy use cases: registration, authentication, sessions, invitations.

All methods expect a session whose tenancy context has already been set by
the caller (API dependency or CLI). Auth flows run with RLS bypass because
they resolve the tenant; tenant-scoped member management runs under RLS.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.audit import record_audit
from visionroute.application.context import RequestContext
from visionroute.application.errors import (
    AccountLockedError,
    DomainConflictError,
    DomainNotFoundError,
    InvalidCredentialsError,
    ServiceNotConfiguredError,
    ValidationFailedError,
)
from visionroute.application.mail.service import MailService
from visionroute.application.outbox import publish_event
from visionroute.domain.ids import uuid7
from visionroute.domain.passwords import password_problems
from visionroute.domain.permissions import ROLE_LABELS_TR, RoleKey
from visionroute.infrastructure.db.models.identity import (
    Invitation,
    Membership,
    Organization,
    OrganizationSettings,
    Session,
    User,
)
from visionroute.infrastructure.security.passwords import hash_password, verify_password
from visionroute.infrastructure.security.tokens import (
    generate_opaque_secret,
    hash_opaque_secret,
)

_MAX_FAILED_LOGINS = 10
_LOCKOUT = timedelta(minutes=15)
# Verified for unknown accounts so response timing does not reveal whether an
# e-mail address is registered (the Argon2 check dominates login latency).
_TIMING_EQUALIZER_HASH = hash_password("zamanlama-dengeleyici-gercek-parola-degil")


@dataclass(frozen=True)
class AuthenticatedUser:
    user: User
    membership: Membership | None
    refresh_token_cleartext: str
    session_id: uuid.UUID


@dataclass(frozen=True)
class InvitationPreview:
    organization_name: str
    email: str
    role_key: str
    expires_at: datetime
    account_exists: bool


class IdentityService:
    def __init__(
        self,
        session: AsyncSession,
        refresh_ttl_seconds: int,
        *,
        mail: MailService | None = None,
        invitation_ttl_days: int = 7,
    ) -> None:
        self._db = session
        self._refresh_ttl = timedelta(seconds=refresh_ttl_seconds)
        self._mail = mail
        self._invitation_ttl = timedelta(days=invitation_ttl_days)

    # ---------------------------------------------------------------- users

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self._db.execute(
            select(User).where(func.lower(User.email) == email.strip().lower())
        )
        return result.scalar_one_or_none()

    async def get_active_membership(self, user_id: uuid.UUID) -> Membership | None:
        result = await self._db.execute(
            select(Membership)
            .where(Membership.user_id == user_id, Membership.status == "active")
            .order_by(Membership.created_at)
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ---------------------------------------------------------------- signup

    async def register_organization(
        self,
        ctx: RequestContext,
        *,
        organization_name: str,
        slug: str,
        owner_email: str,
        owner_full_name: str,
        owner_password: str,
    ) -> tuple[Organization, User, Membership]:
        problems = password_problems(owner_password)
        if problems:
            raise ValidationFailedError(problems)

        existing_org = await self._db.execute(select(Organization).where(Organization.slug == slug))
        if existing_org.scalar_one_or_none() is not None:
            raise DomainConflictError("Bu kısa ad (slug) zaten kullanımda.")
        if await self.get_user_by_email(owner_email) is not None:
            raise DomainConflictError("Bu e-posta adresiyle bir hesap zaten var.")

        organization = Organization(name=organization_name, slug=slug)
        self._db.add(organization)
        self._db.add(OrganizationSettings(organization=organization))
        user = User(
            email=owner_email.strip().lower(),
            password_hash=hash_password(owner_password),
            full_name=owner_full_name,
        )
        self._db.add(user)
        await self._db.flush()
        membership = Membership(
            user_id=user.id,
            organization_id=organization.id,
            role_key=RoleKey.OWNER.value,
        )
        self._db.add(membership)
        await self._db.flush()
        await record_audit(
            self._db,
            ctx,
            action="organization.registered",
            resource_type="organization",
            resource_id=str(organization.id),
            data={"slug": slug},
            organization_id=organization.id,
        )
        from visionroute.application.saas.service import SubscriptionService

        await SubscriptionService(self._db).start_trial(organization.id)
        await publish_event(
            self._db,
            aggregate_type="organization",
            aggregate_id=str(organization.id),
            event_type="organization.registered",
            payload={"organization_id": str(organization.id)},
        )
        return organization, user, membership

    # ---------------------------------------------------------------- login

    async def authenticate(
        self, ctx: RequestContext, *, email: str, password: str
    ) -> tuple[User, Membership | None]:
        """Verify e-mail and password (lockout-aware). Does not start a session:
        the caller decides whether a second factor is required first."""
        user = await self.get_user_by_email(email)
        if user is None or user.status != "active":
            verify_password(_TIMING_EQUALIZER_HASH, password)
            # Uniform error: do not reveal whether the account exists.
            raise InvalidCredentialsError

        now = datetime.now(UTC)
        if user.locked_until is not None and user.locked_until > now:
            raise AccountLockedError

        if not verify_password(user.password_hash, password):
            user.failed_login_count += 1
            if user.failed_login_count >= _MAX_FAILED_LOGINS:
                user.locked_until = now + _LOCKOUT
                user.failed_login_count = 0
                await record_audit(
                    self._db,
                    ctx,
                    action="auth.account_locked",
                    resource_type="user",
                    resource_id=str(user.id),
                )
            # The raised error rolls the request transaction back; the failed
            # attempt counter is a security control and must survive it.
            await self._db.commit()
            raise InvalidCredentialsError

        user.failed_login_count = 0
        user.locked_until = None
        return user, await self.get_active_membership(user.id)

    async def start_session(
        self, ctx: RequestContext, user: User, membership: Membership | None
    ) -> AuthenticatedUser:
        now = datetime.now(UTC)
        cleartext, digest = generate_opaque_secret("vrt")
        session = Session(
            user_id=user.id,
            organization_id=membership.organization_id if membership else None,
            family_id=uuid7(),
            refresh_token_hash=digest,
            user_agent=(ctx.user_agent or "")[:400] or None,
            ip_address=ctx.ip_address,
            expires_at=now + self._refresh_ttl,
            last_used_at=now,
        )
        self._db.add(session)
        await self._db.flush()
        await record_audit(
            self._db,
            ctx,
            action="auth.login",
            resource_type="user",
            resource_id=str(user.id),
            organization_id=membership.organization_id if membership else None,
        )
        return AuthenticatedUser(
            user=user,
            membership=membership,
            refresh_token_cleartext=cleartext,
            session_id=session.id,
        )

    # ---------------------------------------------------------------- refresh

    async def rotate_refresh_token(
        self, ctx: RequestContext, *, refresh_token: str
    ) -> AuthenticatedUser:
        digest = hash_opaque_secret(refresh_token)
        result = await self._db.execute(select(Session).where(Session.refresh_token_hash == digest))
        session = result.scalar_one_or_none()
        now = datetime.now(UTC)

        if session is None:
            raise InvalidCredentialsError

        if session.revoked_at is not None:
            # Reuse of a rotated/revoked token → assume theft, kill the family.
            await self._revoke_family(session.family_id, reuse=True)
            await record_audit(
                self._db,
                ctx,
                action="auth.refresh_reuse_detected",
                resource_type="session",
                resource_id=str(session.id),
                organization_id=session.organization_id,
            )
            # Family revocation must survive the error-path rollback.
            await self._db.commit()
            raise InvalidCredentialsError

        if session.expires_at <= now:
            raise InvalidCredentialsError

        user = await self._db.get(User, session.user_id)
        if user is None or user.status != "active":
            raise InvalidCredentialsError

        session.revoked_at = now
        cleartext, new_digest = generate_opaque_secret("vrt")
        new_session = Session(
            user_id=user.id,
            organization_id=session.organization_id,
            family_id=session.family_id,
            refresh_token_hash=new_digest,
            user_agent=session.user_agent,
            ip_address=ctx.ip_address or session.ip_address,
            expires_at=now + self._refresh_ttl,
            last_used_at=now,
        )
        self._db.add(new_session)
        await self._db.flush()
        membership = await self.get_active_membership(user.id)
        return AuthenticatedUser(
            user=user,
            membership=membership,
            refresh_token_cleartext=cleartext,
            session_id=new_session.id,
        )

    async def _revoke_family(self, family_id: uuid.UUID, *, reuse: bool) -> None:
        now = datetime.now(UTC)
        result = await self._db.execute(
            select(Session).where(Session.family_id == family_id, Session.revoked_at.is_(None))
        )
        for open_session in result.scalars():
            open_session.revoked_at = now
            if reuse:
                open_session.reuse_detected_at = now

    async def logout(self, ctx: RequestContext, *, refresh_token: str) -> None:
        digest = hash_opaque_secret(refresh_token)
        result = await self._db.execute(select(Session).where(Session.refresh_token_hash == digest))
        session = result.scalar_one_or_none()
        if session is not None:
            await self._revoke_family(session.family_id, reuse=False)
            await record_audit(
                self._db,
                ctx,
                action="auth.logout",
                resource_type="session",
                resource_id=str(session.id),
            )

    # ---------------------------------------------------------------- invitations

    async def create_invitation(
        self, ctx: RequestContext, *, email: str, role_key: RoleKey
    ) -> Invitation:
        """Create an invitation and queue its e-mail. The one-time token is only
        ever delivered to the invitee's mailbox, never returned to the caller."""
        if ctx.organization_id is None:
            raise DomainNotFoundError("Organizasyon bağlamı bulunamadı.")
        if role_key == RoleKey.OWNER:
            raise ValidationFailedError(["Sahiplik davetle devredilemez."])
        from visionroute.application.saas.service import SubscriptionService

        await SubscriptionService(self._db).enforce_user_limit(ctx.organization_id)

        normalized = email.strip().lower()
        existing_user = await self.get_user_by_email(normalized)
        if existing_user is not None:
            member = await self._db.execute(
                select(Membership).where(
                    Membership.user_id == existing_user.id,
                    Membership.organization_id == ctx.organization_id,
                )
            )
            if member.scalar_one_or_none() is not None:
                raise DomainConflictError("Bu kullanıcı zaten organizasyon üyesi.")

        now = datetime.now(UTC)
        pending = await self._db.execute(
            select(Invitation.id).where(
                Invitation.organization_id == ctx.organization_id,
                func.lower(Invitation.email) == normalized,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.expires_at > now,
            )
        )
        if pending.first() is not None:
            raise DomainConflictError(
                "Bu e-posta adresine gönderilmiş bekleyen bir davet var; "
                "davet listesinden yeniden gönderebilirsiniz."
            )

        token, digest = generate_opaque_secret("vri")
        invitation = Invitation(
            organization_id=ctx.organization_id,
            email=normalized,
            role_key=role_key.value,
            token_hash=digest,
            invited_by_user_id=ctx.user_id,
            expires_at=now + self._invitation_ttl,
        )
        self._db.add(invitation)
        await self._db.flush()
        await self._send_invitation(ctx, invitation, token)
        await record_audit(
            self._db,
            ctx,
            action="invitation.created",
            resource_type="invitation",
            resource_id=str(invitation.id),
            data={"email": invitation.email, "role": role_key.value},
        )
        await publish_event(
            self._db,
            aggregate_type="invitation",
            aggregate_id=str(invitation.id),
            event_type="invitation.created",
            payload={
                "invitation_id": str(invitation.id),
                "organization_id": str(ctx.organization_id),
            },
        )
        return invitation

    async def resend_invitation(self, ctx: RequestContext, invitation_id: uuid.UUID) -> Invitation:
        """Rotate the token (the previous link stops working), extend the
        expiry and queue a new e-mail."""
        invitation = await self._tenant_invitation(ctx, invitation_id)
        if invitation.accepted_at is not None or invitation.revoked_at is not None:
            raise DomainConflictError(
                "Kabul edilmiş veya iptal edilmiş davet yeniden gönderilemez."
            )
        token, digest = generate_opaque_secret("vri")
        invitation.token_hash = digest
        invitation.expires_at = datetime.now(UTC) + self._invitation_ttl
        await self._send_invitation(ctx, invitation, token)
        await record_audit(
            self._db,
            ctx,
            action="invitation.resent",
            resource_type="invitation",
            resource_id=str(invitation.id),
        )
        return invitation

    async def revoke_invitation(self, ctx: RequestContext, invitation_id: uuid.UUID) -> Invitation:
        invitation = await self._tenant_invitation(ctx, invitation_id)
        if invitation.accepted_at is not None:
            raise DomainConflictError("Kabul edilmiş davet iptal edilemez; üyeliği kaldırın.")
        if invitation.revoked_at is None:
            invitation.revoked_at = datetime.now(UTC)
            await record_audit(
                self._db,
                ctx,
                action="invitation.revoked",
                resource_type="invitation",
                resource_id=str(invitation.id),
            )
        return invitation

    async def preview_invitation(self, *, token: str) -> InvitationPreview:
        invitation = await self._open_invitation_by_token(token)
        organization = await self._db.get(Organization, invitation.organization_id)
        return InvitationPreview(
            organization_name=organization.name if organization else "",
            email=invitation.email,
            role_key=invitation.role_key,
            expires_at=invitation.expires_at,
            account_exists=await self.get_user_by_email(invitation.email) is not None,
        )

    async def accept_invitation(
        self,
        ctx: RequestContext,
        *,
        token: str,
        full_name: str | None,
        password: str | None,
    ) -> tuple[User, Membership]:
        invitation = await self._open_invitation_by_token(token, for_update=True)
        now = datetime.now(UTC)
        from visionroute.application.saas.service import SubscriptionService

        # Re-checked at acceptance: many pending invitations must not exceed the plan.
        await SubscriptionService(self._db).enforce_user_limit(invitation.organization_id)

        user = await self.get_user_by_email(invitation.email)
        if user is None:
            if not full_name or not password:
                raise ValidationFailedError(["Yeni hesap için ad soyad ve parola gereklidir."])
            problems = password_problems(password)
            if problems:
                raise ValidationFailedError(problems)
            user = User(
                email=invitation.email,
                password_hash=hash_password(password),
                full_name=full_name,
                email_verified_at=now,  # the invitation link proves mailbox access
            )
            self._db.add(user)
            await self._db.flush()
        else:
            existing = await self._db.execute(
                select(Membership.id).where(
                    Membership.user_id == user.id,
                    Membership.organization_id == invitation.organization_id,
                )
            )
            if existing.first() is not None:
                raise DomainConflictError("Bu kullanıcı zaten organizasyon üyesi.")
            if user.email_verified_at is None:
                user.email_verified_at = now

        membership = Membership(
            user_id=user.id,
            organization_id=invitation.organization_id,
            role_key=invitation.role_key,
        )
        self._db.add(membership)
        invitation.accepted_at = now
        await self._db.flush()
        await record_audit(
            self._db,
            ctx,
            action="invitation.accepted",
            resource_type="invitation",
            resource_id=str(invitation.id),
            data={"user_id": str(user.id)},
            organization_id=invitation.organization_id,
        )
        return user, membership

    async def _open_invitation_by_token(
        self, token: str, *, for_update: bool = False
    ) -> Invitation:
        stmt = select(Invitation).where(Invitation.token_hash == hash_opaque_secret(token))
        if for_update:
            stmt = stmt.with_for_update()
        invitation = (await self._db.execute(stmt)).scalar_one_or_none()
        now = datetime.now(UTC)
        if (
            invitation is None
            or invitation.accepted_at is not None
            or invitation.revoked_at is not None
            or invitation.expires_at <= now
        ):
            raise DomainNotFoundError("Davet bulunamadı, iptal edilmiş veya süresi dolmuş.")
        return invitation

    async def _tenant_invitation(self, ctx: RequestContext, invitation_id: uuid.UUID) -> Invitation:
        invitation = await self._db.get(Invitation, invitation_id)
        if invitation is None or invitation.organization_id != ctx.organization_id:
            raise DomainNotFoundError("Davet bulunamadı.")
        return invitation

    async def _send_invitation(
        self, ctx: RequestContext, invitation: Invitation, token: str
    ) -> None:
        if self._mail is None:
            raise ServiceNotConfiguredError("E-posta gönderimi yapılandırılmamış.")
        organization = await self._db.get(Organization, invitation.organization_id)
        inviter = await self._db.get(User, ctx.user_id) if ctx.user_id else None
        role_label = ROLE_LABELS_TR.get(RoleKey(invitation.role_key), invitation.role_key)
        await self._mail.enqueue(
            template="invitation",
            recipient=invitation.email,
            context={
                "organization_name": organization.name if organization else "VISiOnRoute",
                "inviter_name": inviter.full_name if inviter else "Organizasyon yöneticiniz",
                "role_label": role_label,
                "expires_at": invitation.expires_at.isoformat(),
            },
            secret_context={"token": token},
            organization_id=invitation.organization_id,
            related=("invitation", str(invitation.id)),
            idempotency_key=f"invitation:{invitation.id}:{invitation.token_hash[:24]}",
        )
        invitation.last_sent_at = datetime.now(UTC)
