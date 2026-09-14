"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { z } from "zod";
import { Card, PageHeader, SeverityBadge, StatTile, formatDateTime } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { liveVehicleSchema, roadRiskSchema, safetyEventListSchema } from "@/lib/schemas";

export default function OverviewPage() {
  const { user } = useAuth();
  const canEvents = can(user, "events.read");
  const canTrips = can(user, "trips.read");
  const canRisks = can(user, "risks.read");

  const events = useQuery({
    queryKey: ["safety-events", "overview"],
    queryFn: () =>
      apiFetch("/api/v1/safety-events?limit=5", { schema: safetyEventListSchema }),
    enabled: canEvents,
  });
  const pending = useQuery({
    queryKey: ["safety-events", "overview", "pending"],
    queryFn: () =>
      apiFetch("/api/v1/safety-events?limit=1&review_status=pending", {
        schema: safetyEventListSchema,
      }),
    enabled: canEvents,
  });
  const live = useQuery({
    queryKey: ["live", "overview"],
    queryFn: () => apiFetch("/api/v1/operations/live", { schema: z.array(liveVehicleSchema) }),
    enabled: canTrips,
  });
  const risks = useQuery({
    queryKey: ["road-risks", "overview"],
    queryFn: () => apiFetch("/api/v1/road-risks", { schema: z.array(roadRiskSchema) }),
    enabled: canRisks,
  });

  const value = (loading: boolean, n: number | undefined) => (loading ? "…" : String(n ?? 0));

  return (
    <div>
      <PageHeader
        title="Genel Bakış"
        description={`Hoş geldiniz${user ? `, ${user.full_name}` : ""}. Filonuzun güvenlik durumuna hızlı bir bakış.`}
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {canEvents && (
          <StatTile label="Toplam güvenlik olayı" value={value(events.isLoading, events.data?.total)} hint="Tüm zamanlar" />
        )}
        {canEvents && (
          <StatTile label="İnceleme bekleyen" value={value(pending.isLoading, pending.data?.total)} />
        )}
        {canTrips && <StatTile label="Aktif seferler" value={value(live.isLoading, live.data?.length)} />}
        {canRisks && <StatTile label="Yol riski bölgesi" value={value(risks.isLoading, risks.data?.length)} />}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {canEvents && (
          <Card>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-ink-900">Son güvenlik olayları</h2>
              <Link href="/panel/olaylar" className="text-xs text-brand-600 hover:underline">
                Tümünü gör
              </Link>
            </div>
            {events.data && events.data.items.length > 0 ? (
              <ul className="divide-y divide-slate-100">
                {events.data.items.map((event) => (
                  <li key={event.id}>
                    <Link href={`/panel/olaylar/${event.id}`} className="flex items-center justify-between py-2.5 hover:bg-slate-50">
                      <div>
                        <p className="text-sm text-ink-900">{event.event_label}</p>
                        <p className="text-xs text-slate-400">{formatDateTime(event.occurred_at)}</p>
                      </div>
                      <SeverityBadge severity={event.severity} label={event.severity_label} />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-6 text-center text-sm text-slate-400">
                Henüz güvenlik olayı yok. Entegrasyonlar sayfasından bir veri kaynağı tanımlayıp
                telemetri gönderdiğinizde olaylar burada görünür.
              </p>
            )}
          </Card>
        )}

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-ink-900">Metodoloji</h2>
          <p className="text-sm text-slate-600">
            Güvenlik olayları, telemetri verilerine uygulanan{" "}
            <strong>deterministik kurallarla</strong> üretilir. Şiddet ve güven seviyeleri ayrı
            hesaplanır; düşük veri kalitesi olayı insan incelemesine işaretler. Bu platform
            kazaları önlediğini iddia etmez; riskleri veriye dayalı ve açıklanabilir biçimde
            görünür kılar.
          </p>
        </Card>
      </div>
    </div>
  );
}
