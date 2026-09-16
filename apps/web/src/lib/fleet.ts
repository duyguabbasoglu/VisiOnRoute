"use client";

/** Shared fleet lookups so screens show plates and names instead of internal IDs. */
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";
import { useAuth } from "./auth";
import { can } from "./permissions";
import { driverListSchema, vehicleListSchema } from "./schemas";

export function useVehicles() {
  const { user } = useAuth();
  const query = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => apiFetch("/api/v1/vehicles?limit=200", { schema: vehicleListSchema }),
    enabled: can(user, "fleet.read"),
  });
  const items = query.data?.items ?? [];
  const names = new Map(items.map((v) => [v.id, v.plate ?? v.external_id]));
  return { query, items, names };
}

export function useDrivers() {
  const { user } = useAuth();
  const query = useQuery({
    queryKey: ["drivers"],
    queryFn: () => apiFetch("/api/v1/drivers?limit=200", { schema: driverListSchema }),
    enabled: can(user, "fleet.read"),
  });
  const items = query.data?.items ?? [];
  const names = new Map(items.map((d) => [d.id, d.full_name]));
  return { query, items, names };
}

export const VEHICLE_STATUS: Record<string, { label: string; tone: "success" | "neutral" | "warning" }> = {
  active: { label: "Etkin", tone: "success" },
  inactive: { label: "Pasif", tone: "neutral" },
  maintenance: { label: "Bakımda", tone: "warning" },
};

export const TRIP_STATUS: Record<string, { label: string; tone: "success" | "neutral" | "warning" }> = {
  active: { label: "Devam ediyor", tone: "success" },
  completed: { label: "Tamamlandı", tone: "neutral" },
  stale: { label: "Sinyal kesildi", tone: "warning" },
};

export const EQUIPMENT_STATUS: Record<string, { label: string; tone: "success" | "neutral" | "warning" }> = {
  active: { label: "Etkin", tone: "success" },
  inactive: { label: "Pasif", tone: "neutral" },
  offline: { label: "Çevrimdışı", tone: "warning" },
  obstructed: { label: "Görüşü engelli", tone: "warning" },
};

export const DEVICE_KINDS = [
  { value: "telematics", label: "Telematik ünitesi" },
  { value: "dashcam", label: "Araç kamerası kaydedici" },
  { value: "sensor", label: "Sensör" },
  { value: "gateway", label: "Ağ geçidi" },
] as const;

export const CAMERA_POSITIONS = [
  { value: "road", label: "Yol (ön cam)" },
  { value: "driver", label: "Sürücü" },
  { value: "cabin", label: "Kabin" },
  { value: "rear", label: "Arka" },
] as const;

export function labelOf(options: readonly { value: string; label: string }[], value: string): string {
  return options.find((option) => option.value === value)?.label ?? value;
}

/** Short, human-readable reference for a record that has no name (never a full UUID). */
export function shortRef(id: string): string {
  return `#${id.slice(-6).toUpperCase()}`;
}
