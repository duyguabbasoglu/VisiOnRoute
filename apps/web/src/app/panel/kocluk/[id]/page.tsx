"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  Card,
  ErrorState,
  LoadingState,
  PageHeader,
  TextField,
  formatDateTime,
} from "@/components/ui";
import { ApiError, apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import {
  COACHING_OUTCOMES,
  coachingActionSchema,
  coachingAssigneeSchema,
  type CoachingAction,
} from "@/lib/schemas";

function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function CoachingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canManage = can(user, "coaching.manage");
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const query = useQuery({
    queryKey: ["coaching", "detail", id],
    queryFn: () => apiFetch(`/api/v1/coaching-actions/${id}`, { schema: coachingActionSchema }),
  });

  const onSaved = (text: string) => (data: CoachingAction) => {
    queryClient.setQueryData(["coaching", "detail", id], data);
    void queryClient.invalidateQueries({ queryKey: ["coaching", "list"] });
    void queryClient.invalidateQueries({ queryKey: ["coaching", "summary"] });
    setFeedback({ kind: "success", text });
  };
  const onError = (err: unknown) => setFeedback({ kind: "error", text: errorMessage(err, "İşlem tamamlanamadı.") });

  const start = useMutation({
    mutationFn: () => apiFetch(`/api/v1/coaching-actions/${id}/start`, { method: "POST", schema: coachingActionSchema }),
    onSuccess: onSaved("Görev başlatıldı."),
    onError,
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="space-y-3">
        <ErrorState message={notFound ? "Koçluk görevi bulunamadı." : errorMessage(query.error, "Görev yüklenemedi.")} />
        <Link href="/panel/kocluk" className="text-sm text-brand-700 hover:underline">
          ← Koçluk görevlerine dön
        </Link>
      </div>
    );
  }

  const action = query.data;
  const active = action.status === "open" || action.status === "in_progress";

  return (
    <div className="max-w-4xl">
      <Link href="/panel/kocluk" className="text-sm text-brand-600 hover:underline">
        ← Koçluk
      </Link>
      <PageHeader
        title={action.title}
        description={action.description ?? undefined}
        action={
          <div className="flex items-center gap-2">
            {action.is_overdue && <Badge tone="danger">Gecikmiş</Badge>}
            <Badge tone={action.status === "completed" ? "success" : action.status === "canceled" ? "neutral" : "info"}>
              {action.status_label}
            </Badge>
          </div>
        }
      />

      {feedback && (
        <Alert kind={feedback.kind} className="mb-4">
          {feedback.text}
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-ink-900">Ayrıntılar</h2>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            <Item label="Sürücü" value={action.driver_name ?? "—"} />
            <Item label="Sorumlu" value={action.assignee_name ?? "Atanmadı"} />
            <Item label="Termin" value={formatDateTime(action.due_at)} />
            <Item label="Oluşturan" value={action.created_by_name ?? "—"} />
            <Item label="Oluşturulma" value={formatDateTime(action.created_at)} />
            <Item label="Başlama" value={formatDateTime(action.started_at)} />
            {action.completed_at && <Item label="Tamamlanma" value={formatDateTime(action.completed_at)} />}
            {action.outcome_label && <Item label="Sonuç" value={action.outcome_label} />}
            {action.canceled_at && <Item label="İptal nedeni" value={action.cancel_reason ?? "—"} />}
          </dl>
          {action.safety_event_id && (
            <p className="mt-4 text-sm">
              İlgili olay:{" "}
              <Link href={`/panel/olaylar/${action.safety_event_id}`} className="text-brand-700 hover:underline">
                {action.event_label ?? "Güvenlik olayı"} ({formatDateTime(action.event_occurred_at)})
              </Link>
            </p>
          )}
          {action.notes && (
            <div className="mt-4">
              <p className="text-xs text-slate-400">Notlar</p>
              <p className="whitespace-pre-wrap text-sm text-ink-900">{action.notes}</p>
            </div>
          )}
          {action.outcome_notes && (
            <div className="mt-4">
              <p className="text-xs text-slate-400">Sonuç notu</p>
              <p className="whitespace-pre-wrap text-sm text-ink-900">{action.outcome_notes}</p>
            </div>
          )}
        </Card>

        <div className="space-y-6">
          {canManage && active && action.status === "open" && (
            <Card>
              <h2 className="mb-2 text-sm font-semibold text-ink-900">Görevi başlat</h2>
              <p className="mb-3 text-sm text-slate-600">
                Başlattığınızda görev size atanır (sorumlu yoksa).
              </p>
              <Button loading={start.isPending} onClick={() => start.mutate()}>
                Başlat
              </Button>
            </Card>
          )}
          {canManage && active && <CompleteCard id={id} onSaved={onSaved("Görev tamamlandı.")} onError={onError} />}
          {canManage && active && <CancelCard id={id} onSaved={onSaved("Görev iptal edildi.")} onError={onError} />}
        </div>
      </div>

      {canManage && active && (
        <EditCard action={action} onSaved={onSaved("Değişiklikler kaydedildi.")} onError={onError} />
      )}
    </div>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className="text-ink-900">{value}</dd>
    </div>
  );
}

type Handlers = { onSaved: (data: CoachingAction) => void; onError: (err: unknown) => void };

function CompleteCard({ id, onSaved, onError }: { id: string } & Handlers) {
  const [outcome, setOutcome] = useState("coached");
  const [notes, setNotes] = useState("");
  const complete = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/coaching-actions/${id}/complete`, {
        method: "POST",
        body: { outcome, outcome_notes: notes || null },
        schema: coachingActionSchema,
      }),
    onSuccess: onSaved,
    onError,
  });
  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink-900">Tamamla</h2>
      <label htmlFor="coach-outcome" className="block text-sm font-medium text-slate-700">
        Sonuç
      </label>
      <select
        id="coach-outcome"
        value={outcome}
        onChange={(e) => setOutcome(e.target.value)}
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
      >
        {COACHING_OUTCOMES.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <label htmlFor="coach-outcome-notes" className="mt-3 block text-sm font-medium text-slate-700">
        Sonuç notu
      </label>
      <textarea
        id="coach-outcome-notes"
        rows={3}
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
      />
      <Button className="mt-3" loading={complete.isPending} onClick={() => complete.mutate()}>
        Tamamlandı olarak işaretle
      </Button>
    </Card>
  );
}

function CancelCard({ id, onSaved, onError }: { id: string } & Handlers) {
  const [reason, setReason] = useState("");
  const cancel = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/coaching-actions/${id}/cancel`, {
        method: "POST",
        body: { reason },
        schema: coachingActionSchema,
      }),
    onSuccess: onSaved,
    onError,
  });
  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink-900">İptal et</h2>
      <TextField label="İptal nedeni" value={reason} onChange={(e) => setReason(e.target.value)} />
      <Button
        variant="secondary"
        className="mt-3"
        disabled={reason.trim().length < 3}
        loading={cancel.isPending}
        onClick={() => cancel.mutate()}
      >
        Görevi iptal et
      </Button>
    </Card>
  );
}

