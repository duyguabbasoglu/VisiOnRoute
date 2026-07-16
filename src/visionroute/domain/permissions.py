"""Permission catalog and system role definitions (version 1).

The catalog is the authoritative source for authorization decisions and is
seeded into the ``roles`` / ``permissions`` / ``role_permissions`` tables so
reporting and the admin UI can inspect it. An integration test asserts the
database seed matches this catalog.

Deny-by-default: an action without an explicit permission check must not exist.
"""

from __future__ import annotations

from enum import StrEnum

CATALOG_VERSION = 1


class Permission(StrEnum):
    ORG_READ = "org.read"
    ORG_UPDATE = "org.update"
    ORG_MEMBERS_READ = "org.members.read"
    ORG_MEMBERS_MANAGE = "org.members.manage"
    ORG_INVITATIONS_MANAGE = "org.invitations.manage"
    ORG_RETENTION_MANAGE = "org.retention.manage"

    FLEET_READ = "fleet.read"
    FLEET_MANAGE = "fleet.manage"

    TRIPS_READ = "trips.read"
    TELEMETRY_READ = "telemetry.read"

    EVENTS_READ = "events.read"
    EVENTS_REVIEW = "events.review"
    EVIDENCE_READ = "events.evidence.read"
    EVIDENCE_RAW_MEDIA = "events.evidence.raw_media"

    RISKS_READ = "risks.read"
    RISKS_MANAGE = "risks.manage"
    GEOFENCES_MANAGE = "geofences.manage"

    COACHING_READ = "coaching.read"
    COACHING_MANAGE = "coaching.manage"

    ANALYTICS_READ = "analytics.read"
    REPORTS_READ = "reports.read"
    REPORTS_MANAGE = "reports.manage"

    NOTIFICATIONS_MANAGE = "notifications.manage"
    INTEGRATIONS_READ = "integrations.read"
    INTEGRATIONS_MANAGE = "integrations.manage"

    SUBSCRIPTION_READ = "subscription.read"
    SUBSCRIPTION_MANAGE = "subscription.manage"

    AUDIT_READ = "audit.read"


class RoleKey(StrEnum):
    """System tenant roles. Turkish display names live in ROLE_LABELS_TR."""

    OWNER = "owner"
    ADMIN = "admin"
    SAFETY_MANAGER = "safety_manager"
    FLEET_MANAGER = "fleet_manager"
    EVENT_REVIEWER = "event_reviewer"
    COACH = "coach"
    ANALYST = "analyst"
    AUDITOR = "auditor"
    INTEGRATION_MANAGER = "integration_manager"
    DRIVER = "driver"


ROLE_LABELS_TR: dict[RoleKey, str] = {
    RoleKey.OWNER: "Organizasyon Sahibi",
    RoleKey.ADMIN: "Organizasyon Yöneticisi",
    RoleKey.SAFETY_MANAGER: "Güvenlik Müdürü",
    RoleKey.FLEET_MANAGER: "Filo Yöneticisi",
    RoleKey.EVENT_REVIEWER: "Olay İnceleyici",
    RoleKey.COACH: "Sürücü Koçu",
    RoleKey.ANALYST: "Analist",
    RoleKey.AUDITOR: "Salt Okunur Denetçi",
    RoleKey.INTEGRATION_MANAGER: "Entegrasyon Yöneticisi",
    RoleKey.DRIVER: "Sürücü (Self Servis)",
}

_ALL = set(Permission)

_READ_ONLY_AUDIT = {
    Permission.ORG_READ,
    Permission.ORG_MEMBERS_READ,
    Permission.FLEET_READ,
    Permission.TRIPS_READ,
    Permission.EVENTS_READ,
    Permission.RISKS_READ,
    Permission.COACHING_READ,
    Permission.ANALYTICS_READ,
    Permission.REPORTS_READ,
    Permission.SUBSCRIPTION_READ,
    Permission.AUDIT_READ,
}

ROLE_PERMISSIONS: dict[RoleKey, frozenset[Permission]] = {
    RoleKey.OWNER: frozenset(_ALL),
    RoleKey.ADMIN: frozenset(_ALL - {Permission.SUBSCRIPTION_MANAGE}),
    RoleKey.SAFETY_MANAGER: frozenset(
        {
            Permission.ORG_READ,
            Permission.ORG_MEMBERS_READ,
            Permission.FLEET_READ,
            Permission.TRIPS_READ,
            Permission.TELEMETRY_READ,
            Permission.EVENTS_READ,
            Permission.EVENTS_REVIEW,
            Permission.EVIDENCE_READ,
            Permission.EVIDENCE_RAW_MEDIA,
            Permission.RISKS_READ,
            Permission.RISKS_MANAGE,
            Permission.GEOFENCES_MANAGE,
            Permission.COACHING_READ,
            Permission.COACHING_MANAGE,
            Permission.ANALYTICS_READ,
            Permission.REPORTS_READ,
            Permission.REPORTS_MANAGE,
            Permission.NOTIFICATIONS_MANAGE,
        }
    ),
    RoleKey.FLEET_MANAGER: frozenset(
        {
            Permission.ORG_READ,
            Permission.ORG_MEMBERS_READ,
            Permission.FLEET_READ,
            Permission.FLEET_MANAGE,
            Permission.TRIPS_READ,
            Permission.TELEMETRY_READ,
            Permission.EVENTS_READ,
            Permission.RISKS_READ,
            Permission.ANALYTICS_READ,
            Permission.REPORTS_READ,
        }
    ),
    RoleKey.EVENT_REVIEWER: frozenset(
        {
            Permission.ORG_READ,
            Permission.FLEET_READ,
            Permission.TRIPS_READ,
            Permission.EVENTS_READ,
            Permission.EVENTS_REVIEW,
            Permission.EVIDENCE_READ,
            Permission.RISKS_READ,
        }
    ),
    RoleKey.COACH: frozenset(
        {
            Permission.ORG_READ,
            Permission.FLEET_READ,
            Permission.EVENTS_READ,
            Permission.EVIDENCE_READ,
            Permission.COACHING_READ,
            Permission.COACHING_MANAGE,
            Permission.ANALYTICS_READ,
        }
    ),
    RoleKey.ANALYST: frozenset(
        {
            Permission.ORG_READ,
            Permission.FLEET_READ,
            Permission.TRIPS_READ,
            Permission.EVENTS_READ,
            Permission.RISKS_READ,
            Permission.ANALYTICS_READ,
            Permission.REPORTS_READ,
            Permission.REPORTS_MANAGE,
        }
    ),
    RoleKey.AUDITOR: frozenset(_READ_ONLY_AUDIT),
    RoleKey.INTEGRATION_MANAGER: frozenset(
        {
            Permission.ORG_READ,
            Permission.FLEET_READ,
            Permission.INTEGRATIONS_READ,
            Permission.INTEGRATIONS_MANAGE,
            Permission.NOTIFICATIONS_MANAGE,
        }
    ),
    # Drivers see only their own coaching/events through driver-scoped endpoints;
    # object-level scoping is enforced in services, not just by these flags.
    RoleKey.DRIVER: frozenset({Permission.COACHING_READ}),
}


def role_has(role: RoleKey, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]
