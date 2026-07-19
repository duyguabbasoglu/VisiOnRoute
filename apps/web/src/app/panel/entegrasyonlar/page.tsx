"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { Card, EmptyState, PageHeader, formatDateTime } from "@/components/ui";

interface DataSource {
  id: string;
  name: string;
  source_key: string;
  kind: string;
  status: string;
  last_event_at: string | null;
  accepted_count: number;
  rejected_count: number;
  duplicate_count: number;
}

export default function IntegrationsPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [sourceKey, setSourceKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [issuedKey, setIssuedKey] = useState<string | null>(null);

  const sources = useQuery({
    queryKey: ["data-sources"],
    queryFn: () => apiFetch<DataSource[]>("/api/v1/integrations/data-sources"),
  });

  const createSource = useMutation({
    mutationFn: () =>
      apiFetch<DataSource>("/api/v1/integrations/data-sources", {
        method: "POST",
        body: { name, source_key: sourceKey, kind: "rest" },
      }),
    onSuccess: () => {
      setName("");
      setSourceKey("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["data-sources"] });
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Veri kaynağı oluşturulamadı."),
  });

  const createKey = useMutation({
    mutationFn: async () => {
      const client = await apiFetch<{ id: string }>("/api/v1/integrations/clients", {
        method: "POST",
        body: { name: "Panel üzerinden oluşturulan istemci" },
      });
      return apiFetch<{ api_key: string }>(
        `/api/v1/integrations/clients/${client.id}/tokens`,
        { method: "POST", body: { scopes: ["ingest:write"] } },
      );
    },
    onSuccess: (data) => setIssuedKey(data.api_key),
  });

  return (
    <div>
      <PageHeader
        title="Entegrasyonlar"
        description="Veri kaynaklarını tanımlayın ve veri alımı için API anahtarı üretin."
      />

      <Card className="mb-4">
        <h2 className="mb-3 text-sm font-semibold text-ink-900">Yeni veri kaynağı</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createSource.mutate();
          }}
          className="flex flex-wrap items-end gap-3"
        >
          <div>
            <label className="block text-xs text-slate-500">Ad</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500">
              Kaynak anahtarı (küçük harf, tire)
            </label>
            <input
              required
              value={sourceKey}
              onChange={(e) => setSourceKey(e.target.value)}
              placeholder="telematik-1"
              className="mt-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={createSource.isPending}
            className="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
          >
            Oluştur
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>
      </Card>

      <Card className="mb-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-ink-900">API anahtarı</h2>
            <p className="text-xs text-slate-500">
              Cihazlarınızın veri göndermesi için `ingest:write` kapsamlı anahtar.
            </p>
          </div>
          <button
            onClick={() => createKey.mutate()}
            disabled={createKey.isPending}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
          >
            Anahtar üret
          </button>
        </div>
        {issuedKey && (
          <div className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
            <p className="font-medium">Anahtar yalnızca bir kez gösterilir:</p>
            <code className="mt-1 block break-all font-mono text-xs">{issuedKey}</code>
          </div>
        )}
      </Card>

      <h2 className="mb-2 text-sm font-semibold text-ink-900">Kaynak sağlığı</h2>
      {sources.data && sources.data.length > 0 ? (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Ad</th>
                <th className="px-4 py-2.5 font-medium">Anahtar</th>
                <th className="px-4 py-2.5 font-medium">Kabul</th>
                <th className="px-4 py-2.5 font-medium">Red</th>
                <th className="px-4 py-2.5 font-medium">Kopya</th>
                <th className="px-4 py-2.5 font-medium">Son olay</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {sources.data.map((s) => (
                <tr key={s.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 text-ink-900">{s.name}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-slate-500">
                    {s.source_key}
                  </td>
                  <td className="px-4 py-2.5 text-emerald-700">{s.accepted_count}</td>
                  <td className="px-4 py-2.5 text-red-600">{s.rejected_count}</td>
                  <td className="px-4 py-2.5 text-slate-500">{s.duplicate_count}</td>
                  <td className="px-4 py-2.5 text-slate-500">
                    {formatDateTime(s.last_event_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <EmptyState message="Henüz veri kaynağı tanımlanmamış." />
      )}
    </div>
  );
}