function EditCard({ action, onSaved, onError }: { action: CoachingAction } & Handlers) {
  const [assignee, setAssignee] = useState(action.assignee_user_id ?? "");
  const [due, setDue] = useState(toLocalInput(action.due_at));
  const [notes, setNotes] = useState(action.notes ?? "");
  useEffect(() => {
    setAssignee(action.assignee_user_id ?? "");
    setDue(toLocalInput(action.due_at));
    setNotes(action.notes ?? "");
  }, [action]);

  const assignees = useQuery({
    queryKey: ["coaching", "assignees"],
    queryFn: () => apiFetch("/api/v1/coaching-actions/assignees", { schema: z.array(coachingAssigneeSchema) }),
  });
  const save = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/coaching-actions/${action.id}`, {
        method: "PATCH",
        body: {
          assignee_user_id: assignee || null,
          due_at: due ? new Date(due).toISOString() : null,
          notes: notes || null,
        },
        schema: coachingActionSchema,
      }),
    onSuccess: onSaved,
    onError,
  });

  return (
    <Card className="mt-6">
      <h2 className="mb-3 text-sm font-semibold text-ink-900">Düzenle</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="edit-assignee" className="block text-sm font-medium text-slate-700">
            Sorumlu
          </label>
          <select
            id="edit-assignee"
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
        <TextField label="Termin" type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} />
        <div className="sm:col-span-2">
          <label htmlFor="edit-notes" className="block text-sm font-medium text-slate-700">
            Notlar
          </label>
          <textarea
            id="edit-notes"
            rows={4}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
      </div>
      <Button className="mt-3" loading={save.isPending} onClick={() => save.mutate()}>
        Kaydet
      </Button>
    </Card>
  );
}
