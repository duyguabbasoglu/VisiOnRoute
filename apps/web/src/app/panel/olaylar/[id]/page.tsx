"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { SafetyEventDetail } from "@/lib/types";
import {
  Card,
  PageHeader,
  ReviewBadge,
  SeverityBadge,
  formatDateTime,
} from "@/components/ui";

const DECISIONS = [
  { value: "confirmed", label: "Onayla" },
  { value: "rejected", label: "Reddet" },
  { value: "uncertain", label: "Belirsiz" },
];

export default function EventDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["safety-event", id],
    queryFn: () => apiFetch<SafetyEventDetail>(`/api/v1/safety-events/${id}`),
  });

  const review = useMutation({
    mutationFn: (decision: string) =>
      apiFetch<SafetyEventDetail>(`/api/v1/safety-events/${id}/review`, {
        method: "POST",
        body: { decision, notes: notes || null },
      }),
    onSuccess: () => {
      setMessage("İnceleme kaydedildi.");
      void queryClient.invalidateQueries({ queryKey: ["safety-event", id] });
      void queryClient.invalidateQueries({ queryKey: ["safety-events"] });
    },
    onError: (err) => {
      setMessage(err instanceof ApiError ? err.message : "İnceleme kaydedilemedi.");
    },
  });

  if (query.isLoading) {
    return <p className="text-sm text-slate-500">Yükleniyor…</p>;
  }
  if (query.isError || !query.data) {
    return (
      <Card>
        <p className="text-sm text-slate-600">Güvenlik olayı bulunamadı.</p>
        <Link href="/panel/olaylar" className="mt-2 inline-block text-sm text-brand-600">
          ← Olay listesine dön
        </Link>
      </Card>
    );
  }

  const event = query.data;
  const exp = event.explanation;

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
              value={
                exp.nerede
                  ? `${exp.nerede.latitude.toFixed(5)}, ${exp.nerede.longitude.toFixed(5)}`
                  : "—"
              }
            />
            <Detail label="Hangi veri?" value={exp.hangi_veri} />
            <Detail label="Hangi kural?" value={exp.hangi_kural} />
            <Detail
              label="Eşik / Ölçülen"
              value={`${exp.esik ?? "—"} / ${exp.olculen_deger ?? "—"}`}
            />
            <Detail label="Güven seviyesi" value={`%${Math.round(exp.guven_seviyesi * 100)}`} />
            <Detail
              label="Veri kalitesi"
              value={exp.veri_kalitesi != null ? `%${Math.round(exp.veri_kalitesi * 100)}` : "—"}
            />
          </dl>
          {exp.inceleme_gerekli && (
            <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
              Düşük veri kalitesi nedeniyle bu olay insan incelemesi gerektiriyor.
            </p>
          )}
        </Card>

        <Card>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink-900">İnceleme</h2>
            <ReviewBadge status={event.review_status} />
          </div>
          <label htmlFor="notes" className="block text-sm text-slate-600">
            Not (isteğe bağlı)
          </label>
          <textarea
            id="notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            {DECISIONS.map((d) => (
              <button
                key={d.value}
                onClick={() => review.mutate(d.value)}
                disabled={review.isPending}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm transition hover:bg-slate-50 disabled:opacity-60"
              >
                {d.label}
              </button>
            ))}
          </div>
          {message && <p className="mt-3 text-sm text-slate-600">{message}</p>}
        </Card>
      </div>

      <Card className="mt-6">
        <h2 className="mb-3 text-sm font-semibold text-ink-900">Kanıt</h2>
        {event.evidence.length > 0 ? (
          <ul className="space-y-2">
            {event.evidence.map((ev) => (
              <li key={ev.id} className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                <span className="font-medium text-slate-700">
                  {ev.kind === "telemetry_window" ? "Telemetri penceresi" : ev.kind}
                </span>
                {ev.telemetry_window && (
                  <pre className="mt-1 overflow-x-auto text-[11px] text-slate-500">
                    {JSON.stringify(ev.telemetry_window, null, 2)}
                  </pre>
                )}
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

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className="text-sm text-ink-900">{value}</dd>
    </div>
  );
}
