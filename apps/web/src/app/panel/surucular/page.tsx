"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { Driver, Paginated } from "@/lib/types";
import { Card, EmptyState, PageHeader } from "@/components/ui";

export default function DriversPage() {
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
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Sürücü eklenemedi."),
  });

  return (
    <div>
      <PageHeader title="Sürücüler" description="Sürücü kayıtlarını yönetin." />
      <Card className="mb-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
          className="flex flex-wrap items-end gap-3"
        >
          <div>
            <label className="block text-xs text-slate-500">Dış kimlik</label>
            <input
              required
              value={externalId}
              onChange={(e) => setExternalId(e.target.value)}
              placeholder="SUR-001"
              className="mt-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500">Ad soyad</label>
            <input
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Ahmet Yılmaz"
              className="mt-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={create.isPending}
            className="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
          >
            Sürücü ekle
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>
      </Card>

      {query.data && query.data.items.length > 0 ? (
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
              {query.data.items.map((d) => (
                <tr key={d.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 text-ink-900">{d.full_name}</td>
                  <td className="px-4 py-2.5 text-slate-600">{d.external_id}</td>
                  <td className="px-4 py-2.5 text-slate-600">{d.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <EmptyState message="Henüz sürücü eklenmemiş." />
      )}
    </div>
  );
}
