"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { z } from "zod";
import { FleetMap } from "@/components/FleetMap";
import {
  Alert,
  Badge,
  CELL,
  Card,
  DataTable,
  DetailRow,
  EmptyState,
  ErrorState,
  PageHeader,
  ReviewBadge,
  SeverityBadge,
  SkeletonRows,
  formatDateTime,
  formatNumber,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { TRIP_STATUS, useDrivers, useVehicles } from "@/lib/fleet";
import { can } from "@/lib/permissions";
import { safetyEventListSchema, trailPointSchema, tripSchema } from "@/lib/schemas";

export default function TripDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const router = useRouter();
  const canTrail = can(user, "telemetry.read");
  const canEvents = can(user, "events.read");
  const vehicles = useVehicles();
  const drivers = useDrivers();

  const trip = useQuery({
    queryKey: ["trip", id],
    queryFn: () => apiFetch(`/api/v1/trips/${id}`, { schema: tripSchema }),
  });
  const trail = useQuery({
    queryKey: ["trip", id, "trail"],
    queryFn: () => apiFetch(`/api/v1/trips/${id}/trail?limit=5000`, { schema: z.array(trailPointSchema) }),
    enabled: canTrail,
  });
  const events = useQuery({
    queryKey: ["safety-events", "trip", id],
    queryFn: () => apiFetch(`/api/v1/safety-events?trip_id=${id}&limit=200`, { schema: safetyEventListSchema }),
    enabled: canEvents,
  });

  if (trip.isLoading) return <SkeletonRows rows={4} />;
  if (trip.isError || !trip.data) {
    return (
      <div>
        <BackLink />
        <ErrorState message={errorMessage(trip.error, "Sefer yüklenemedi.")} onRetry={() => void trip.refetch()} />
      </div>
    );
  }

  const t = trip.data;
  const status = TRIP_STATUS[t.status] ?? { label: t.status, tone: "neutral" as const };
  const vehicleName = vehicles.names.get(t.vehicle_id) ?? "Araç";
  const eventItems = events.data?.items ?? [];
  const speeds = (trail.data ?? []).map((p) => p.speed_kph).filter((s): s is number => s != null);
  const averageSpeed = speeds.length ? speeds.reduce((a, b) => a + b, 0) / speeds.length : null;

  return (
    <div>
      <BackLink />
      <PageHeader
        title={`Sefer · ${vehicleName}`}
        description={`${formatDateTime(t.started_at)} tarihinde başladı.`}
        action={<Badge tone={status.tone}>{status.label}</Badge>}
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_20rem]">
        <div>
          {canTrail ? (
            trail.isError ? (
              <ErrorState message={errorMessage(trail.error, "Güzergâh yüklenemedi.")} onRetry={() => void trail.refetch()} />
            ) : (
              <FleetMap
                label="Sefer güzergâhı"
                className="h-[26rem]"
                data={{
                  trail: (trail.data ?? []).map((p) => [p.longitude, p.latitude]),
                  events: eventItems
                    .filter((e) => e.latitude != null && e.longitude != null)
                    .map((e) => ({
                      id: e.id,
                      latitude: e.latitude ?? 0,
                      longitude: e.longitude ?? 0,
                      label: `${e.event_label} · ${e.severity_label}`,
                      detail: formatDateTime(e.occurred_at),
                      severity: e.severity,
                    })),
                }}
                onSelect={(selection) => {
                  if (selection.kind === "event") router.push(`/panel/olaylar/${selection.id}`);
                }}
              />
            )
          ) : (
            <Alert kind="info">Güzergâhı görüntülemek için telemetri okuma yetkisi gerekir.</Alert>
          )}
          {canTrail && trail.data && trail.data.length === 0 && (
            <p className="mt-2 text-xs text-slate-500">Bu sefer için kayıtlı konum noktası yok.</p>
          )}
        </div>
        <Card>
          <h2 className="mb-2 text-sm font-semibold text-ink-900">Sefer özeti</h2>
          <dl className="divide-y divide-slate-100">
            <DetailRow label="Araç" value={vehicleName} />
            <DetailRow label="Sürücü" value={t.driver_id ? (drivers.names.get(t.driver_id) ?? "Atanmış sürücü") : "Atanmamış"} />
            <DetailRow label="Başlangıç" value={formatDateTime(t.started_at)} />
            <DetailRow label="Bitiş" value={formatDateTime(t.ended_at)} />
            <DetailRow label="Son sinyal" value={formatDateTime(t.last_point_at)} />
            <DetailRow label="Mesafe" value={`${formatNumber(t.distance_km)} km`} />
            <DetailRow label="Konum noktası" value={formatNumber(t.point_count, 0)} />
            <DetailRow label="Azami hız" value={t.max_speed_kph != null ? `${Math.round(t.max_speed_kph)} km/s` : "—"} />
            {averageSpeed != null && <DetailRow label="Ortalama anlık hız" value={`${Math.round(averageSpeed)} km/s`} />}
            {canEvents && <DetailRow label="Güvenlik olayı" value={String(events.data?.total ?? "…")} />}
          </dl>
        </Card>
      </div>

      {canEvents && (
        <div className="mt-6">
          <h2 className="mb-3 text-base font-semibold text-ink-900">Bu seferdeki güvenlik olayları</h2>
          {events.isLoading ? (
            <SkeletonRows />
          ) : events.isError ? (
            <ErrorState message={errorMessage(events.error, "Olaylar yüklenemedi.")} onRetry={() => void events.refetch()} />
          ) : eventItems.length === 0 ? (
            <EmptyState message="Bu seferde güvenlik olayı tespit edilmedi." />
          ) : (
            <DataTable label="Seferdeki güvenlik olayları" headers={["Olay", "Şiddet", "Zaman", "İnceleme", ""]}>
              {eventItems.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50">
                  <td className={`${CELL} text-ink-900`}>{e.event_label}</td>
                  <td className={CELL}>
                    <SeverityBadge severity={e.severity} label={e.severity_label} />
                  </td>
                  <td className={`${CELL} text-slate-500`}>{formatDateTime(e.occurred_at)}</td>
                  <td className={CELL}>
                    <ReviewBadge status={e.review_status} />
                  </td>
                  <td className={`${CELL} text-right`}>
                    <Link href={`/panel/olaylar/${e.id}`} className="text-xs font-medium text-brand-700 hover:underline">
                      İncele
                    </Link>
                  </td>
                </tr>
              ))}
            </DataTable>
          )}
        </div>
      )}
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/panel/seferler" className="mb-3 inline-block text-sm text-brand-700 hover:underline">
      ← Seferler
    </Link>
  );
}
