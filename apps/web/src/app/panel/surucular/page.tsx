"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  CELL,
  Card,
  ConfirmButton,
  DataTable,
  EmptyState,
  ErrorState,
  PageHeader,
  SectionHeading,
  SkeletonRows,
  TextField,
  formatDateTime,
  formatNumber,
  type FeedbackState,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useVehicles } from "@/lib/fleet";
import { can } from "@/lib/permissions";
import { assignmentSchema, driverListSchema, driverSchema, driverScoreSchema } from "@/lib/schemas";

const DRIVER_STATUS: Record<string, { label: string; tone: "success" | "neutral" | "warning" }> = {
  active: { label: "Etkin", tone: "success" },
  inactive: { label: "Pasif", tone: "neutral" },
  erased: { label: "Silindi (KVKK)", tone: "warning" },
};

export default function DriversPage() {
  const { user } = useAuth();
  const canManage = can(user, "fleet.manage");
  const canScore = can(user, "analytics.read");
  const queryClient = useQueryClient();
  const [externalId, setExternalId] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [feedback, setFeedback] = useState<FeedbackState>(null);
  const [selection, setSelection] = useState<Record<string, string>>({});

  const drivers = useQuery({
    queryKey: ["drivers"],
    queryFn: () => apiFetch("/api/v1/drivers?limit=200", { schema: driverListSchema }),
  });
  const vehicles = useVehicles();
  const assignments = useQuery({
    queryKey: ["assignments"],
    queryFn: () => apiFetch("/api/v1/assignments", { schema: z.array(assignmentSchema) }),
  });
  const refreshAssignments = () => void queryClient.invalidateQueries({ queryKey: ["assignments"] });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/drivers", {
        method: "POST",
        body: { external_id: externalId.trim(), full_name: fullName.trim(), phone: phone.trim() || null },
        schema: driverSchema,
      }),
    onSuccess: (driver) => {
      setExternalId("");
      setFullName("");
      setPhone("");
      setFeedback({ kind: "success", text: `${driver.full_name} eklendi.` });
      void queryClient.invalidateQueries({ queryKey: ["drivers"] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Sürücü eklenemedi.") }),
  });
  const assign = useMutation({
    mutationFn: ({ driverId, vehicleId }: { driverId: string; vehicleId: string }) =>
      apiFetch("/api/v1/assignments", {
        method: "POST",
        body: { driver_id: driverId, vehicle_id: vehicleId },
        schema: assignmentSchema,
      }),
    onSuccess: () => {
      setFeedback({ kind: "success", text: "Sürücü araca atandı." });
      refreshAssignments();
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Atama yapılamadı.") }),
  });
  const close = useMutation({
    mutationFn: (assignmentId: string) =>
      apiFetch(`/api/v1/assignments/${assignmentId}/close`, { method: "POST", schema: assignmentSchema }),
    onSuccess: () => {
      setFeedback({ kind: "success", text: "Atama sonlandırıldı." });
      refreshAssignments();
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Atama sonlandırılamadı.") }),
  });

  const openByDriver = new Map(
    (assignments.data ?? []).filter((a) => a.ended_at === null).map((a) => [a.driver_id, a]),
  );
  const busyVehicles = new Set((assignments.data ?? []).filter((a) => a.ended_at === null).map((a) => a.vehicle_id));

  const headers = ["Ad soyad", "Dış kimlik", "Durum", "Araç ataması"];
  if (canScore) headers.push("Risk skoru");

  return (
    <div>
      <PageHeader title="Sürücüler" description="Sürücü kayıtları, araç atamaları ve mesafeye göre normalize risk skoru." />
      {canManage && (
        <Card className="mb-4">
          <SectionHeading title="Yeni sürücü" />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
            className="grid grid-cols-1 items-start gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_auto]"
          >
            <TextField
              label="Dış kimlik"
              required
              maxLength={120}
              value={externalId}
              onChange={(e) => setExternalId(e.target.value)}
              placeholder="SUR-001"
              hint="Telematik/cihaz verisindeki sürücü kimliği."
            />
            <TextField
              label="Ad soyad"
              required
              minLength={2}
              maxLength={200}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Ahmet Yılmaz"
            />
            <TextField label="Telefon" type="tel" maxLength={32} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="0555 000 00 00" />
            <Button type="submit" className="lg:mt-6" loading={create.isPending} disabled={!externalId.trim() || fullName.trim().length < 2}>
              Sürücü ekle
            </Button>
          </form>
        </Card>
      )}
      {feedback && (
        <Alert kind={feedback.kind} className="mb-4">
          {feedback.text}
        </Alert>
      )}

      {drivers.isLoading ? (
        <SkeletonRows rows={4} />
      ) : drivers.isError ? (
        <ErrorState message={errorMessage(drivers.error, "Sürücüler yüklenemedi.")} onRetry={() => void drivers.refetch()} />
      ) : drivers.data && drivers.data.items.length > 0 ? (
        <DataTable label="Sürücüler" headers={headers}>
          {drivers.data.items.map((d) => {
            const status = DRIVER_STATUS[d.status] ?? { label: d.status, tone: "neutral" as const };
            const open = openByDriver.get(d.id);
            const chosen = selection[d.id] ?? "";
            return (
              <tr key={d.id} className="hover:bg-slate-50">
                <td className={`${CELL} text-ink-900`}>
                  {d.full_name}
                  {d.phone && <span className="block text-xs text-slate-400">{d.phone}</span>}
                </td>
                <td className={`${CELL} text-slate-600`}>{d.external_id}</td>
                <td className={CELL}>
                  <Badge tone={status.tone}>{status.label}</Badge>
                </td>
                <td className={CELL}>
                  {open ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-slate-700">{vehicles.names.get(open.vehicle_id) ?? "Araç"}</span>
                      <span className="text-xs text-slate-400">{formatDateTime(open.started_at)} itibarıyla</span>
                      {canManage && (
                        <ConfirmButton label="Atamayı bitir" onConfirm={() => close.mutate(open.id)} loading={close.isPending} />
                      )}
                    </div>
                  ) : canManage && d.status === "active" ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <select
                        aria-label={`${d.full_name} için araç`}
                        value={chosen}
                        onChange={(e) => setSelection((current) => ({ ...current, [d.id]: e.target.value }))}
                        className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm"
                      >
                        <option value="">Araç seçin…</option>
                        {vehicles.items
                          .filter((v) => !busyVehicles.has(v.id))
                          .map((v) => (
                            <option key={v.id} value={v.id}>
                              {v.plate ?? v.external_id}
                            </option>
                          ))}
                      </select>
                      <Button
                        variant="secondary"
                        className="px-2 py-1 text-xs"
                        disabled={!chosen}
                        loading={assign.isPending && assign.variables?.driverId === d.id}
                        onClick={() => assign.mutate({ driverId: d.id, vehicleId: chosen })}
                      >
                        Ata
                      </Button>
                    </div>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
                {canScore && (
                  <td className={CELL}>
                    <DriverScore driverId={d.id} name={d.full_name} />
                  </td>
                )}
              </tr>
            );
          })}
        </DataTable>
      ) : (
        <EmptyState message={canManage ? "Henüz sürücü eklenmemiş. Yukarıdaki formla ilk sürücüyü ekleyin." : "Henüz sürücü eklenmemiş."} />
      )}
      {canScore && (
        <p className="mt-3 text-xs text-slate-500">
          Risk skoru son 90 günün olaylarını sürüş mesafesine göre ağırlıklandırır (100 = en düşük risk). Tek başına
          disiplin kararı için kullanılmamalıdır.
        </p>
      )}
    </div>
  );
}

function DriverScore({ driverId, name }: { driverId: string; name: string }) {
  const [requested, setRequested] = useState(false);
  const score = useQuery({
    queryKey: ["driver-score", driverId],
    queryFn: () => apiFetch(`/api/v1/drivers/${driverId}/risk-score`, { schema: driverScoreSchema }),
    enabled: requested,
  });
  if (!requested) {
    return (
      <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => setRequested(true)} aria-label={`${name} için risk skorunu hesapla`}>
        Hesapla
      </Button>
    );
  }
  if (score.isLoading) return <span className="text-xs text-slate-500">Hesaplanıyor…</span>;
  if (score.isError || !score.data) return <span className="text-xs text-red-600">{errorMessage(score.error, "Hesaplanamadı.")}</span>;
  if (!score.data.has_sufficient_exposure || score.data.score == null) {
    return (
      <span className="text-xs text-slate-500" title={score.data.note ?? undefined}>
        Yetersiz veri ({formatNumber(score.data.exposure_km)} km)
      </span>
    );
  }
  const value = Math.round(score.data.score);
  const tone = value >= 80 ? "success" : value >= 60 ? "warning" : "danger";
  return (
    <span className="flex items-center gap-2">
      <Badge tone={tone}>{value} / 100</Badge>
      <span className="text-xs text-slate-400">
        {score.data.event_count} olay · {formatNumber(score.data.exposure_km)} km
      </span>
    </span>
  );
}
