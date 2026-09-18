"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { z } from "zod";
import { FleetMap } from "@/components/FleetMap";
import { Card, PageHeader, SectionHeading, SeverityBadge, StatTile, formatDateTime } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useVehicles } from "@/lib/fleet";
import { can } from "@/lib/permissions";
import {
  coachingSummarySchema,
  dataSourceSchema,
  liveVehicleSchema,
  roadRiskSchema,
  safetyEventListSchema,
} from "@/lib/schemas";

export default function OverviewPage() {
  const { user } = useAuth();
  const router = useRouter();
  const canEvents = can(user, "events.read");
  const canTrips = can(user, "trips.read");
  const canRisks = can(user, "risks.read");
  const canCoaching = can(user, "coaching.read");
  const canIntegrations = can(user, "integrations.read");
  const canFleet = can(user, "fleet.read");
  const vehicles = useVehicles();

  const events = useQuery({
    queryKey: ["safety-events", "overview"],
    queryFn: () => apiFetch("/api/v1/safety-events?limit=50", { schema: safetyEventListSchema }),
    enabled: canEvents,
  });
  const pending = useQuery({
    queryKey: ["safety-events", "overview", "pending"],
    queryFn: () =>
      apiFetch("/api/v1/safety-events?limit=1&review_status=pending", { schema: safetyEventListSchema }),
    enabled: canEvents,
  });
  const live = useQuery({
    queryKey: ["live"],
    queryFn: () => apiFetch("/api/v1/operations/live", { schema: z.array(liveVehicleSchema) }),
    enabled: canTrips,
    refetchInterval: 30_000,
  });
  const risks = useQuery({
    queryKey: ["road-risks"],
    queryFn: () => apiFetch("/api/v1/road-risks", { schema: z.array(roadRiskSchema) }),
    enabled: canRisks,
  });
  const coaching = useQuery({
    queryKey: ["coaching", "summary"],
    queryFn: () => apiFetch("/api/v1/coaching-actions/summary", { schema: coachingSummarySchema }),
    enabled: canCoaching,
  });
  const sources = useQuery({
    queryKey: ["data-sources"],
    queryFn: () => apiFetch("/api/v1/integrations/data-sources", { schema: z.array(dataSourceSchema) }),
    enabled: canIntegrations,
  });

  const value = (loading: boolean, n: number | undefined) => (loading ? "…" : String(n ?? 0));
  const recent = (events.data?.items ?? []).slice(0, 6);

  const steps = [
    { done: vehicles.items.length > 0, label: "İlk aracınızı ekleyin", href: "/panel/araclar", show: canFleet },
    { done: (sources.data?.length ?? 0) > 0, label: "Bir veri kaynağı tanımlayın", href: "/panel/entegrasyonlar", show: canIntegrations },
    {
      done: (sources.data ?? []).some((s) => s.accepted_count > 0),
      label: "API anahtarıyla telemetri gönderin",
      href: "/panel/entegrasyonlar",
      show: canIntegrations,
    },
    { done: (events.data?.total ?? 0) > 0, label: "İlk güvenlik olayını inceleyin", href: "/panel/olaylar", show: canEvents },
  ].filter((step) => step.show);
  const loadingSetup = vehicles.query.isLoading || sources.isLoading || events.isLoading;
  const showSetup = !loadingSetup && steps.length > 0 && steps.some((step) => !step.done);

  return (
    <div>
      <PageHeader
        title="Genel Bakış"
        description={`Hoş geldiniz${user ? `, ${user.full_name}` : ""}. Filonuzun güvenlik durumuna hızlı bir bakış.`}
      />

      {showSetup && (
        <Card className="mb-6 border-brand-100 bg-brand-50/50">
          <SectionHeading title="Başlangıç adımları" description="VisiOnRoute'u kullanmaya başlamak için şu adımları tamamlayın." />
          <ol className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map((step, index) => (
              <li key={step.label}>
                <Link
                  href={step.href}
                  className={`flex h-full items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition ${
                    step.done ? "border-emerald-200 bg-white text-slate-500" : "border-slate-200 bg-white text-ink-900 hover:border-brand-500"
                  }`}
                >
                  <span
                    aria-hidden
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                      step.done ? "bg-emerald-100 text-emerald-700" : "bg-brand-100 text-brand-700"
                    }`}
                  >
                    {step.done ? "✓" : index + 1}
                  </span>
                  <span>
                    {step.label}
                    <span className="sr-only">{step.done ? " (tamamlandı)" : " (bekliyor)"}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {canEvents && <StatTile label="Toplam güvenlik olayı" value={value(events.isLoading, events.data?.total)} hint="Tüm zamanlar" />}
        {canEvents && <StatTile label="İnceleme bekleyen" value={value(pending.isLoading, pending.data?.total)} />}
        {canTrips && <StatTile label="Aktif seferler" value={value(live.isLoading, live.data?.length)} />}
        {canCoaching ? (
          <StatTile
            label="Açık koçluk görevi"
            value={value(coaching.isLoading, coaching.data ? coaching.data.open + coaching.data.in_progress : undefined)}
            hint={coaching.data?.overdue ? `${coaching.data.overdue} görev gecikmede` : undefined}
          />
        ) : (
          canRisks && <StatTile label="Yol riski bölgesi" value={value(risks.isLoading, risks.data?.length)} />
        )}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-5">
        {(canTrips || canEvents) && (
          <Card className="lg:col-span-3">
            <SectionHeading
              title="Operasyon haritası"
              action={
                <Link href="/panel/harita" className="text-xs font-medium text-brand-700 hover:underline">
                  Tam ekran harita
                </Link>
              }
            />
            <FleetMap
              label="Aktif araçlar ve son olaylar"
              className="h-72"
              data={{
                vehicles: (live.data ?? [])
                  .filter((v) => v.latitude != null && v.longitude != null)
                  .map((v) => ({
                    id: v.trip_id,
                    latitude: v.latitude ?? 0,
                    longitude: v.longitude ?? 0,
                    label: vehicles.names.get(v.vehicle_id) ?? "Araç",
                    stale: v.is_stale,
                  })),
                events: (events.data?.items ?? [])
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
              onSelect={(selection) =>
                router.push(selection.kind === "event" ? `/panel/olaylar/${selection.id}` : `/panel/seferler/${selection.id}`)
              }
            />
          </Card>
        )}

        {canEvents && (
          <Card className="lg:col-span-2">
            <SectionHeading
              title="Son güvenlik olayları"
              action={
                <Link href="/panel/olaylar" className="text-xs font-medium text-brand-700 hover:underline">
                  Tümünü gör
                </Link>
              }
            />
            {recent.length > 0 ? (
              <ul className="divide-y divide-slate-100">
                {recent.map((event) => (
                  <li key={event.id}>
                    <Link href={`/panel/olaylar/${event.id}`} className="flex items-center justify-between gap-3 py-2.5 hover:bg-slate-50">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-ink-900">
                          {event.event_label} · {vehicles.names.get(event.vehicle_id) ?? "Araç"}
                        </p>
                        <p className="text-xs text-slate-500">{formatDateTime(event.occurred_at)}</p>
                      </div>
                      <SeverityBadge severity={event.severity} label={event.severity_label} />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-6 text-center text-sm text-slate-500">
                {events.isLoading ? "Yükleniyor…" : "Henüz güvenlik olayı yok."}
              </p>
            )}
          </Card>
        )}
      </div>

      <Card className="mt-6">
        <SectionHeading title="Metodoloji" />
        <p className="text-sm text-slate-600">
          Güvenlik olayları, telemetri verilerine uygulanan <strong>deterministik kurallarla</strong> üretilir. Şiddet
          ve güven seviyeleri ayrı hesaplanır; düşük veri kalitesi olayı insan incelemesine işaretler. VisiOnRoute
          kazaları önlediğini iddia etmez; riskli sürüş davranışlarını ve yol güvenliği sinyallerini veriye dayalı ve
          açıklanabilir biçimde görünür kılar.
        </p>
      </Card>
    </div>
  );
}
