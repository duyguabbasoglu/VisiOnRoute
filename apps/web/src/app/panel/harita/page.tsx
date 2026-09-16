"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { z } from "zod";
import { FleetMap, MAP_SEVERITY_COLORS, type FleetMapData } from "@/components/FleetMap";
import {
  Alert,
  Card,
  PageHeader,
  SEVERITY_LABELS,
  SectionHeading,
  SeverityBadge,
  formatDateTime,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useVehicles } from "@/lib/fleet";
import { can, type Permission } from "@/lib/permissions";
import { geofenceSchema, liveVehicleSchema, roadRiskSchema, safetyEventListSchema } from "@/lib/schemas";

type LayerKey = "vehicles" | "events" | "risks" | "geofences";

const LAYERS: { key: LayerKey; label: string; permission: Permission }[] = [
  { key: "vehicles", label: "Aktif araçlar", permission: "trips.read" },
  { key: "events", label: "Güvenlik olayları", permission: "events.read" },
  { key: "risks", label: "Yol riski bölgeleri", permission: "risks.read" },
  { key: "geofences", label: "Coğrafi alanlar", permission: "risks.read" },
];

const GEOFENCE_KINDS: Record<string, string> = {
  high_risk: "Yüksek riskli alan",
  depot: "Depo / garaj",
  restricted: "Kısıtlı alan",
  custom: "Özel alan",
};

