"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmButton,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  TextField,
  formatDateTime,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import {
  apiClientSchema,
  apiTokenSummarySchema,
  dataSourceSchema,
  issuedApiTokenSchema,
} from "@/lib/schemas";

const API_SCOPES = [
  { value: "ingest:write", label: "Telemetri gönderimi" },
  { value: "evidence:write", label: "Kanıt medyası yükleme (kamera)" },
];
const SCOPE_LABELS: Record<string, string> = Object.fromEntries(API_SCOPES.map((s) => [s.value, s.label]));

export default function IntegrationsPage() {
  const { user } = useAuth();
  const canManage = can(user, "integrations.manage");
  return (
    <div>
      <PageHeader
        title="Entegrasyonlar"
        description="Veri kaynaklarını tanımlayın, cihaz ve kameralar için kapsamlı API anahtarları yönetin."
      />
      {canManage && <NewDataSource />}
      {canManage && <NewApiKey />}
      <ApiClients canManage={canManage} />
      <DataSources />
    </div>
  );
}

function NewDataSource() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [sourceKey, setSourceKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/integrations/data-sources", {
        method: "POST",
        body: { name, source_key: sourceKey, kind: "rest" },
        schema: dataSourceSchema,
      }),
    onSuccess: () => {
      setName("");
      setSourceKey("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["data-sources"] });
    },
    onError: (err) => setError(errorMessage(err, "Veri kaynağı oluşturulamadı.")),
  });

  return (
    <Card className="mb-4">
      <h2 className="mb-3 text-sm font-semibold text-ink-900">Yeni veri kaynağı</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
        className="flex flex-wrap items-end gap-3"
      >
        <TextField label="Ad" required value={name} onChange={(e) => setName(e.target.value)} />
        <TextField
          label="Kaynak anahtarı"
          required
          value={sourceKey}
          onChange={(e) => setSourceKey(e.target.value)}
          placeholder="telematik-1"
          hint="Küçük harf, rakam ve tire."
        />
        <Button type="submit" loading={create.isPending}>
          Oluştur
        </Button>
      </form>
      {error && (
        <Alert kind="error" className="mt-3">
          {error}
        </Alert>
      )}
    </Card>
  );
}

function NewApiKey() {
  const queryClient = useQueryClient();
  const [clientName, setClientName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["ingest:write"]);
  const [issuedKey, setIssuedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: async () => {
      const client = await apiFetch("/api/v1/integrations/clients", {
        method: "POST",
        body: { name: clientName.trim() || "Panel üzerinden oluşturulan istemci" },
        schema: apiClientSchema,
      });
      return apiFetch(`/api/v1/integrations/clients/${client.id}/tokens`, {
        method: "POST",
        body: { scopes },
        schema: issuedApiTokenSchema,
      });
    },
    onSuccess: (data) => {
      setError(null);
      setClientName("");
      setIssuedKey(data.api_key);
      void queryClient.invalidateQueries({ queryKey: ["api-clients"] });
    },
    onError: (err) => setError(errorMessage(err, "API anahtarı üretilemedi.")),
  });

  return (
    <Card className="mb-4">
      <h2 className="text-sm font-semibold text-ink-900">API anahtarı</h2>
      <p className="text-xs text-slate-500">
        Anahtara yalnızca gereken yetkileri verin. Anahtar yalnızca bir kez gösterilir.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <TextField
          label="İstemci adı"
          value={clientName}
          maxLength={200}
          placeholder="Ör. Kabin kamerası 12"
          onChange={(e) => setClientName(e.target.value)}
        />
        <fieldset className="flex flex-wrap gap-4 text-sm text-slate-700">
          <legend className="sr-only">Anahtar kapsamları</legend>
          {API_SCOPES.map((scope) => (
            <label key={scope.value} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={scopes.includes(scope.value)}
                onChange={(e) =>
                  setScopes((current) =>
                    e.target.checked ? [...current, scope.value] : current.filter((item) => item !== scope.value),
                  )
                }
              />
              {scope.label}
            </label>
          ))}
        </fieldset>
        <Button variant="secondary" onClick={() => create.mutate()} loading={create.isPending} disabled={scopes.length === 0}>
          Anahtar üret
        </Button>
      </div>
      {error && (
        <Alert kind="error" className="mt-3">
          {error}
        </Alert>
      )}
      {issuedKey && (
        <div className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          <p className="font-medium">Anahtar yalnızca bir kez gösterilir:</p>
          <code aria-label="Yeni API anahtarı" className="mt-1 block break-all font-mono text-xs">
            {issuedKey}
          </code>
          <Button variant="ghost" className="mt-2 px-2 py-1 text-xs" onClick={() => setIssuedKey(null)}>
            Kaydettim, gizle
          </Button>
        </div>
      )}
    </Card>
  );
}

