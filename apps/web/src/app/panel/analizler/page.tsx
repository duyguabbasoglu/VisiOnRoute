"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card, ErrorState, LoadingState, PageHeader, SEVERITY_LABELS, StatTile } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { analyticsSummarySchema } from "@/lib/schemas";

const SEVERITY_ORDER = ["critical", "high", "medium", "low"] as const;
const WINDOWS = [7, 30, 90, 365];

export default function AnalyticsPage() {
  const [windowDays, setWindowDays] = useState(30);
  const summary = useQuery({
    queryKey: ["analytics-summary", windowDays],
    queryFn: () =>
      apiFetch(`/api/v1/analytics/summary?window_days=${windowDays}`, { schema: analyticsSummarySchema }),
  });

  return (
    <div>
      <PageHeader
        title="Analizler"
        description="Seçili dönemdeki tüm güvenlik olayları ve sürüş mesafesi."
        action={
          <label className="text-sm text-slate-600">
            <span className="sr-only">Dönem</span>
            <select
              value={windowDays}
              onChange={(e) => setWindowDays(Number(e.target.value))}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            >
              {WINDOWS.map((w) => (
                <option key={w} value={w}>
                  Son {w} gün
                </option>
              ))}
            </select>
          </label>
        }
      />
      {summary.isLoading ? (
        <LoadingState />
      ) : summary.isError || !summary.data ? (
        <ErrorState message={errorMessage(summary.error, "Analizler yüklenemedi.")} onRetry={() => void summary.refetch()} />
      ) : (
        <SummaryView data={summary.data} />
      )}
    </div>
  );
}

function SummaryView({
  data,
}: {
  data: {
    total_events: number;
    events_by_severity: Record<string, number>;
    total_distance_km: number;
    events_per_100km: number | null;
    confirmation_rate: number | null;
    data_note_tr: string;
  };
}) {
  const counts = SEVERITY_ORDER.map((severity) => ({ severity, count: data.events_by_severity[severity] ?? 0 }));
  const maxCount = Math.max(1, ...counts.map((c) => c.count));
  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Toplam olay" value={String(data.total_events)} />
        <StatTile label="Sürüş mesafesi" value={`${data.total_distance_km.toLocaleString("tr-TR")} km`} />
        <StatTile
          label="100 km başına olay"
          value={data.events_per_100km != null ? data.events_per_100km.toLocaleString("tr-TR") : "—"}
          hint="Mesafe verisi yoksa hesaplanmaz"
        />
        <StatTile
          label="Onay oranı"
          value={data.confirmation_rate != null ? `%${Math.round(data.confirmation_rate * 100)}` : "—"}
          hint="Onaylanan / incelenen olay"
        />
      </div>
      <Card className="mt-6">
        <h2 className="mb-4 text-sm font-semibold text-ink-900">Şiddet dağılımı</h2>
        <div className="space-y-3">
          {counts.map((c) => (
            <div key={c.severity} className="flex items-center gap-3">
              <span className="w-16 text-sm text-slate-500">{SEVERITY_LABELS[c.severity] ?? c.severity}</span>
              <div className="h-4 flex-1 overflow-hidden rounded bg-slate-100">
                <div
                  className="h-full rounded bg-brand-500"
                  style={{ width: `${(c.count / maxCount) * 100}%` }}
                  role="img"
                  aria-label={`${SEVERITY_LABELS[c.severity] ?? c.severity}: ${c.count} olay`}
                />
              </div>
              <span className="w-10 text-right text-sm text-slate-700">{c.count}</span>
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs text-slate-500">{data.data_note_tr}</p>
        <p className="mt-1 text-xs text-slate-400">
          Sürücüler yalnızca ham olay sayısına göre sıralanmamalıdır; olay sayıları sürüş mesafesiyle birlikte
          değerlendirilmelidir.
        </p>
      </Card>
    </>
  );
}
