"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { LiveVehicle } from "@/lib/types";
import { Card, EmptyState, PageHeader, formatDateTime } from "@/components/ui";

export default function LiveOpsPage() {
  const query = useQuery({
    queryKey: ["live"],
    queryFn: () => apiFetch<LiveVehicle[]>("/api/v1/operations/live"),
    refetchInterval: 10_000, // near-real-time refresh
  });

  const vehicles = query.data ?? [];

  return (
    <div>
      <PageHeader
        title="Canlı Operasyon"
        description="Aktif seferlerin son bilinen konumu (10 sn'de bir yenilenir)."
      />
      {query.isLoading ? (
        <p className="text-sm text-slate-500">Yükleniyor…</p>
      ) : vehicles.length === 0 ? (
        <EmptyState message="Şu anda aktif sefer yok. Telemetri gelmeye başladığında araçlar burada görünür." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {vehicles.map((v) => (
            <Card key={v.trip_id}>
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm text-ink-900">
                  {v.vehicle_id.slice(0, 8)}
                </span>
                {v.is_stale ? (
                  <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-700">
                    Besleme gecikmeli
                  </span>
                ) : (
                  <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">
                    Canlı
                  </span>
                )}
              </div>
              <dl className="mt-3 space-y-1 text-sm">
                <div className="flex justify-between">
                  <dt className="text-slate-400">Konum</dt>
                  <dd className="text-slate-700">
                    {v.latitude != null && v.longitude != null
                      ? `${v.latitude.toFixed(4)}, ${v.longitude.toFixed(4)}`
                      : "—"}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Azami hız</dt>
                  <dd className="text-slate-700">
                    {v.max_speed_kph != null ? `${Math.round(v.max_speed_kph)} km/s` : "—"}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Son sinyal</dt>
                  <dd className="text-slate-700">{formatDateTime(v.last_point_at)}</dd>
                </div>
              </dl>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
