"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
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
import type { Paginated, Vehicle } from "@/lib/types";

const VEHICLE_STATUS: Record<string, { label: string; tone: "success" | "neutral" | "warning" }> = {
  active: { label: "Etkin", tone: "success" },
  inactive: { label: "Pasif", tone: "neutral" },
  maintenance: { label: "Bakımda", tone: "warning" },
};

export default function VehiclesPage() {
  const { user } = useAuth();
  const canManage = can(user, "fleet.manage");
  const queryClient = useQueryClient();
  const [externalId, setExternalId] = useState("");
  const [plate, setPlate] = useState("");
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => apiFetch<Paginated<Vehicle>>("/api/v1/vehicles?limit=100"),
  });

  const create = useMutation({
    mutationFn: () =>
      apiFetch<Vehicle>("/api/v1/vehicles", {
        method: "POST",
        body: { external_id: externalId, plate: plate || null },
      }),
    onSuccess: () => {
      setExternalId("");
      setPlate("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["vehicles"] });
    },
    onError: (err) => setError(errorMessage(err, "Araç eklenemedi.")),
  });

  return (
    <div>
      <PageHeader title="Araçlar" description="Filonuzdaki araçları yönetin." />
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
              placeholder="34ABC123"
              hint="Telemetri verisindeki araç kimliği."
            />
            <TextField label="Plaka" value={plate} onChange={(e) => setPlate(e.target.value)} placeholder="34 ABC 123" />
            <Button type="submit" loading={create.isPending}>
              Araç ekle
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
        <ErrorState message={errorMessage(query.error, "Araçlar yüklenemedi.")} />
      ) : query.data && query.data.items.length > 0 ? (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Dış kimlik</th>
                <th className="px-4 py-2.5 font-medium">Plaka</th>
                <th className="px-4 py-2.5 font-medium">Durum</th>
                <th className="px-4 py-2.5 font-medium">Eklenme</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {query.data.items.map((v) => {
                const status = VEHICLE_STATUS[v.status] ?? { label: v.status, tone: "neutral" as const };
                return (
                  <tr key={v.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2.5 text-ink-900">{v.external_id}</td>
                    <td className="px-4 py-2.5 text-slate-600">{v.plate ?? "—"}</td>
                    <td className="px-4 py-2.5">
                      <Badge tone={status.tone}>{status.label}</Badge>
                    </td>
                    <td className="px-4 py-2.5 text-slate-500">{formatDateTime(v.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      ) : (
        <EmptyState
          message={
            canManage
              ? "Henüz araç eklenmemiş. Yukarıdaki formu kullanarak ilk aracınızı ekleyin."
              : "Henüz araç eklenmemiş."
          }
        />
      )}
    </div>
  );
}
