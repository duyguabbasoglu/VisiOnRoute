/** API response shapes. Identity/event types are inferred from Zod schemas. */

export type {
  AuthResponse,
  Invitation,
  LiveVehicle,
  Member,
  Organization,
  RoadRisk,
  SafetyEvent,
  SafetyEventList,
  SessionUser,
} from "./schemas";
import type { SafetyEvent } from "./schemas";

export interface SafetyEventDetail extends SafetyEvent {
  explanation: {
    ne_oldu: string;
    ne_zaman: string;
    nerede: { latitude: number; longitude: number } | null;
    hangi_veri: string;
    hangi_kural: string;
    esik: number | null;
    olculen_deger: number | null;
    guven_seviyesi: number;
    veri_kalitesi: number | null;
    inceleme_gerekli: boolean;
  };
  ruleset_version: number;
  severity_framework_version: number;
  evidence: {
    id: string;
    kind: string;
    telemetry_window: Record<string, unknown> | null;
    captured_at: string | null;
  }[];
  evidence_restricted: boolean;
}

export interface Vehicle {
  id: string;
  external_id: string;
  plate: string | null;
  label: string | null;
  make: string | null;
  model: string | null;
  year: number | null;
  status: string;
  fleet_id: string | null;
  created_at: string;
}

export interface Driver {
  id: string;
  external_id: string;
  full_name: string;
  phone: string | null;
  status: string;
  created_at: string;
}

export interface Paginated<T> {
  items: T[];
  pagination: { total: number; limit: number; offset: number };
}
