"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { SafetyEventList } from "@/lib/types";
import { Card, PageHeader, StatTile } from "@/components/ui";

const SEVERITY_ORDER = ["critical", "high", "medium", "low"] as const;
const SEVERITY_LABELS: Record<string, string> = {
  critical: "Kritik",
  high: "Yüksek",
  medium: "Orta",
  low: "Düşük",
};

export default function AnalyticsPage() {
  const query = useQuery({
    queryKey: ["analytics-events"],
    queryFn: () => apiFetch<SafetyEventList>("/api/v1/safety-events?limit=200"),
  });

  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const bySeverity = SEVERITY_ORDER.map((sev) => ({
    severity: sev,
    count: items.filter((e) => e.severity === sev).length,
  }));
  const confirmed = items.filter((e) => e.review_status === "confirmed").length;
  const confirmationRate = items.length ? Math.round((confirmed / items.length) * 100) : 0;
  const maxCount = Math.max(1, ...bySeverity.map((b) => b.count));

  return (
    <div>
      <PageHeader
        title="Analizler"
        description="Güvenlik olaylarının dağılımı. Örneklem: son 200 olay."
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatTile label="Toplam olay" value={String(total)} />
        <StatTile label="Örneklemdeki olay" value={String(items.length)} />
        <StatTile
          label="Onay oranı"
          value={`%${confirmationRate}`}
          hint="Onaylanan / örneklemdeki olay"
        />
      </div>

      <Card className="mt-6">
        <h2 className="mb-4 text-sm font-semibold text-ink-900">Şiddet dağılımı</h2>
        <div className="space-y-3">
          {bySeverity.map((b) => (
            <div key={b.severity} className="flex items-center gap-3">
              <span className="w-16 text-sm text-slate-500">
                {SEVERITY_LABELS[b.severity]}
              </span>
              <div className="h-4 flex-1 overflow-hidden rounded bg-slate-100">
                <div
                  className="h-full rounded bg-brand-500"
                  style={{ width: `${(b.count / maxCount) * 100}%` }}
                  role="img"
                  aria-label={`${SEVERITY_LABELS[b.severity]}: ${b.count} olay`}
                />
              </div>
              <span className="w-8 text-right text-sm text-slate-700">{b.count}</span>
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs text-slate-400">
          Not: Bu analiz son 200 olayın örneklemine dayanır ve tam popülasyonu
          temsil etmeyebilir. Sürücüler yalnızca ham olay sayısına göre
          sıralanmaz; normalize risk skoru için sürücü detayına bakın.
        </p>
      </Card>
    </div>
  );
}
