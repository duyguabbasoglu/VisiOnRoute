"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Alert, Badge, Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, TextField } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { Driver, Paginated } from "@/lib/types";

const DRIVER_STATUS: Record<string, { label: string; tone: "success" | "neutral" | "warning" }> = {
  active: { label: "Etkin", tone: "success" },
  inactive: { label: "Pasif", tone: "neutral" },
  erased: { label: "Silindi (KVKK)", tone: "warning" },
};

export default function DriversPage() {
  const { user } = useAuth();
  const canManage = can(user, "fleet.manage");
  const queryClient = useQueryClient();
  const [externalId, setExternalId] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["drivers"],
    queryFn: () => apiFetch<Paginated<Driver>>("/api/v1/drivers?limit=100"),
  });

  const create = useMutation({
    mutationFn: () =>
      apiFetch<Driver>("/api/v1/drivers", {
        method: "POST",
        body: { external_id: externalId, full_name: fullName },
      }),
    onSuccess: () => {
      setExternalId("");
      setFullName("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["drivers"] });
    },
    onError: (err) => setError(errorMessage(err, "Sürücü eklenemedi.")),
  });

  return (
    <div>
      <PageHeader title="Sürücüler" description="Sürücü kayıtlarını yönetin." />
      {canManage && (
        <Card className="mb-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
            className="flex flex-wrap items-end gap-3"
          >
            <TextField
              label="Dış kimlik"
              required
              value={externalId}
              onChange={(e) => setExternalId(e.target.value)}
              placeholder="SUR-001"
              hint="Telematik/cihaz verisindeki sürücü kimliği."
            />
            <TextField
              label="Ad soyad"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Ahmet Yılmaz"
            />
            <Button type="submit" loading={create.isPending}>
              Sürücü ekle
            </Button>
          </form>
          {error && (
            <Alert kind="error" className="mt-3">
              {error}
            </Alert>
          )}
        </Card>
      )}

      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error, "Sürücüler yüklenemedi.")} />
      ) : query.data && query.data.items.length > 0 ? (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Ad soyad</th>
                <th className="px-4 py-2.5 font-medium">Dış kimlik</th>
                <th className="px-4 py-2.5 font-medium">Durum</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {query.data.items.map((d) => {
                const status = DRIVER_STATUS[d.status] ?? { label: d.status, tone: "neutral" as const };
                return (
                  <tr key={d.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2.5 text-ink-900">{d.full_name}</td>
                    <td className="px-4 py-2.5 text-slate-600">{d.external_id}</td>
                    <td className="px-4 py-2.5">
                      <Badge tone={status.tone}>{status.label}</Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      ) : (
        <EmptyState message="Henüz sürücü eklenmemiş." />
      )}
    </div>
  );
}
