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
import type { safetyEventDetailSchema } from "./schemas";
import type { z } from "zod";

export type SafetyEventDetail = z.infer<typeof safetyEventDetailSchema>;

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
