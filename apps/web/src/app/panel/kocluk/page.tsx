"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatTile,
  TextField,
  formatDateTime,
} from "@/components/ui";
import { apiDownload, apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import {
  coachingActionSchema,
  coachingAssigneeSchema,
  coachingListSchema,
  coachingSummarySchema,
  driverSchema,
  type CoachingAction,
} from "@/lib/schemas";

const STATUS_FILTERS = [
  { value: "", label: "Tüm durumlar" },
  { value: "open", label: "Açık" },
  { value: "in_progress", label: "Devam ediyor" },
  { value: "completed", label: "Tamamlandı" },
  { value: "canceled", label: "İptal edildi" },
];

function coachingStatusTone(status: string): "info" | "warning" | "success" | "neutral" {
  if (status === "open") return "info";
  if (status === "in_progress") return "warning";
  if (status === "completed") return "success";
  return "neutral";
}

export default function CoachingPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState("");
  const [mine, setMine] = useState(false);
  const [overdue, setOverdue] = useState(false);
  const [creating, setCreating] = useState(false);
  const canManage = can(user, "coaching.manage");

  const summary = useQuery({
    queryKey: ["coaching", "summary"],
    queryFn: () => apiFetch("/api/v1/coaching-actions/summary", { schema: coachingSummarySchema }),
  });
  const list = useQuery({
    queryKey: ["coaching", "list", status, mine, overdue],
    queryFn: () => {
      const params = new URLSearchParams({ limit: "100" });
      if (status) params.set("status", status);
      if (mine) params.set("assigned_to_me", "true");
      if (overdue) params.set("overdue", "true");
      return apiFetch(`/api/v1/coaching-actions?${params.toString()}`, { schema: coachingListSchema });
    },
  });

  return (
    <div>
      <PageHeader
        title="Koçluk"
        description="Onaylanan güvenlik olaylarından doğan sürücü koçluğu görevleri."
        action={
          <div className="flex flex-wrap gap-2">
            {can(user, "reports.read") && (
              <Button
                variant="secondary"
                onClick={() => void apiDownload("/api/v1/reports/coaching.csv", "kocluk-gorevleri.csv")}
              >
                CSV indir
              </Button>
            )}
            {canManage && <Button onClick={() => setCreating((v) => !v)}>Yeni görev</Button>}
          </div>
        }
      />

      {summary.data && (
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatTile label="Açık" value={String(summary.data.open)} />
          <StatTile label="Devam eden" value={String(summary.data.in_progress)} />
          <StatTile label="Gecikmiş" value={String(summary.data.overdue)} />
          <StatTile
            label="Son 30 günde tamamlanan"
            value={String(summary.data.completed_last_30_days)}
            hint={
              summary.data.average_days_to_complete != null
                ? `Ortalama ${summary.data.average_days_to_complete} günde`
                : undefined
            }
          />
        </div>
      )}

      {creating && canManage && <CreateCoachingForm onDone={() => setCreating(false)} />}

      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-4">
          <select
            aria-label="Durum filtresi"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
          >
            {STATUS_FILTERS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
            Bana atananlar
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={overdue} onChange={(e) => setOverdue(e.target.checked)} />
            Yalnızca gecikmiş
          </label>
        </div>
      </Card>

      {list.isLoading && <LoadingState />}
      {list.isError && (
        <ErrorState message={errorMessage(list.error, "Koçluk görevleri yüklenemedi.")} onRetry={() => void list.refetch()} />
      )}
      {list.data && list.data.items.length === 0 && (
        <EmptyState message="Filtrelere uyan koçluk görevi yok. Güvenlik olaylarını incelerken “Koçluk atandı” çözümünü seçtiğinizde görevler burada oluşur." />
      )}
      {list.data && list.data.items.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Görev</th>
                <th className="px-4 py-2.5 font-medium">Sürücü</th>
                <th className="px-4 py-2.5 font-medium">Sorumlu</th>
                <th className="px-4 py-2.5 font-medium">Termin</th>
                <th className="px-4 py-2.5 font-medium">Durum</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.items.map((a: CoachingAction) => (
                <tr key={a.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5">
                    <Link href={`/panel/kocluk/${a.id}`} className="text-brand-700 hover:underline">
                      {a.title}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 text-slate-600">{a.driver_name ?? "—"}</td>
                  <td className="px-4 py-2.5 text-slate-600">{a.assignee_name ?? "Atanmadı"}</td>
                  <td className="px-4 py-2.5 text-slate-600">
                    {formatDateTime(a.due_at)} {a.is_overdue && <Badge tone="danger">Gecikmiş</Badge>}
                  </td>
                  <td className="px-4 py-2.5">
                    <Badge tone={coachingStatusTone(a.status)}>{a.status_label}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function CreateCoachingForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [driverId, setDriverId] = useState("");
  const [assignee, setAssignee] = useState("");
  const [due, setDue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const drivers = useQuery({
    queryKey: ["drivers", "all"],
    queryFn: () =>
      apiFetch("/api/v1/drivers?limit=200", {
        schema: z.object({ items: z.array(driverSchema) }),
      }),
  });
  const assignees = useQuery({
    queryKey: ["coaching", "assignees"],
    queryFn: () => apiFetch("/api/v1/coaching-actions/assignees", { schema: z.array(coachingAssigneeSchema) }),
  });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/coaching-actions", {
        method: "POST",
        body: {
          title,
          driver_id: driverId || null,
          assignee_user_id: assignee || null,
          due_at: due ? new Date(due).toISOString() : null,
        },
        schema: coachingActionSchema.extend({ created: z.boolean() }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["coaching"] });
      onDone();
    },
    onError: (err) => setError(errorMessage(err, "Görev oluşturulamadı.")),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    create.mutate();
  }

  return (
    <Card className="mb-6">
      <h2 className="mb-3 text-sm font-semibold text-ink-900">Yeni koçluk görevi</h2>
      <form onSubmit={onSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField label="Başlık" required value={title} onChange={(e) => setTitle(e.target.value)} />
        <div>
          <label htmlFor="coach-driver" className="block text-sm font-medium text-slate-700">
            Sürücü
          </label>
          <select
            id="coach-driver"
            value={driverId}
            onChange={(e) => setDriverId(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">Seçilmedi</option>
            {drivers.data?.items.map((d) => (
              <option key={d.id} value={d.id}>
                {d.full_name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="coach-assignee" className="block text-sm font-medium text-slate-700">
            Sorumlu
          </label>
          <select
            id="coach-assignee"
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">Atanmadı</option>
            {assignees.data?.map((a) => (
              <option key={a.user_id} value={a.user_id}>
                {a.full_name} ({a.role_label})
              </option>
            ))}
          </select>
        </div>
        <TextField label="Termin" type="datetime-local" value={due} hint="Boş bırakılırsa 7 gün sonrası." onChange={(e) => setDue(e.target.value)} />
        {error && <Alert kind="error" className="sm:col-span-2">{error}</Alert>}
        <div className="flex gap-2 sm:col-span-2">
          <Button type="submit" loading={create.isPending}>
            Oluştur
          </Button>
          <Button variant="ghost" onClick={onDone}>
            Vazgeç
          </Button>
        </div>
      </form>
    </Card>
  );
}
