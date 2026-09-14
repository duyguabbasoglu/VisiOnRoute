"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { z } from "zod";
import { Badge, Card, EmptyState, ErrorState, PageHeader, formatDateTime } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
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
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("connecting");

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

  const vehicles = query.data ?? [];
  const status = STATUS_BADGE[streamStatus];

  return (
    <div>
      <PageHeader title="Canlı Operasyon" description="Aktif seferlerin son bilinen konumu." />
      <div className="mb-4" aria-live="polite">
        <Badge tone={status.tone}>{status.label}</Badge>
      </div>
      {query.isLoading ? (
        <p className="text-sm text-slate-500">Yükleniyor…</p>
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error, "Canlı veriler yüklenemedi.")} />
      ) : vehicles.length === 0 ? (
        <EmptyState message="Şu anda aktif sefer yok. Telemetri gelmeye başladığında araçlar burada görünür." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {vehicles.map((v) => (
            <Card key={v.trip_id}>
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm text-ink-900">{v.vehicle_id.slice(0, 8)}</span>
                {v.is_stale ? (
                  <Badge tone="warning">Besleme gecikmeli</Badge>
                ) : (
                  <Badge tone="success">Canlı</Badge>
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
