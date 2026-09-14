/**
 * Mirror of the backend permission catalog (visionroute.domain.permissions).
 * Used ONLY to hide controls a user cannot use; every action is still
 * authorized by the API (deny-by-default, AGENTS.md rule 4).
 */
import type { SessionUser } from "./schemas";

export type Permission =
  | "org.read"
  | "org.update"
  | "org.members.read"
  | "org.members.manage"
  | "org.invitations.manage"
  | "org.retention.manage"
  | "fleet.read"
  | "fleet.manage"
  | "trips.read"
  | "telemetry.read"
  | "events.read"
  | "events.review"
  | "events.evidence.read"
  | "events.evidence.raw_media"
  | "risks.read"
  | "risks.manage"
  | "geofences.manage"
  | "coaching.read"
  | "coaching.manage"
  | "analytics.read"
  | "reports.read"
  | "reports.manage"
  | "notifications.manage"
  | "integrations.read"
  | "integrations.manage"
  | "subscription.read"
  | "subscription.manage"
  | "audit.read";

const ALL: Permission[] = [
  "org.read",
  "org.update",
  "org.members.read",
  "org.members.manage",
  "org.invitations.manage",
  "org.retention.manage",
  "fleet.read",
  "fleet.manage",
  "trips.read",
  "telemetry.read",
  "events.read",
  "events.review",
  "events.evidence.read",
  "events.evidence.raw_media",
  "risks.read",
  "risks.manage",
  "geofences.manage",
  "coaching.read",
  "coaching.manage",
  "analytics.read",
  "reports.read",
  "reports.manage",
  "notifications.manage",
  "integrations.read",
  "integrations.manage",
  "subscription.read",
  "subscription.manage",
  "audit.read",
];

export const ROLE_PERMISSIONS: Record<string, readonly Permission[]> = {
  owner: ALL,
  admin: ALL.filter((p) => p !== "subscription.manage"),
  safety_manager: [
    "org.read",
    "org.members.read",
    "fleet.read",
    "trips.read",
    "telemetry.read",
    "events.read",
    "events.review",
    "events.evidence.read",
    "events.evidence.raw_media",
    "risks.read",
    "risks.manage",
    "geofences.manage",
    "coaching.read",
    "coaching.manage",
    "analytics.read",
    "reports.read",
    "reports.manage",
    "notifications.manage",
  ],
  fleet_manager: [
    "org.read",
    "org.members.read",
    "fleet.read",
    "fleet.manage",
    "trips.read",
    "telemetry.read",
    "events.read",
    "risks.read",
    "analytics.read",
    "reports.read",
  ],
  event_reviewer: [
    "org.read",
    "fleet.read",
    "trips.read",
    "events.read",
    "events.review",
    "events.evidence.read",
    "risks.read",
  ],
  coach: [
    "org.read",
    "fleet.read",
    "events.read",
    "events.evidence.read",
    "coaching.read",
    "coaching.manage",
    "analytics.read",
  ],
  analyst: [
    "org.read",
    "fleet.read",
    "trips.read",
    "events.read",
    "risks.read",
    "analytics.read",
    "reports.read",
    "reports.manage",
  ],
  auditor: [
    "org.read",
    "org.members.read",
    "fleet.read",
    "trips.read",
    "events.read",
    "risks.read",
    "coaching.read",
    "analytics.read",
    "reports.read",
    "subscription.read",
    "audit.read",
  ],
  integration_manager: [
    "org.read",
    "fleet.read",
    "integrations.read",
    "integrations.manage",
    "notifications.manage",
  ],
  driver: ["coaching.read"],
};

/** Roles an organization can assign through invitations (owner is never delegated). */
export const INVITABLE_ROLES: { value: string; label: string }[] = [
  { value: "admin", label: "Organizasyon Yöneticisi" },
  { value: "safety_manager", label: "Güvenlik Müdürü" },
  { value: "fleet_manager", label: "Filo Yöneticisi" },
  { value: "event_reviewer", label: "Olay İnceleyici" },
  { value: "coach", label: "Sürücü Koçu" },
  { value: "analyst", label: "Analist" },
  { value: "auditor", label: "Salt Okunur Denetçi" },
  { value: "integration_manager", label: "Entegrasyon Yöneticisi" },
];

export function can(user: SessionUser | null, permission: Permission): boolean {
  if (!user) return false;
  if (user.is_platform_admin) return true;
  if (!user.role) return false;
  return (ROLE_PERMISSIONS[user.role] ?? []).includes(permission);
}