function ApiClients({ canManage }: { canManage: boolean }) {
  const clients = useQuery({
    queryKey: ["api-clients"],
    queryFn: () => apiFetch("/api/v1/integrations/clients", { schema: z.array(apiClientSchema) }),
  });
  return (
    <Card className="mb-4">
      <h2 className="mb-3 text-sm font-semibold text-ink-900">API istemcileri ve anahtarlar</h2>
      {clients.isLoading ? (
        <LoadingState />
      ) : clients.isError ? (
        <ErrorState message={errorMessage(clients.error, "API istemcileri yüklenemedi.")} />
      ) : !clients.data?.length ? (
        <EmptyState message="Henüz API istemcisi yok." />
      ) : (
        <ul className="space-y-3">
          {clients.data.map((client) => (
            <li key={client.id} className="rounded-lg border border-slate-200 p-3">
              <p className="text-sm font-medium text-ink-900">{client.name}</p>
              <p className="text-xs text-slate-500">Oluşturulma: {formatDateTime(client.created_at)}</p>
              <ClientTokens clientId={client.id} canManage={canManage} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ClientTokens({ clientId, canManage }: { clientId: string; canManage: boolean }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const tokens = useQuery({
    queryKey: ["api-tokens", clientId],
    queryFn: () =>
      apiFetch(`/api/v1/integrations/clients/${clientId}/tokens`, { schema: z.array(apiTokenSummarySchema) }),
  });
  const revoke = useMutation({
    mutationFn: (tokenId: string) => apiFetch(`/api/v1/integrations/tokens/${tokenId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["api-tokens", clientId] }),
    onError: (err) => setError(errorMessage(err, "Anahtar iptal edilemedi.")),
  });

  if (tokens.isLoading) return <LoadingState />;
  if (tokens.isError) return <ErrorState message={errorMessage(tokens.error, "Anahtarlar yüklenemedi.")} />;
  if (!tokens.data?.length) return <p className="mt-2 text-xs text-slate-500">Bu istemcinin anahtarı yok.</p>;
  return (
    <div className="mt-2 overflow-x-auto">
      {error && (
        <Alert kind="error" className="mb-2">
          {error}
        </Alert>
      )}
      <table className="w-full text-xs">
        <thead className="text-left text-slate-500">
          <tr>
            <th className="py-1 pr-3">Önek</th>
            <th className="py-1 pr-3">Kapsam</th>
            <th className="py-1 pr-3">Son kullanım</th>
            <th className="py-1 pr-3">Durum</th>
            <th className="py-1" />
          </tr>
        </thead>
        <tbody>
          {tokens.data.map((token) => (
            <tr key={token.id} className="border-t border-slate-100">
              <td className="py-1 pr-3 font-mono">{token.prefix}…</td>
              <td className="py-1 pr-3">{token.scopes.map((s) => SCOPE_LABELS[s] ?? s).join(", ")}</td>
              <td className="py-1 pr-3">{formatDateTime(token.last_used_at)}</td>
              <td className="py-1 pr-3">
                {token.revoked_at ? (
                  <Badge tone="neutral">İptal edildi</Badge>
                ) : token.expires_at && new Date(token.expires_at) < new Date() ? (
                  <Badge tone="warning">Süresi doldu</Badge>
                ) : (
                  <Badge tone="success">Etkin</Badge>
                )}
              </td>
              <td className="py-1 text-right">
                {canManage && !token.revoked_at && (
                  <ConfirmButton label="İptal et" onConfirm={() => revoke.mutate(token.id)} loading={revoke.isPending} />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DataSources() {
  const sources = useQuery({
    queryKey: ["data-sources"],
    queryFn: () => apiFetch("/api/v1/integrations/data-sources", { schema: z.array(dataSourceSchema) }),
  });
  return (
    <>
      <h2 className="mb-2 text-sm font-semibold text-ink-900">Kaynak sağlığı</h2>
      {sources.isLoading ? (
        <LoadingState />
      ) : sources.isError ? (
        <ErrorState message={errorMessage(sources.error, "Veri kaynakları yüklenemedi.")} />
      ) : sources.data && sources.data.length > 0 ? (
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
                  <td className="px-4 py-2.5 font-mono text-xs text-slate-500">{s.source_key}</td>
                  <td className="px-4 py-2.5 text-emerald-700">{s.accepted_count}</td>
                  <td className="px-4 py-2.5 text-red-600">{s.rejected_count}</td>
                  <td className="px-4 py-2.5 text-slate-500">{s.duplicate_count}</td>
                  <td className="px-4 py-2.5 text-slate-500">{formatDateTime(s.last_event_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <EmptyState message="Henüz veri kaynağı tanımlanmamış." />
      )}
    </>
  );
}
