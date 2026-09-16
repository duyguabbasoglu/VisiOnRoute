"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { z } from "zod";
import {
  Badge,
  CELL,
  DataTable,
  EmptyState,
  ErrorState,
  PageHeader,
  SkeletonRows,
  formatDateTime,
  formatNumber,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { TRIP_STATUS, useDrivers, useVehicles } from "@/lib/fleet";
import { tripSchema } from "@/lib/schemas";

export default function TripsPage() {
  const [status, setStatus] = useState("");
  const trips = useQuery({
    queryKey: ["trips", status],
    queryFn: () =>
      apiFetch(`/api/v1/trips?limit=100${status ? `&status=${status}` : ""}`, { schema: z.array(tripSchema) }),
  });
  const vehicles = useVehicles();
  const drivers = useDrivers();

  return (
    <div>
      <PageHeader
        title="Seferler"
        description="Telemetri geldikçe otomatik oluşturulan araç seferleri; güzergâh ve olaylar için ayrıntıyı açın."
        action={
          <label className="text-sm text-slate-600">
            <span className="sr-only">Sefer durumu</span>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm"
            >
              <option value="">Tüm seferler</option>
              {Object.entries(TRIP_STATUS).map(([value, s]) => (
                <option key={value} value={value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        }
      />
      {trips.isLoading ? (
        <SkeletonRows rows={4} />
      ) : trips.isError ? (
        <ErrorState message={errorMessage(trips.error, "Seferler yüklenemedi.")} onRetry={() => void trips.refetch()} />
      ) : !trips.data?.length ? (
        <EmptyState
          message={
            status
              ? "Seçili durumda sefer yok."
              : "Henüz sefer kaydı yok. Telemetri geldikçe seferler otomatik oluşturulur."
          }
        />
      ) : (
        <DataTable label="Seferler" headers={["Başlangıç", "Araç", "Sürücü", "Durum", "Mesafe", "Azami hız", ""]}>
          {trips.data.map((t) => {
            const s = TRIP_STATUS[t.status] ?? { label: t.status, tone: "neutral" as const };
            return (
              <tr key={t.id} className="hover:bg-slate-50">
                <td className={`${CELL} text-slate-600`}>{formatDateTime(t.started_at)}</td>
                <td className={`${CELL} font-medium text-ink-900`}>{vehicles.names.get(t.vehicle_id) ?? "—"}</td>
                <td className={`${CELL} text-slate-600`}>{t.driver_id ? (drivers.names.get(t.driver_id) ?? "—") : "—"}</td>
                <td className={CELL}>
                  <Badge tone={s.tone}>{s.label}</Badge>
                </td>
                <td className={`${CELL} text-slate-600`}>{formatNumber(t.distance_km)} km</td>
                <td className={`${CELL} text-slate-600`}>
                  {t.max_speed_kph != null ? `${Math.round(t.max_speed_kph)} km/s` : "—"}
                </td>
                <td className={`${CELL} text-right`}>
                  <Link href={`/panel/seferler/${t.id}`} className="text-xs font-medium text-brand-700 hover:underline">
                    Ayrıntı
                  </Link>
                </td>
              </tr>
            );
          })}
        </DataTable>
      )}
    </div>
  );
}