export default function MapPage() {
  const { user } = useAuth();
  const router = useRouter();
  const available = LAYERS.filter((layer) => can(user, layer.permission));
  const [visible, setVisible] = useState<Record<LayerKey, boolean>>({
    vehicles: true,
    events: true,
    risks: true,
    geofences: true,
  });
  const [severity, setSeverity] = useState("");
  const vehicles = useVehicles();

  const live = useQuery({
    queryKey: ["live"],
    queryFn: () => apiFetch("/api/v1/operations/live", { schema: z.array(liveVehicleSchema) }),
    enabled: can(user, "trips.read"),
    refetchInterval: 15_000,
  });
  const events = useQuery({
    queryKey: ["safety-events", "map", severity],
    queryFn: () =>
      apiFetch(`/api/v1/safety-events?limit=200${severity ? `&severity=${severity}` : ""}`, {
        schema: safetyEventListSchema,
      }),
    enabled: can(user, "events.read"),
  });
  const risks = useQuery({
    queryKey: ["road-risks"],
    queryFn: () => apiFetch("/api/v1/road-risks", { schema: z.array(roadRiskSchema) }),
    enabled: can(user, "risks.read"),
  });
  const geofences = useQuery({
    queryKey: ["geofences"],
    queryFn: () => apiFetch("/api/v1/geofences", { schema: z.array(geofenceSchema) }),
    enabled: can(user, "risks.read"),
  });

  const locatedEvents = (events.data?.items ?? []).filter((e) => e.latitude != null && e.longitude != null);
  const unlocatedEvents = (events.data?.items.length ?? 0) - locatedEvents.length;
  const locatedVehicles = (live.data ?? []).filter((v) => v.latitude != null && v.longitude != null);

  const data: FleetMapData = {
    vehicles: visible.vehicles
      ? locatedVehicles.map((v) => ({
          id: v.trip_id,
          latitude: v.latitude ?? 0,
          longitude: v.longitude ?? 0,
          label: vehicles.names.get(v.vehicle_id) ?? "Araç",
          detail: `${v.is_stale ? "Besleme gecikmeli" : "Canlı"} · Son sinyal ${formatDateTime(v.last_point_at)}`,
          stale: v.is_stale,
        }))
      : [],
    events: visible.events
      ? locatedEvents.map((e) => ({
          id: e.id,
          latitude: e.latitude ?? 0,
          longitude: e.longitude ?? 0,
          label: `${e.event_label} · ${e.severity_label}`,
          detail: `${vehicles.names.get(e.vehicle_id) ?? "Araç"} · ${formatDateTime(e.occurred_at)}`,
          severity: e.severity,
        }))
      : [],
    risks: visible.risks
      ? (risks.data ?? []).map((r) => ({
          id: r.id,
          latitude: r.center_latitude,
          longitude: r.center_longitude,
          radiusM: r.radius_m,
          severity: r.inferred_severity,
          label: "Tekrarlanan sert olay bölgesi",
          detail: `${r.observed_count} gözlem · güven %${Math.round(r.confidence * 100)}`,
        }))
      : [],
    geofences: visible.geofences
      ? (geofences.data ?? []).map((g) => ({
          id: g.id,
          latitude: g.center_latitude,
          longitude: g.center_longitude,
          radiusM: g.radius_m,
          label: g.name,
          detail: `${GEOFENCE_KINDS[g.kind] ?? g.kind} · ${Math.round(g.radius_m)} m`,
        }))
      : [],
  };

  const errors = [live, events, risks, geofences]
    .filter((q) => q.isError)
    .map((q) => errorMessage(q.error, "Harita verilerinin bir kısmı yüklenemedi."));

  return (
    <div>
      <PageHeader
        title="Harita"
        description="Aktif araçların son konumu, konumlu güvenlik olayları, yol riski bölgeleri ve coğrafi alanlar."
      />
      {errors.length > 0 && (
        <Alert kind="error" className="mb-4">
          {errors[0]}
        </Alert>
      )}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_18rem]">
        <FleetMap
          label="Filo haritası"
          data={data}
          className="h-[60vh] min-h-[22rem]"
          onSelect={(selection) =>
            router.push(selection.kind === "event" ? `/panel/olaylar/${selection.id}` : `/panel/seferler/${selection.id}`)
          }
        />
        <div className="space-y-4">
          <Card>
            <fieldset>
              <legend className="text-sm font-semibold text-ink-900">Katmanlar</legend>
              <div className="mt-3 space-y-2">
                {available.map((layer) => (
                  <label key={layer.key} className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={visible[layer.key]}
                      onChange={(e) => setVisible((current) => ({ ...current, [layer.key]: e.target.checked }))}
                    />
                    {layer.label}
                  </label>
                ))}
              </div>
            </fieldset>
            {can(user, "events.read") && (
              <label className="mt-4 block text-sm text-slate-700">
                <span className="font-medium">Olay şiddeti</span>
                <select
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                >
                  <option value="">Tüm şiddetler</option>
                  {["critical", "high", "medium", "low"].map((s) => (
                    <option key={s} value={s}>
                      {SEVERITY_LABELS[s]}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </Card>
          <Card>
            <h2 className="text-sm font-semibold text-ink-900">Gösterim</h2>
            <ul className="mt-3 space-y-2 text-sm text-slate-600">
              <li className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-full border-2 border-blue-400 bg-ink-900" aria-hidden />
                Aktif araç (gri: besleme gecikmeli)
              </li>
              {(["critical", "high", "medium", "low"] as const).map((s) => (
                <li key={s} className="flex items-center gap-2">
                  <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: MAP_SEVERITY_COLORS[s] }} aria-hidden />
                  {SEVERITY_LABELS[s]} şiddetli olay / risk bölgesi
                </li>
              ))}
              <li className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-sm border border-blue-600 bg-blue-600/20" aria-hidden />
                Coğrafi alan
              </li>
            </ul>
            {unlocatedEvents > 0 && (
              <p className="mt-3 text-xs text-slate-500">
                Konum bilgisi olmayan {unlocatedEvents} olay haritada gösterilmez.
              </p>
            )}
          </Card>
        </div>
      </div>

      {visible.events && locatedEvents.length > 0 && (
        <Card className="mt-6">
          <SectionHeading title="Haritadaki son olaylar" description="Klavye ile erişim için olayların liste görünümü." />
          <ul className="divide-y divide-slate-100">
            {locatedEvents.slice(0, 10).map((e) => (
              <li key={e.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                <div>
                  <p className="text-sm text-ink-900">
                    {e.event_label} · {vehicles.names.get(e.vehicle_id) ?? "Araç"}
                  </p>
                  <p className="text-xs text-slate-500">{formatDateTime(e.occurred_at)}</p>
                </div>
                <div className="flex items-center gap-3">
                  <SeverityBadge severity={e.severity} label={e.severity_label} />
                  <Link href={`/panel/olaylar/${e.id}`} className="text-xs font-medium text-brand-700 hover:underline">
                    İncele
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
