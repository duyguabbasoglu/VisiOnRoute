"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { Paginated, Vehicle } from "@/lib/types";
import { Card, EmptyState, PageHeader, formatDateTime } from "@/components/ui";

export default function VehiclesPage() {
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
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Araç eklenemedi."),
  });

  return (
    <div>
      <PageHeader title="Araçlar" description="Filonuzdaki araçları yönetin." />
      <Card className="mb-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
          className="flex flex-wrap items-end gap-3"
        >
          <div>
            <label className="block text-xs text-slate-500">Dış kimlik (external_id)</label>
            <input
              required
              value={externalId}
              onChange={(e) => setExternalId(e.target.value)}
              placeholder="34ABC123"
              className="mt-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500">Plaka</label>
            <input
              value={plate}
              onChange={(e) => setPlate(e.target.value)}
              placeholder="34 ABC 123"
              className="mt-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={create.isPending}
            className="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
          >
            Araç ekle
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>
      </Card>

      {query.data && query.data.items.length > 0 ? (
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
              {query.data.items.map((v) => (
                <tr key={v.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 text-ink-900">{v.external_id}</td>
                  <td className="px-4 py-2.5 text-slate-600">{v.plate ?? "—"}</td>
                  <td className="px-4 py-2.5 text-slate-600">{v.status}</td>
                  <td className="px-4 py-2.5 text-slate-500">{formatDateTime(v.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <EmptyState message="Henüz araç eklenmemiş. Yukarıdaki formu kullanarak ilk aracınızı ekleyin." />
      )}
    </div>
  );
}
