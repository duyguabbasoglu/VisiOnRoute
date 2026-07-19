"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import type { SafetyEventList } from "@/lib/types";
import {
  Card,
  EmptyState,
  PageHeader,
  ReviewBadge,
  SeverityBadge,
  formatDateTime,
} from "@/components/ui";

const SEVERITIES = [
  { value: "", label: "Tüm şiddetler" },
  { value: "critical", label: "Kritik" },
  { value: "high", label: "Yüksek" },
  { value: "medium", label: "Orta" },
  { value: "low", label: "Düşük" },
];

const REVIEW = [
  { value: "", label: "Tüm durumlar" },
  { value: "pending", label: "Beklemede" },
  { value: "confirmed", label: "Onaylandı" },
  { value: "rejected", label: "Reddedildi" },
  { value: "uncertain", label: "Belirsiz" },
];

export default function EventsPage() {
  const [severity, setSeverity] = useState("");
  const [review, setReview] = useState("");

  const query = useQuery({
    queryKey: ["safety-events", severity, review],
    queryFn: () => {
      const params = new URLSearchParams({ limit: "50" });
      if (severity) params.set("severity", severity);
      if (review) params.set("review_status", review);
      return apiFetch<SafetyEventList>(`/api/v1/safety-events?${params.toString()}`);
    },
  });

  return (
    <div>
      <PageHeader
        title="Güvenlik Olayları"
        description="Sürücü davranışı kaynaklı, açıklanabilir güvenlik olayları."
      />
      <Card className="mb-4">
        <div className="flex flex-wrap gap-3">
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            aria-label="Şiddet filtresi"
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
          >
            {SEVERITIES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <select
            value={review}
            onChange={(e) => setReview(e.target.value)}
            aria-label="İnceleme durumu filtresi"
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
          >
            {REVIEW.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
      </Card>

      {query.isLoading ? (
        <p className="text-sm text-slate-500">Yükleniyor…</p>
      ) : query.data && query.data.items.length > 0 ? (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Olay</th>
                <th className="px-4 py-2.5 font-medium">Şiddet</th>
                <th className="px-4 py-2.5 font-medium">Güven</th>
                <th className="px-4 py-2.5 font-medium">Zaman</th>
                <th className="px-4 py-2.5 font-medium">İnceleme</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {query.data.items.map((event) => (
                <tr key={event.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 text-ink-900">
                    {event.event_label}
                    {event.occurrence_count > 1 && (
                      <span className="ml-1 text-xs text-slate-400">
                        ×{event.occurrence_count}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <SeverityBadge severity={event.severity} label={event.severity_label} />
                  </td>
                  <td className="px-4 py-2.5 text-slate-600">
                    %{Math.round(event.confidence * 100)}
                  </td>
                  <td className="px-4 py-2.5 text-slate-500">
                    {formatDateTime(event.occurred_at)}
                  </td>
                  <td className="px-4 py-2.5">
                    <ReviewBadge status={event.review_status} />
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Link
                      href={`/panel/olaylar/${event.id}`}
                      className="text-xs text-brand-600 hover:underline"
                    >
                      İncele
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <EmptyState message="Seçili filtrelerle eşleşen güvenlik olayı bulunamadı." />
      )}
    </div>
  );
}
