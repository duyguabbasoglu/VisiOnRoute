"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { Card, EmptyState, PageHeader, formatDateTime } from "@/components/ui";

interface Trip {
  id: string;
  vehicle_id: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  distance_km: number;
  point_count: number;
  max_speed_kph: number | null;
}

const STATUS_LABELS: Record<string, string> = {
  active: "Aktif",
  completed: "Tamamlandı",
  stale: "Bekliyor",
};

export default function TripsPage() {
  const query = useQuery({
    queryKey: ["trips"],
    queryFn: () => apiFetch<Trip[]>("/api/v1/trips?limit=100"),
  });
  const trips = query.data ?? [];

  return (
    <div>
      <PageHeader title="Seferler" description="Araç seferleri ve mesafe özetleri." />
      {query.isLoading ? (
        <p className="text-sm text-slate-500">Yükleniyor…</p>
      ) : trips.length === 0 ? (
        <EmptyState message="Henüz sefer kaydı yok. Telemetri geldikçe seferler otomatik oluşturulur." />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Başlangıç</th>
                <th className="px-4 py-2.5 font-medium">Durum</th>
                <th className="px-4 py-2.5 font-medium">Mesafe</th>
                <th className="px-4 py-2.5 font-medium">Nokta</th>
                <th className="px-4 py-2.5 font-medium">Azami hız</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {trips.map((t) => (
                <tr key={t.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 text-slate-600">{formatDateTime(t.started_at)}</td>
                  <td className="px-4 py-2.5 text-slate-600">
                    {STATUS_LABELS[t.status] ?? t.status}
                  </td>
                  <td className="px-4 py-2.5 text-slate-600">{t.distance_km.toFixed(1)} km</td>
                  <td className="px-4 py-2.5 text-slate-500">{t.point_count}</td>
                  <td className="px-4 py-2.5 text-slate-600">
                    {t.max_speed_kph != null ? `${Math.round(t.max_speed_kph)} km/s` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
