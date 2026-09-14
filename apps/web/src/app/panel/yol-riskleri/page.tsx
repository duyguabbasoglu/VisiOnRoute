"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import { Alert, Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, SeverityBadge } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { roadRiskSchema } from "@/lib/schemas";

export default function RoadRisksPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const query = useQuery({
    queryKey: ["road-risks"],
    queryFn: () => apiFetch("/api/v1/road-risks", { schema: z.array(roadRiskSchema) }),
  });
  const rebuild = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/road-risks/rebuild", { method: "POST", schema: z.object({ road_risks: z.number() }) }),
    onSuccess: (data) => {
      setFeedback({ kind: "success", text: `${data.road_risks} yol riski bölgesi hesaplandı.` });
      void queryClient.invalidateQueries({ queryKey: ["road-risks"] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Yol riskleri hesaplanamadı.") }),
  });

  return (
    <div>
      <PageHeader
        title="Yol Riskleri"
        description="Tekrarlanan sert olaylardan çıkarılan yol riski bölgeleri."
        action={
          can(user, "risks.manage") ? (
            <Button variant="secondary" loading={rebuild.isPending} onClick={() => rebuild.mutate()}>
              Yeniden hesapla
            </Button>
          ) : null
        }
      />
      {feedback && (
        <Alert kind={feedback.kind} className="mb-4">
          {feedback.text}
        </Alert>
      )}
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error, "Yol riskleri yüklenemedi.")} onRetry={() => void query.refetch()} />
      ) : !query.data?.length ? (
        <EmptyState message="Henüz yol riski tespit edilmedi. Yeterli olay biriktiğinde yeniden hesaplama ile kümeleme yapılır." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {query.data.map((r) => (
            <Card key={r.id}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-ink-900">Tekrarlanan sert olay bölgesi</span>
                <SeverityBadge severity={r.inferred_severity} />
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
                  <dt className="text-slate-400">Yarıçap</dt>
                  <dd>{Math.round(r.radius_m)} m</dd>
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
