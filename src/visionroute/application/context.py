"""Request context passed from the API layer into application services."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from visionroute.domain.permissions import Permission, RoleKey, role_has


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Who is acting, in which tenant, from where.

    ``organization_id`` is None only for platform-level actors operating
    outside a tenant (platform admins, bootstrap, system jobs).
    """

    user_id: uuid.UUID | None
    organization_id: uuid.UUID | None
    role: RoleKey | None
    is_platform_admin: bool
    actor_label: str
    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    # Authoritative account state resolved from the database per request.
    email_verified: bool = False
    mfa_enabled: bool = False

    def has_permission(self, permission: Permission) -> bool:
        if self.is_platform_admin:
            return True
        if self.role is None:
            return False
        return role_has(self.role, permission)


SYSTEM_CONTEXT = RequestContext(
    user_id=None,
    organization_id=None,
    role=None,
    is_platform_admin=False,
    actor_label="system",
)
