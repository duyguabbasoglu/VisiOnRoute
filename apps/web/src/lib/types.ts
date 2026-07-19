/** API response shapes (mirrors backend Pydantic schemas). */

export interface SessionUser {
  id: string;
  email: string;
  full_name: string;
  organization_id: string | null;
  organization_name: string | null;
  role: string | null;
  role_label: string | null;
  is_platform_admin: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: SessionUser;
}

export interface SafetyEvent {
  id: string;
  event_type: string;
  event_label: string;
  severity: string;
  severity_label: string;
  confidence: number;
  occurred_at: string;
  vehicle_id: string;
  driver_id: string | null;
  trip_id: string | null;
  latitude: number | null;
  longitude: number | null;
  reason_tr: string;
  review_status: string;
  occurrence_count: number;
  needs_review: boolean;
}

export interface SafetyEventList {
  items: SafetyEvent[];
  total: number;
  limit: number;
  offset: number;
}

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

export interface LiveVehicle {
  trip_id: string;
  vehicle_id: string;
  driver_id: string | null;
  latitude: number | null;
  longitude: number | null;
  last_point_at: string | null;
  max_speed_kph: number | null;
  is_stale: boolean;
}

export interface Paginated<T> {
  items: T[];
  pagination: { total: number; limit: number; offset: number };
}

export interface RoadRisk {
  id: string;
  risk_type: string;
  center_latitude: number;
  center_longitude: number;
  radius_m: number;
  observed_count: number;
  inferred_severity: string;
  confidence: number;
  source: string;
  review_status: string;
}
