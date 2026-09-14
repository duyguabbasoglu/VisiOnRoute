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
import {
  RESOLUTIONS,
  coachingAssigneeSchema,
  reviewResponseSchema,
  safetyEventDetailSchema,
} from "@/lib/schemas";
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
  const canViewMedia = can(user, "events.evidence.raw_media");
  const canManageMedia = canViewMedia && canReview;

  const [decision, setDecision] = useState("confirmed");
  const [resolution, setResolution] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [notes, setNotes] = useState("");
  const [assignee, setAssignee] = useState("");
  const [due, setDue] = useState("");
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const query = useQuery({
    queryKey: ["safety-event", id],
    queryFn: () => apiFetch(`/api/v1/safety-events/${id}`, { schema: safetyEventDetailSchema }),
  });
  const assignees = useQuery({
    queryKey: ["coaching", "assignees"],
    queryFn: () => apiFetch("/api/v1/coaching-actions/assignees", { schema: z.array(coachingAssigneeSchema) }),
    enabled: canManageCoaching && resolution === "kocluk_atandi",
  });

  const review = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/safety-events/${id}/review`, {
        schema: reviewResponseSchema,
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
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-slate-700">{EVIDENCE_KIND_LABELS[ev.kind] ?? "Kanıt"}</span>
                  {ev.captured_at && <Badge>{formatDateTime(ev.captured_at)}</Badge>}
                  {ev.kind !== "telemetry_window" && (
                    <MediaEvidence eventId={event.id} evidence={ev} canView={canViewMedia} canManage={canManageMedia} />
                  )}
                </div>
                {ev.telemetry_window && <TelemetryWindow data={ev.telemetry_window} />}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">Bağlı kanıt yok.</p>
        )}
        {!event.evidence_restricted && canManageMedia && <EvidenceUpload eventId={event.id} />}
      </Card>
    </div>
  );
}

const EVIDENCE_KIND_LABELS: Record<string, string> = {
  telemetry_window: "Telemetri penceresi",
  snapshot: "Görüntü",
  clip: "Video klip",
  note: "Not",
};

const MEDIA_STATUS: Record<string, { label: string; tone: "neutral" | "success" | "warning" | "danger" }> = {
  available: { label: "Erişilebilir", tone: "success" },
  rejected: { label: "Reddedildi (içerik türü uyuşmadı)", tone: "danger" },
  deleted: { label: "Silindi", tone: "neutral" },
  pending_upload: { label: "Yükleniyor", tone: "warning" },
};

const ALLOWED_MEDIA = ["image/jpeg", "image/png", "video/mp4"];

const accessSchema = z.object({ url: z.string().url(), expires_in: z.number() });
const uploadSlotSchema = z.object({
  evidence_id: z.string(),
  upload: z.object({
    url: z.string().url(),
    method: z.enum(["POST", "PUT"]),
    fields: z.record(z.string()),
    headers: z.record(z.string()),
    expires_at: z.string(),
    max_bytes: z.number(),
  }),
});

function formatBytes(size: number | null): string {
  if (size === null) return "";
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

type EvidenceItem = SafetyEventDetail["evidence"][number];

function MediaEvidence({
  eventId,
  evidence,
  canView,
  canManage,
}: {
  eventId: string;
  evidence: EvidenceItem;
  canView: boolean;
  canManage: boolean;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const status = MEDIA_STATUS[evidence.status] ?? { label: evidence.status, tone: "neutral" as const };
  const base = `/api/v1/safety-events/${eventId}/evidence/${evidence.id}`;

  const open = useMutation({
    mutationFn: () => apiFetch(`${base}/access`, { schema: accessSchema }),
    // The short-lived link is used immediately and never stored.
    onSuccess: ({ url }) => {
      setError(null);
      window.open(url, "_blank", "noopener,noreferrer");
    },
    onError: (err) => setError(errorMessage(err, "Kanıt bağlantısı alınamadı.")),
  });
  const remove = useMutation({
    mutationFn: () => apiFetch(base, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["safety-event", eventId] }),
    onError: (err) => setError(errorMessage(err, "Kanıt silinemedi.")),
  });

  return (
    <>
      <Badge tone={status.tone}>{status.label}</Badge>
      {evidence.size_bytes !== null && <span>{formatBytes(evidence.size_bytes)}</span>}
      {evidence.redaction_status === "not_processed" && (
        <Badge tone="warning">Anonimleştirilmedi (yüz/plaka görünebilir)</Badge>
      )}
      {evidence.status === "available" && canView && (
        <Button variant="secondary" className="px-2 py-1 text-xs" loading={open.isPending} onClick={() => open.mutate()}>
          Güvenli bağlantıyla aç
        </Button>
      )}
      {evidence.status === "available" && canManage && (
        <Button
          variant="danger"
          className="px-2 py-1 text-xs"
          loading={remove.isPending}
          onClick={() => {
            if (window.confirm("Bu kanıt dosyası kalıcı olarak silinsin mi? Bu işlem denetim kaydına yazılır.")) {
              remove.mutate();
            }
          }}
        >
          Sil
        </Button>
      )}
      {!canView && evidence.status === "available" && (
        <span className="text-slate-500">Ham medyayı açmak için ek yetki gerekir.</span>
      )}
      {error && <span role="alert" className="text-red-700">{error}</span>}
    </>
  );
}

async function sendToStorage(slot: z.infer<typeof uploadSlotSchema>["upload"], file: File): Promise<void> {
  let response: Response;
  if (slot.method === "POST") {
    const form = new FormData();
    for (const [key, value] of Object.entries(slot.fields)) form.append(key, value);
    form.append("file", file);
    response = await fetch(slot.url, { method: "POST", body: form, credentials: "omit" });
  } else {
    response = await fetch(slot.url, { method: "PUT", body: file, headers: slot.headers, credentials: "omit" });
  }
  if (!response.ok) throw new Error("upload_failed");
}

function EvidenceUpload({ eventId }: { eventId: string }) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const upload = useMutation({
    mutationFn: async (selected: File) => {
      const slot = await apiFetch(`/api/v1/safety-events/${eventId}/evidence/uploads`, {
        method: "POST",
        body: { content_type: selected.type, size_bytes: selected.size, filename: selected.name },
        schema: uploadSlotSchema,
      });
      try {
        await sendToStorage(slot.upload, selected);
      } catch {
        throw new ApiError(0, "UPLOAD_FAILED", "Dosya depolamaya yüklenemedi. Bağlantınızı kontrol edip tekrar deneyin.");
      }
      await apiFetch(`/api/v1/safety-events/${eventId}/evidence/${slot.evidence_id}/complete`, { method: "POST" });
    },
    onSuccess: () => {
      setFile(null);
      setFeedback({ kind: "success", text: "Kanıt dosyası doğrulandı ve olaya eklendi." });
      void queryClient.invalidateQueries({ queryKey: ["safety-event", eventId] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Kanıt yüklenemedi.") }),
  });

  return (
    <form
      className="mt-4 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!file) return;
        if (!ALLOWED_MEDIA.includes(file.type)) {
          setFeedback({ kind: "error", text: "Yalnızca JPEG, PNG görüntü veya MP4 video yüklenebilir." });
          return;
        }
        upload.mutate(file);
      }}
    >
      <label className="text-sm text-slate-700">
        <span className="mb-1 block font-medium">Görüntü veya video kanıtı ekle</span>
        <input
          type="file"
          accept={ALLOWED_MEDIA.join(",")}
          onChange={(e) => {
            setFeedback(null);
            setFile(e.target.files?.[0] ?? null);
          }}
          className="text-sm"
        />
      </label>
      <Button type="submit" disabled={!file} loading={upload.isPending}>
        Yükle
      </Button>
      <p className="w-full text-xs text-slate-500">
        Dosya içeriği sunucuda doğrulanır. Otomatik yüz/plaka anonimleştirme bu sürümde yoktur; kişisel veri
        içeren kayıtları yalnızca gerekli olduğunda ekleyin.
      </p>
      {feedback && <Alert kind={feedback.kind}>{feedback.text}</Alert>}
    </form>
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
