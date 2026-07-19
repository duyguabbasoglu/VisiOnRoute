"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import type { LiveVehicle, RoadRisk, SafetyEventList } from "@/lib/types";
import { Card, PageHeader, SeverityBadge, StatTile, formatDateTime } from "@/components/ui";

export default function OverviewPage() {
  const events = useQuery({
    queryKey: ["safety-events", "overview"],
    queryFn: () => apiFetch<SafetyEventList>("/api/v1/safety-events?limit=5"),
  });
  const live = useQuery({
    queryKey: ["live", "overview"],
    queryFn: () => apiFetch<LiveVehicle[]>("/api/v1/operations/live"),
  });
  const risks = useQuery({
    queryKey: ["road-risks", "overview"],
    queryFn: () => apiFetch<RoadRisk[]>("/api/v1/road-risks"),
  });

  const pendingCount =
    events.data?.items.filter((e) => e.review_status === "pending").length ?? 0;

  return (
    <div>
      <PageHeader
        title="Genel Bakış"
        description="Filonuzun güvenlik durumuna hızlı bir bakış."
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Toplam güvenlik olayı"
          value={events.isLoading ? "…" : String(events.data?.total ?? 0)}
          hint="Tüm zamanlar"
        />
        <StatTile
          label="İnceleme bekleyen (son 5)"
          value={events.isLoading ? "…" : String(pendingCount)}
        />
        <StatTile
          label="Aktif seferler"
          value={live.isLoading ? "…" : String(live.data?.length ?? 0)}
        />
        <StatTile
          label="Yol riski bölgesi"
          value={risks.isLoading ? "…" : String(risks.data?.length ?? 0)}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
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
                <li key={event.id} className="flex items-center justify-between py-2.5">
                  <div>
                    <p className="text-sm text-ink-900">{event.event_label}</p>
                    <p className="text-xs text-slate-400">
                      {formatDateTime(event.occurred_at)}
                    </p>
                  </div>
                  <SeverityBadge severity={event.severity} label={event.severity_label} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="py-6 text-center text-sm text-slate-400">
              Henüz güvenlik olayı yok.
            </p>
          )}
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-ink-900">Metodoloji</h2>
          <p className="text-sm text-slate-600">
            Güvenlik olayları, telemetri verilerine uygulanan{" "}
            <strong>deterministik kurallarla</strong> üretilir. Şiddet ve güven
            seviyeleri ayrı hesaplanır; düşük veri kalitesi olayı insan
            incelemesine işaretler. Bu platform kazaları önlediğini iddia etmez;
            riskleri veriye dayalı ve açıklanabilir biçimde görünür kılar.
          </p>
        </Card>
      </div>
    </div>
  );
}
