"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import {
  Button,
  CELL,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  PageHeader,
  ReviewBadge,
  SeverityBadge,
  SyntheticBadge,
  SkeletonRows,
  formatDateTime,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useDrivers, useVehicles } from "@/lib/fleet";
import { safetyEventListSchema } from "@/lib/schemas";

const PAGE_SIZE = 50;

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

const FILTER_CLASS = "rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm";

export default function EventsPage() {
  const [severity, setSeverity] = useState("");
  const [review, setReview] = useState("");
  const [vehicle, setVehicle] = useState("");
  const [page, setPage] = useState(0);
  const vehicles = useVehicles();
  const drivers = useDrivers();

  const query = useQuery({
    queryKey: ["safety-events", severity, review, vehicle, page],
    queryFn: () => {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) });
      if (severity) params.set("severity", severity);
      if (review) params.set("review_status", review);
      if (vehicle) params.set("vehicle_id", vehicle);
      return apiFetch(`/api/v1/safety-events?${params.toString()}`, { schema: safetyEventListSchema });
    },
  });

  const filter = (setter: (value: string) => void) => (e: { target: { value: string } }) => {
    setter(e.target.value);
    setPage(0);
  };
  const total = query.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <PageHeader
        title="Güvenlik Olayları"
        description="Telemetriye uygulanan deterministik kurallarla üretilen, açıklanabilir güvenlik olayları."
      />
      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <select value={severity} onChange={filter(setSeverity)} aria-label="Şiddet filtresi" className={FILTER_CLASS}>
            {SEVERITIES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <select value={review} onChange={filter(setReview)} aria-label="İnceleme durumu filtresi" className={FILTER_CLASS}>
            {REVIEW.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
          {vehicles.items.length > 0 && (
            <select value={vehicle} onChange={filter(setVehicle)} aria-label="Araç filtresi" className={FILTER_CLASS}>
              <option value="">Tüm araçlar</option>
              {vehicles.items.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.plate ?? v.external_id}
                </option>
              ))}
            </select>
          )}
          {query.data && <span className="ml-auto text-xs text-slate-500">{total} olay</span>}
        </div>
      </Card>

      {query.isLoading ? (
        <SkeletonRows rows={5} />
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error, "Olaylar yüklenemedi.")} onRetry={() => void query.refetch()} />
      ) : query.data && query.data.items.length > 0 ? (
        <>
          <DataTable label="Güvenlik olayları" headers={["Olay", "Araç / sürücü", "Şiddet", "Güven", "Zaman", "İnceleme", ""]}>
            {query.data.items.map((event) => (
              <tr key={event.id} className="hover:bg-slate-50">
                <td className={`${CELL} text-ink-900`}>
                  {event.event_label}
                  {event.occurrence_count > 1 && (
                    <span className="ml-1 text-xs text-slate-400">×{event.occurrence_count}</span>
                  )}
                  <SyntheticBadge origin={event.data_origin} />
                </td>
                <td className={`${CELL} text-slate-600`}>
                  {vehicles.names.get(event.vehicle_id) ?? "—"}
                  {event.driver_id && (
                    <span className="block text-xs text-slate-400">{drivers.names.get(event.driver_id) ?? ""}</span>
                  )}
                </td>
                <td className={CELL}>
                  <SeverityBadge severity={event.severity} label={event.severity_label} />
                </td>
                <td className={`${CELL} text-slate-600`}>%{Math.round(event.confidence * 100)}</td>
                <td className={`${CELL} whitespace-nowrap text-slate-500`}>{formatDateTime(event.occurred_at)}</td>
                <td className={CELL}>
                  <ReviewBadge status={event.review_status} />
                </td>
                <td className={`${CELL} text-right`}>
                  <Link href={`/panel/olaylar/${event.id}`} className="text-xs font-medium text-brand-700 hover:underline">
                    İncele
                  </Link>
                </td>
              </tr>
            ))}
          </DataTable>
          {pages > 1 && (
            <nav aria-label="Sayfalama" className="mt-4 flex items-center justify-end gap-3 text-sm text-slate-600">
              <Button variant="secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                Önceki
              </Button>
              <span>
                Sayfa {page + 1} / {pages}
              </span>
              <Button variant="secondary" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>
                Sonraki
              </Button>
            </nav>
          )}
        </>
      ) : (
        <EmptyState
          message={
            severity || review || vehicle
              ? "Seçili filtrelerle eşleşen güvenlik olayı bulunamadı."
              : "Henüz güvenlik olayı yok. Telemetri geldiğinde kurallar olayları otomatik üretir."
          }
        />
      )}
    </div>
  );
}
