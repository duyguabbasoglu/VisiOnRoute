"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmButton,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  TextField,
  formatDateTime,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { assignmentSchema, driverListSchema, driverSchema, vehicleListSchema } from "@/lib/schemas";

const DRIVER_STATUS: Record<string, { label: string; tone: "success" | "neutral" | "warning" }> = {
  active: { label: "Etkin", tone: "success" },
  inactive: { label: "Pasif", tone: "neutral" },
  erased: { label: "Silindi (KVKK)", tone: "warning" },
};

export default function DriversPage() {
  const { user } = useAuth();
  const canManage = can(user, "fleet.manage");
  const queryClient = useQueryClient();
  const [externalId, setExternalId] = useState("");
  const [fullName, setFullName] = useState("");
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [selection, setSelection] = useState<Record<string, string>>({});

  const drivers = useQuery({
    queryKey: ["drivers"],
    queryFn: () => apiFetch("/api/v1/drivers?limit=100", { schema: driverListSchema }),
  });
  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => apiFetch("/api/v1/vehicles?limit=100", { schema: vehicleListSchema }),
  });
  const assignments = useQuery({
    queryKey: ["assignments"],
    queryFn: () => apiFetch("/api/v1/assignments", { schema: z.array(assignmentSchema) }),
  });
  const refreshAssignments = () => void queryClient.invalidateQueries({ queryKey: ["assignments"] });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/drivers", {
        method: "POST",
        body: { external_id: externalId, full_name: fullName },
        schema: driverSchema,
      }),
    onSuccess: () => {
      setExternalId("");
      setFullName("");
      setFeedback(null);
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

  const vehicleName = new Map((vehicles.data?.items ?? []).map((v) => [v.id, v.plate ?? v.external_id]));
  const openByDriver = new Map(
    (assignments.data ?? []).filter((a) => a.ended_at === null).map((a) => [a.driver_id, a]),
  );
  const busyVehicles = new Set((assignments.data ?? []).filter((a) => a.ended_at === null).map((a) => a.vehicle_id));

  return (
    <div>
      <PageHeader title="Sürücüler" description="Sürücü kayıtları ve araç atamaları." />
      {canManage && (
        <Card className="mb-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
            className="flex flex-wrap items-end gap-3"
          >
            <TextField
              label="Dış kimlik"
              required
              value={externalId}
              onChange={(e) => setExternalId(e.target.value)}
              placeholder="SUR-001"
              hint="Telematik/cihaz verisindeki sürücü kimliği."
            />
            <TextField
              label="Ad soyad"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Ahmet Yılmaz"
            />
            <Button type="submit" loading={create.isPending}>
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
        <LoadingState />
      ) : drivers.isError ? (
        <ErrorState message={errorMessage(drivers.error, "Sürücüler yüklenemedi.")} onRetry={() => void drivers.refetch()} />
      ) : drivers.data && drivers.data.items.length > 0 ? (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Ad soyad</th>
                <th className="px-4 py-2.5 font-medium">Dış kimlik</th>
                <th className="px-4 py-2.5 font-medium">Durum</th>
                <th className="px-4 py-2.5 font-medium">Araç ataması</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {drivers.data.items.map((d) => {
                const status = DRIVER_STATUS[d.status] ?? { label: d.status, tone: "neutral" as const };
                const open = openByDriver.get(d.id);
                const chosen = selection[d.id] ?? "";
                return (
                  <tr key={d.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2.5 text-ink-900">{d.full_name}</td>
                    <td className="px-4 py-2.5 text-slate-600">{d.external_id}</td>
                    <td className="px-4 py-2.5">
                      <Badge tone={status.tone}>{status.label}</Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      {open ? (
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-slate-700">{vehicleName.get(open.vehicle_id) ?? "Araç"}</span>
                          <span className="text-xs text-slate-400">{formatDateTime(open.started_at)} itibarıyla</span>
                          {canManage && (
                            <ConfirmButton
                              label="Atamayı bitir"
                              onConfirm={() => close.mutate(open.id)}
                              loading={close.isPending}
                            />
                          )}
                        </div>
                      ) : canManage && d.status === "active" ? (
                        <div className="flex flex-wrap items-center gap-2">
                          <select
                            aria-label={`${d.full_name} için araç`}
                            value={chosen}
                            onChange={(e) => setSelection((current) => ({ ...current, [d.id]: e.target.value }))}
                            className="rounded-lg border border-slate-300 px-2 py-1 text-sm"
                          >
                            <option value="">Araç seçin…</option>
                            {(vehicles.data?.items ?? [])
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
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      ) : (
        <EmptyState message="Henüz sürücü eklenmemiş." />
      )}
    </div>
  );
}
