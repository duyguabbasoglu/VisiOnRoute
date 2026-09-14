"use client";

import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageHeader, formatDateTime } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { tripSchema, vehicleListSchema } from "@/lib/schemas";

const STATUS: Record<string, { label: string; tone: "success" | "neutral" | "warning" }> = {
  active: { label: "Devam ediyor", tone: "success" },
  completed: { label: "Tamamlandı", tone: "neutral" },
  stale: { label: "Sinyal kesildi", tone: "warning" },
};

export default function TripsPage() {
  const trips = useQuery({
    queryKey: ["trips"],
    queryFn: () => apiFetch("/api/v1/trips?limit=100", { schema: z.array(tripSchema) }),
  });
  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => apiFetch("/api/v1/vehicles?limit=100", { schema: vehicleListSchema }),
  });
  const vehicleName = new Map((vehicles.data?.items ?? []).map((v) => [v.id, v.plate ?? v.external_id]));

  return (
    <div>
      <PageHeader title="Seferler" description="Araç seferleri ve mesafe özetleri." />
      {trips.isLoading ? (
        <LoadingState />
      ) : trips.isError ? (
        <ErrorState message={errorMessage(trips.error, "Seferler yüklenemedi.")} onRetry={() => void trips.refetch()} />
      ) : !trips.data?.length ? (
        <EmptyState message="Henüz sefer kaydı yok. Telemetri geldikçe seferler otomatik oluşturulur." />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Başlangıç</th>
                <th className="px-4 py-2.5 font-medium">Araç</th>
                <th className="px-4 py-2.5 font-medium">Durum</th>
                <th className="px-4 py-2.5 font-medium">Mesafe</th>
                <th className="px-4 py-2.5 font-medium">Nokta</th>
                <th className="px-4 py-2.5 font-medium">Azami hız</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {trips.data.map((t) => {
                const status = STATUS[t.status] ?? { label: t.status, tone: "neutral" as const };
                return (
                  <tr key={t.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2.5 text-slate-600">{formatDateTime(t.started_at)}</td>
                    <td className="px-4 py-2.5 text-ink-900">{vehicleName.get(t.vehicle_id) ?? "—"}</td>
                    <td className="px-4 py-2.5">
                      <Badge tone={status.tone}>{status.label}</Badge>
                    </td>
                    <td className="px-4 py-2.5 text-slate-600">{t.distance_km.toFixed(1)} km</td>
                    <td className="px-4 py-2.5 text-slate-500">{t.point_count}</td>
                    <td className="px-4 py-2.5 text-slate-600">
                      {t.max_speed_kph != null ? `${Math.round(t.max_speed_kph)} km/s` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
