"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { RoadRisk } from "@/lib/types";
import { Card, EmptyState, PageHeader, SeverityBadge } from "@/components/ui";

export default function RoadRisksPage() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["road-risks"],
    queryFn: () => apiFetch<RoadRisk[]>("/api/v1/road-risks"),
  });
  const rebuild = useMutation({
    mutationFn: () =>
      apiFetch<{ road_risks: number }>("/api/v1/road-risks/rebuild", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["road-risks"] }),
  });

  const risks = query.data ?? [];

  return (
    <div>
      <PageHeader
        title="Yol Riskleri"
        description="Tekrarlanan sert olaylardan çıkarılan yol riski bölgeleri."
        action={
          <button
            onClick={() => rebuild.mutate()}
            disabled={rebuild.isPending}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
          >
            {rebuild.isPending ? "Hesaplanıyor…" : "Yeniden hesapla"}
          </button>
        }
      />
      {query.isLoading ? (
        <p className="text-sm text-slate-500">Yükleniyor…</p>
      ) : risks.length === 0 ? (
        <EmptyState message="Henüz yol riski tespit edilmedi. Yeterli olay biriktiğinde 'Yeniden hesapla' ile kümeleme yapılır." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {risks.map((r) => (
            <Card key={r.id}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-ink-900">
                  Tekrarlanan sert olay
                </span>
                <SeverityBadge severity={r.inferred_severity} label={r.inferred_severity} />
              </div>
              <dl className="mt-3 space-y-1 text-sm text-slate-600">
                <div className="flex justify-between">
                  <dt className="text-slate-400">Gözlem sayısı</dt>
                  <dd>{r.observed_count}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Güven</dt>
                  <dd>%{Math.round(r.confidence * 100)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Konum</dt>
                  <dd>
                    {r.center_latitude.toFixed(4)}, {r.center_longitude.toFixed(4)}
                  </dd>
                </div>
              </dl>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
