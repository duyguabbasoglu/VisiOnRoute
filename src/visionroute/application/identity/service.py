"""Identity & tenancy use cases.

All methods expect a session whose tenancy context has already been set by
the caller (API dependency or CLI). Auth flows run with RLS bypass because
they resolve the tenant; tenant-scoped member management runs under RLS.
"""

from __future__ import annotations

import secrets
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
    ValidationFailedError,
)
from visionroute.application.outbox import publish_event
from visionroute.domain.ids import uuid7
from visionroute.domain.passwords import password_problems
from visionroute.domain.permissions import RoleKey
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
_INVITATION_TTL = timedelta(days=7)


@dataclass(frozen=True)
class AuthenticatedUser:
    user: User
    membership: Membership | None
    refresh_token_cleartext: str
    session_id: uuid.UUID


class IdentityService:
    def __init__(self, session: AsyncSession, refresh_ttl_seconds: int) -> None:
        self._db = session
        self._refresh_ttl = timedelta(seconds=refresh_ttl_seconds)

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
    ) -> tuple[Organization, User]:
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
        self._db.add(
            Membership(
                user_id=user.id,
                organization_id=organization.id,
                role_key=RoleKey.OWNER.value,
            )
        )
        await record_audit(
            self._db,
            ctx,
            action="organization.registered",
            resource_type="organization",
            resource_id=str(organization.id),
            data={"slug": slug},
            organization_id=organization.id,
        )
        await publish_event(
            self._db,
            aggregate_type="organization",
            aggregate_id=str(organization.id),
            event_type="organization.registered",
            payload={"organization_id": str(organization.id), "owner_email": user.email},
        )
        return organization, user

    # ---------------------------------------------------------------- login

    async def login(
        self,
        ctx: RequestContext,
        *,
        email: str,
        password: str,
    ) -> AuthenticatedUser:
        user = await self.get_user_by_email(email)
        if user is None or user.status != "active":
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
        membership = await self.get_active_membership(user.id)

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
    ) -> tuple[Invitation, str]:
        if ctx.organization_id is None:
            raise DomainNotFoundError("Organizasyon bağlamı bulunamadı.")
        if role_key == RoleKey.OWNER:
            raise ValidationFailedError(["Sahiplik davetle devredilemez."])

        existing_user = await self.get_user_by_email(email)
        if existing_user is not None:
            member = await self._db.execute(
                select(Membership).where(
                    Membership.user_id == existing_user.id,
                    Membership.organization_id == ctx.organization_id,
                )
            )
            if member.scalar_one_or_none() is not None:
                raise DomainConflictError("Bu kullanıcı zaten organizasyon üyesi.")

        token = secrets.token_urlsafe(32)
        invitation = Invitation(
            organization_id=ctx.organization_id,
            email=email.strip().lower(),
            role_key=role_key.value,
            token_hash=hash_opaque_secret(token),
            invited_by_user_id=ctx.user_id,
            expires_at=datetime.now(UTC) + _INVITATION_TTL,
        )
        self._db.add(invitation)
        await self._db.flush()
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
                "email": invitation.email,
            },
        )
        return invitation, token

    async def accept_invitation(
        self,
        ctx: RequestContext,
        *,
        token: str,
        full_name: str | None,
        password: str | None,
    ) -> tuple[User, Membership]:
        digest = hash_opaque_secret(token)
        result = await self._db.execute(select(Invitation).where(Invitation.token_hash == digest))
        invitation = result.scalar_one_or_none()
        now = datetime.now(UTC)
        if invitation is None or invitation.accepted_at is not None or invitation.expires_at <= now:
            raise DomainNotFoundError("Davet bulunamadı veya süresi dolmuş.")

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
                email_verified_at=now,  # invitation itself proves mailbox access
            )
            self._db.add(user)
            await self._db.flush()

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
        )
        return user, membership
