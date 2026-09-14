"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  Card,
  ErrorState,
  LoadingState,
  PageHeader,
  ReviewBadge,
  SeverityBadge,
  TextField,
  formatDateTime,
} from "@/components/ui";
import { ApiError, apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { RESOLUTIONS, coachingAssigneeSchema } from "@/lib/schemas";
import type { SafetyEventDetail } from "@/lib/types";

const DECISIONS = [
  { value: "confirmed", label: "Onayla" },
  { value: "rejected", label: "Reddet" },
  { value: "uncertain", label: "Belirsiz" },
];

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canReview = can(user, "events.review");
  const canManageCoaching = can(user, "coaching.manage");

  const [decision, setDecision] = useState("confirmed");
  const [resolution, setResolution] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [notes, setNotes] = useState("");
  const [assignee, setAssignee] = useState("");
  const [due, setDue] = useState("");
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const query = useQuery({
    queryKey: ["safety-event", id],
    queryFn: () => apiFetch<SafetyEventDetail>(`/api/v1/safety-events/${id}`),
  });
  const assignees = useQuery({
    queryKey: ["coaching", "assignees"],
    queryFn: () => apiFetch("/api/v1/coaching-actions/assignees", { schema: z.array(coachingAssigneeSchema) }),
    enabled: canManageCoaching && resolution === "kocluk_atandi",
  });

  const review = useMutation({
    mutationFn: () =>
      apiFetch<{ coaching_action_id: string | null }>(`/api/v1/safety-events/${id}/review`, {
        method: "POST",
        body: {
          decision,
          notes: notes || null,
          root_cause: rootCause || null,
          resolution: resolution || null,
          coaching_assignee_user_id: resolution === "kocluk_atandi" && assignee ? assignee : null,
          coaching_due_at: resolution === "kocluk_atandi" && due ? new Date(due).toISOString() : null,
        },
      }),
    onSuccess: (res) => {
      setFeedback({
        kind: "success",
        text: res.coaching_action_id
          ? "İnceleme kaydedildi ve koçluk görevi oluşturuldu."
          : "İnceleme kaydedildi.",
      });
      void queryClient.invalidateQueries({ queryKey: ["safety-event", id] });
      void queryClient.invalidateQueries({ queryKey: ["safety-events"] });
      void queryClient.invalidateQueries({ queryKey: ["coaching"] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "İnceleme kaydedilemedi.") }),
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="space-y-3">
        <ErrorState message={notFound ? "Güvenlik olayı bulunamadı." : errorMessage(query.error, "Olay yüklenemedi.")} onRetry={notFound ? undefined : () => void query.refetch()} />
        <Link href="/panel/olaylar" className="text-sm text-brand-700 hover:underline">
          ← Olay listesine dön
        </Link>
      </div>
    );
  }

  const event = query.data;
  const exp = event.explanation;
  const coachingWithoutConfirm = resolution === "kocluk_atandi" && decision !== "confirmed";

  return (
    <div>
      <Link href="/panel/olaylar" className="text-sm text-brand-600 hover:underline">
        ← Güvenlik Olayları
      </Link>
      <PageHeader
        title={event.event_label}
        description={event.reason_tr}
        action={<SeverityBadge severity={event.severity} label={event.severity_label} />}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-ink-900">Açıklama</h2>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
            <Detail label="Ne oldu?" value={exp.ne_oldu} />
            <Detail label="Ne zaman?" value={formatDateTime(exp.ne_zaman)} />
            <Detail
              label="Nerede?"
              value={exp.nerede ? `${exp.nerede.latitude.toFixed(5)}, ${exp.nerede.longitude.toFixed(5)}` : "—"}
            />
            <Detail label="Hangi veri?" value={exp.hangi_veri} />
            <Detail label="Hangi kural?" value={exp.hangi_kural} />
            <Detail label="Eşik / Ölçülen" value={`${exp.esik ?? "—"} / ${exp.olculen_deger ?? "—"}`} />
            <Detail label="Güven seviyesi" value={`%${Math.round(exp.guven_seviyesi * 100)}`} />
            <Detail label="Veri kalitesi" value={exp.veri_kalitesi != null ? `%${Math.round(exp.veri_kalitesi * 100)}` : "—"} />
          </dl>
          {exp.inceleme_gerekli && (
            <Alert kind="warning" className="mt-4">
              Düşük veri kalitesi nedeniyle bu olay insan incelemesi gerektiriyor.
            </Alert>
          )}
          {event.review_status !== "pending" && (
            <div className="mt-4 rounded-lg bg-slate-50 p-3 text-sm">
              <p className="text-slate-700">
                Son inceleme: <ReviewBadge status={event.review_status} /> · {formatDateTime(event.reviewed_at)}
              </p>
              {event.resolution_label && <p className="mt-1 text-slate-600">Çözüm: {event.resolution_label}</p>}
              {event.root_cause && <p className="mt-1 text-slate-600">Kök neden: {event.root_cause}</p>}
              {event.reviewer_notes && <p className="mt-1 whitespace-pre-wrap text-slate-600">Not: {event.reviewer_notes}</p>}
            </div>
          )}
          {event.coaching_action && (
            <p className="mt-3 text-sm">
              Koçluk görevi:{" "}
              <Link href={`/panel/kocluk/${event.coaching_action.id}`} className="text-brand-700 hover:underline">
                {event.coaching_action.status_label}
              </Link>{" "}
              {event.coaching_action.due_at && <span className="text-slate-500">· termin {formatDateTime(event.coaching_action.due_at)}</span>}
            </p>
          )}
        </Card>

        <Card>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink-900">İnceleme</h2>
            <ReviewBadge status={event.review_status} />
          </div>
          {!canReview ? (
            <p className="text-sm text-slate-500">Bu olayı inceleme yetkiniz yok.</p>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setFeedback(null);
                review.mutate();
              }}
              className="space-y-3"
            >
              <fieldset>
                <legend className="text-sm font-medium text-slate-700">Karar</legend>
                <div className="mt-1 flex flex-wrap gap-3">
                  {DECISIONS.map((d) => (
                    <label key={d.value} className="flex items-center gap-1.5 text-sm">
                      <input
                        type="radio"
                        name="decision"
                        value={d.value}
                        checked={decision === d.value}
                        onChange={() => setDecision(d.value)}
                      />
                      {d.label}
                    </label>
                  ))}
                </div>
              </fieldset>
              <div>
                <label htmlFor="resolution" className="block text-sm font-medium text-slate-700">
                  Çözüm
                </label>
                <select
                  id="resolution"
                  value={resolution}
                  onChange={(e) => setResolution(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                >
                  <option value="">Seçilmedi</option>
                  {RESOLUTIONS.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>
              {coachingWithoutConfirm && (
                <Alert kind="warning">Koçluk yalnızca onaylanan olaylar için atanabilir.</Alert>
              )}
              {resolution === "kocluk_atandi" && canManageCoaching && (
                <>
                  <div>
                    <label htmlFor="coach-assignee" className="block text-sm font-medium text-slate-700">
                      Koçluk sorumlusu
                    </label>
                    <select
                      id="coach-assignee"
                      value={assignee}
                      onChange={(e) => setAssignee(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    >
                      <option value="">Daha sonra atanacak</option>
                      {assignees.data?.map((a) => (
                        <option key={a.user_id} value={a.user_id}>
                          {a.full_name} ({a.role_label})
                        </option>
                      ))}
                    </select>
                  </div>
                  <TextField label="Termin" type="datetime-local" value={due} hint="Boş bırakılırsa 7 gün sonrası." onChange={(e) => setDue(e.target.value)} />
                </>
              )}
              <TextField label="Kök neden (isteğe bağlı)" maxLength={60} value={rootCause} onChange={(e) => setRootCause(e.target.value)} />
              <div>
                <label htmlFor="notes" className="block text-sm font-medium text-slate-700">
                  Not (isteğe bağlı)
                </label>
                <textarea
                  id="notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </div>
              <Button type="submit" loading={review.isPending} disabled={coachingWithoutConfirm}>
                İncelemeyi kaydet
              </Button>
              {feedback && <Alert kind={feedback.kind}>{feedback.text}</Alert>}
            </form>
          )}
        </Card>
      </div>

      <Card className="mt-6">
        <h2 className="mb-3 text-sm font-semibold text-ink-900">Kanıt</h2>
        {event.evidence_restricted ? (
          <p className="text-sm text-slate-500">
            Kanıt verileri kişisel veri içerir; görüntülemek için kanıt erişim yetkisi gerekir.
          </p>
        ) : event.evidence.length > 0 ? (
          <ul className="space-y-2">
            {event.evidence.map((ev) => (
              <li key={ev.id} className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                <span className="font-medium text-slate-700">
                  {ev.kind === "telemetry_window" ? "Telemetri penceresi" : ev.kind}
                </span>
                {ev.captured_at && <Badge>{formatDateTime(ev.captured_at)}</Badge>}
                {ev.telemetry_window && <TelemetryWindow data={ev.telemetry_window} />}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">Bağlı kanıt yok.</p>
        )}
      </Card>
    </div>
  );
}

const TELEMETRY_LABELS: Record<string, string> = {
  speed_kph: "Hız (km/s)",
  acceleration_ms2: "Boylamsal hızlanma (m/s²)",
  lateral_acceleration_ms2: "Yanal hızlanma (m/s²)",
  quality: "Veri kalitesi",
  measured_value: "Ölçülen değer",
  threshold: "Eşik",
};

function TelemetryWindow({ data }: { data: Record<string, unknown> }) {
  return (
    <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
      {Object.entries(data).map(([key, value]) => (
        <div key={key}>
          <dt className="text-[11px] text-slate-400">{TELEMETRY_LABELS[key] ?? key}</dt>
          <dd className="text-slate-700">{value == null ? "—" : String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className="text-sm text-ink-900">{value}</dd>
    </div>
  );
}
