"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { z } from "zod";
import { FleetMap } from "@/components/FleetMap";
import { Badge, Card, EmptyState, ErrorState, PageHeader, SkeletonRows, formatDateTime } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useDrivers, useVehicles } from "@/lib/fleet";
import { liveVehicleSchema } from "@/lib/schemas";
import { subscribeToStream, type StreamStatus } from "@/lib/stream";

const liveListSchema = z.array(liveVehicleSchema);
const FALLBACK_REFRESH_MS = 10_000;

const STATUS_BADGE: Record<StreamStatus, { label: string; tone: "success" | "warning" | "info" }> = {
  live: { label: "Anlık bağlantı açık", tone: "success" },
  connecting: { label: "Bağlanıyor…", tone: "info" },
  fallback: { label: "Anlık bağlantı yok — 10 sn'de bir yenileniyor", tone: "warning" },
};

export default function LiveOpsPage() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("connecting");
  const vehicles = useVehicles();
  const drivers = useDrivers();

  const query = useQuery({
    queryKey: ["live"],
    queryFn: () => apiFetch("/api/v1/operations/live", { schema: liveListSchema }),
    // Polling only while the push stream is not delivering updates.
    refetchInterval: streamStatus === "live" ? false : FALLBACK_REFRESH_MS,
  });

  useEffect(
    () =>
      subscribeToStream("/api/v1/operations/stream", {
        onStatus: setStreamStatus,
        onEvent: (event, data) => {
          if (event === "live") {
            try {
              const parsed = liveListSchema.safeParse(JSON.parse(data));
              if (parsed.success) queryClient.setQueryData(["live"], parsed.data);
            } catch {
              // Malformed payloads are ignored; the next update replaces them.
            }
          } else if (event === "safety") {
            void queryClient.invalidateQueries({ queryKey: ["safety-events"] });
          }
        },
      }),
    [queryClient],
  );

  const live = query.data ?? [];
  const status = STATUS_BADGE[streamStatus];
  const name = (vehicleId: string) => vehicles.names.get(vehicleId) ?? "Araç";

  return (
    <div>
      <PageHeader
        title="Canlı Operasyon"
        description="Aktif seferlerin son bilinen konumu; yeni telemetri geldikçe anında güncellenir."
        action={
          <span aria-live="polite">
            <Badge tone={status.tone}>{status.label}</Badge>
          </span>
        }
      />
      {query.isLoading ? (
        <SkeletonRows rows={4} />
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error, "Canlı veriler yüklenemedi.")} onRetry={() => void query.refetch()} />
      ) : live.length === 0 ? (
        <EmptyState message="Şu anda aktif sefer yok. Telemetri gelmeye başladığında araçlar burada ve haritada görünür." />
      ) : (
        <>
          <FleetMap
            label="Aktif araçların haritası"
            className="mb-6 h-80"
            data={{
              vehicles: live
                .filter((v) => v.latitude != null && v.longitude != null)
                .map((v) => ({
                  id: v.trip_id,
                  latitude: v.latitude ?? 0,
                  longitude: v.longitude ?? 0,
                  label: name(v.vehicle_id),
                  detail: `Son sinyal ${formatDateTime(v.last_point_at)}`,
                  stale: v.is_stale,
                })),
            }}
            onSelect={(selection) => router.push(`/panel/seferler/${selection.id}`)}
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {live.map((v) => (
              <Card key={v.trip_id}>
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate font-medium text-ink-900">{name(v.vehicle_id)}</span>
                  {v.is_stale ? <Badge tone="warning">Besleme gecikmeli</Badge> : <Badge tone="success">Canlı</Badge>}
                </div>
                <dl className="mt-3 space-y-1 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Sürücü</dt>
                    <dd className="text-slate-700">{v.driver_id ? (drivers.names.get(v.driver_id) ?? "Atanmış") : "Atanmamış"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Azami hız</dt>
                    <dd className="text-slate-700">{v.max_speed_kph != null ? `${Math.round(v.max_speed_kph)} km/s` : "—"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Son sinyal</dt>
                    <dd className="text-slate-700">{formatDateTime(v.last_point_at)}</dd>
                  </div>
                </dl>
                <Link href={`/panel/seferler/${v.trip_id}`} className="mt-3 inline-block text-xs font-medium text-brand-700 hover:underline">
                  Seferi aç
                </Link>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
