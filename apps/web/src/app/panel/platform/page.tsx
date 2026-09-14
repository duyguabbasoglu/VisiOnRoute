"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import { Alert, Button, Card, ErrorState, LoadingState, PageHeader, StatTile } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { platformHealthSchema, platformOrgSchema, platformPlanSchema } from "@/lib/schemas";

export default function PlatformPage() {
  const { user } = useAuth();
  if (!user?.is_platform_admin) {
    return (
      <div>
        <PageHeader title="Platform Yönetimi" />
        <Alert kind="warning">Bu sayfa yalnızca platform yöneticileri içindir.</Alert>
      </div>
    );
  }
  return (
    <div className="max-w-6xl">
      <PageHeader
        title="Platform Yönetimi"
        description="Kuyruk sağlığı ve organizasyon abonelikleri. Faturalama manueldir; plan ataması aboneliği etkinleştirir."
      />
      <Health />
      <Organizations />
    </div>
  );
}

function Health() {
  const health = useQuery({
    queryKey: ["platform-health"],
    queryFn: () => apiFetch("/api/v1/platform/health", { schema: platformHealthSchema }),
    refetchInterval: 30_000,
  });
  if (health.isLoading) return <LoadingState />;
  if (health.isError || !health.data) {
    return <ErrorState message={errorMessage(health.error, "Sağlık bilgileri yüklenemedi.")} />;
  }
  const h = health.data;
  return (
    <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-6">
      <StatTile label="Outbox bekleyen" value={String(h.outbox_pending)} />
      <StatTile label="Outbox ölü" value={String(h.outbox_dead_letter)} />
      <StatTile label="Karantina" value={String(h.ingest_quarantined)} />
      <StatTile label="Webhook ölü" value={String(h.webhook_dead_letter)} />
      <StatTile label="E-posta bekleyen" value={String(h.email_pending)} />
      <StatTile label="E-posta ölü" value={String(h.email_dead_letter)} />
    </div>
  );
}

const SUBSCRIPTION_LABELS: Record<string, string> = {
  trial: "Deneme",
  active: "Etkin",
  past_due: "Ödeme bekleniyor",
  canceled: "İptal",
};

function Organizations() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const orgs = useQuery({
    queryKey: ["platform-orgs"],
    queryFn: () => apiFetch("/api/v1/platform/organizations", { schema: z.array(platformOrgSchema) }),
  });
  const plans = useQuery({
    queryKey: ["platform-plans"],
    queryFn: () => apiFetch("/api/v1/platform/plans", { schema: z.array(platformPlanSchema) }),
  });
  const changePlan = useMutation({
    mutationFn: ({ orgId, planKey }: { orgId: string; planKey: string }) =>
      apiFetch(`/api/v1/platform/organizations/${orgId}/plan`, {
        method: "POST",
        body: { plan_key: planKey },
        schema: platformOrgSchema,
      }),
    onSuccess: (org) => {
      setFeedback({ kind: "success", text: `${org.name}: plan güncellendi, abonelik etkin.` });
      void queryClient.invalidateQueries({ queryKey: ["platform-orgs"] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Plan değiştirilemedi.") }),
  });

  if (orgs.isLoading || plans.isLoading) return <LoadingState />;
  if (orgs.isError || plans.isError) {
    return <ErrorState message={errorMessage(orgs.error ?? plans.error, "Organizasyonlar yüklenemedi.")} />;
  }
  const planNames = new Map((plans.data ?? []).map((p) => [p.key, p.name_tr]));

  return (
    <Card className="overflow-x-auto">
      <h2 className="mb-3 text-sm font-semibold text-ink-900">Organizasyonlar</h2>
      {feedback && (
        <Alert kind={feedback.kind} className="mb-3">
          {feedback.text}
        </Alert>
      )}
      <table className="w-full text-sm">
        <thead className="border-b border-slate-200 text-left text-xs text-slate-500">
          <tr>
            <th className="py-2 pr-3">Organizasyon</th>
            <th className="py-2 pr-3">Üye</th>
            <th className="py-2 pr-3">Plan</th>
            <th className="py-2 pr-3">Abonelik</th>
            <th className="py-2">Plan ata</th>
          </tr>
        </thead>
        <tbody>
          {(orgs.data ?? []).map((org) => {
            const planKey = selected[org.id] ?? org.plan_key ?? "";
            return (
              <tr key={org.id} className="border-b border-slate-100">
                <td className="py-2 pr-3">
                  <span className="block text-ink-900">{org.name}</span>
                  <span className="text-xs text-slate-500">{org.slug}</span>
                </td>
                <td className="py-2 pr-3">{org.member_count}</td>
                <td className="py-2 pr-3">{org.plan_key ? (planNames.get(org.plan_key) ?? org.plan_key) : "—"}</td>
                <td className="py-2 pr-3">
                  {org.subscription_status ? (SUBSCRIPTION_LABELS[org.subscription_status] ?? org.subscription_status) : "—"}
                </td>
                <td className="py-2">
                  <div className="flex items-center gap-2">
                    <select
                      aria-label={`${org.name} planı`}
                      value={planKey}
                      onChange={(e) => setSelected((current) => ({ ...current, [org.id]: e.target.value }))}
                      className="rounded-lg border border-slate-300 px-2 py-1 text-sm"
                    >
                      <option value="">Seçin…</option>
                      {(plans.data ?? []).map((p) => (
                        <option key={p.key} value={p.key}>
                          {p.name_tr}
                        </option>
                      ))}
                    </select>
                    <Button
                      variant="secondary"
                      className="px-2 py-1 text-xs"
                      disabled={!planKey}
                      loading={changePlan.isPending && changePlan.variables?.orgId === org.id}
                      onClick={() => changePlan.mutate({ orgId: org.id, planKey })}
                    >
                      Uygula
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
