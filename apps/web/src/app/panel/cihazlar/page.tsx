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
  SelectField,
  SkeletonRows,
  TextField,
  formatDateTime,
  type FeedbackState,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { CAMERA_POSITIONS, DEVICE_KINDS, EQUIPMENT_STATUS, labelOf, useVehicles } from "@/lib/fleet";
import { can } from "@/lib/permissions";
import { cameraSchema, deviceListSchema, deviceSchema } from "@/lib/schemas";

function StatusBadge({ status }: { status: string }) {
  const s = EQUIPMENT_STATUS[status] ?? { label: status, tone: "neutral" as const };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export default function DevicesPage() {
  const { user } = useAuth();
  const canManage = can(user, "fleet.manage");
  const [feedback, setFeedback] = useState<FeedbackState>(null);
  return (
    <div className="max-w-6xl">
      <PageHeader
        title="Cihazlar ve Kameralar"
        description="Araçlara takılı telematik üniteleri, sensörler ve kameraların kaydı."
      />
      <Alert kind="info" className="mb-4">
        Kameralar bu panelde canlı yayınlanmaz. Kamera veya kaydediciler, Entegrasyonlar sayfasında
        “Kanıt medyası yükleme” kapsamıyla üretilen API anahtarıyla olaylara görüntü ekler.
      </Alert>
      {feedback && (
        <Alert kind={feedback.kind} className="mb-4">
          {feedback.text}
        </Alert>
      )}
      <DevicesSection canManage={canManage} onFeedback={setFeedback} />
      <CamerasSection canManage={canManage} onFeedback={setFeedback} />
    </div>
  );
}

function DevicesSection({ canManage, onFeedback }: { canManage: boolean; onFeedback: (f: FeedbackState) => void }) {
  const queryClient = useQueryClient();
  const vehicles = useVehicles();
  const [externalId, setExternalId] = useState("");
  const [kind, setKind] = useState<string>("telematics");
  const [label, setLabel] = useState("");
  const [vehicleId, setVehicleId] = useState("");

  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => apiFetch("/api/v1/devices?limit=200", { schema: deviceListSchema }),
  });
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["devices"] });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/devices", {
        method: "POST",
        body: { external_id: externalId.trim(), kind, label: label.trim() || null, vehicle_id: vehicleId || null },
        schema: deviceSchema,
      }),
    onSuccess: (device) => {
      setExternalId("");
      setLabel("");
      setVehicleId("");
      onFeedback({ kind: "success", text: `${device.external_id} cihazı kaydedildi.` });
      refresh();
    },
    onError: (err) => onFeedback({ kind: "error", text: errorMessage(err, "Cihaz kaydedilemedi.") }),
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, string | null> }) =>
      apiFetch(`/api/v1/devices/${id}`, { method: "PATCH", body, schema: deviceSchema }),
    onSuccess: () => {
      onFeedback({ kind: "success", text: "Cihaz güncellendi." });
      refresh();
    },
    onError: (err) => onFeedback({ kind: "error", text: errorMessage(err, "Cihaz güncellenemedi.") }),
  });

  return (
    <section aria-labelledby="devices-heading" className="mb-8">
      <h2 id="devices-heading" className="mb-3 text-base font-semibold text-ink-900">
        Cihazlar
      </h2>
      {canManage && (
        <Card className="mb-4">
          <SectionHeading title="Yeni cihaz" description="Dış kimlik, cihazın telemetride kullandığı kimlikle aynı olmalıdır." />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
            className="grid grid-cols-1 items-start gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_1fr_auto]"
          >
            <TextField label="Cihaz dış kimliği" required maxLength={120} value={externalId} onChange={(e) => setExternalId(e.target.value)} placeholder="TLM-0001" />
            <SelectField label="Cihaz türü" value={kind} onChange={(e) => setKind(e.target.value)}>
              {DEVICE_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </SelectField>
            <TextField label="Etiket" maxLength={200} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Ön konsol ünitesi" />
            <SelectField label="Takılı olduğu araç" value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}>
              <option value="">Araç seçilmedi</option>
              {vehicles.items.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.plate ?? v.external_id}
                </option>
              ))}
            </SelectField>
            <Button type="submit" className="lg:mt-6" loading={create.isPending} disabled={!externalId.trim()}>
              Cihaz ekle
            </Button>
          </form>
        </Card>
      )}
      {devices.isLoading ? (
        <SkeletonRows />
      ) : devices.isError ? (
        <ErrorState message={errorMessage(devices.error, "Cihazlar yüklenemedi.")} onRetry={() => void devices.refetch()} />
      ) : !devices.data?.items.length ? (
        <EmptyState message="Henüz cihaz kaydı yok." />
      ) : (
        <DataTable label="Cihazlar" headers={["Cihaz", "Tür", "Araç", "Durum", "Son sinyal", ""]}>
          {devices.data.items.map((device) => (
            <tr key={device.id} className="hover:bg-slate-50">
              <td className={CELL}>
                <p className="font-medium text-ink-900">{device.external_id}</p>
                {device.label && <p className="text-xs text-slate-500">{device.label}</p>}
              </td>
              <td className={`${CELL} text-slate-600`}>{labelOf(DEVICE_KINDS, device.kind)}</td>
              <td className={CELL}>
                {canManage ? (
                  <select
                    aria-label={`${device.external_id} için araç`}
                    value={device.vehicle_id ?? ""}
                    disabled={update.isPending}
                    onChange={(e) => update.mutate({ id: device.id, body: { vehicle_id: e.target.value || null } })}
                    className="max-w-[12rem] rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm"
                  >
                    <option value="">Araç yok</option>
                    {vehicles.items.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.plate ?? v.external_id}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="text-slate-600">{device.vehicle_id ? (vehicles.names.get(device.vehicle_id) ?? "—") : "—"}</span>
                )}
              </td>
              <td className={CELL}>
                <StatusBadge status={device.status} />
              </td>
              <td className={`${CELL} text-slate-500`}>{formatDateTime(device.last_seen_at)}</td>
              <td className={`${CELL} text-right`}>
                {canManage &&
                  (device.status === "inactive" ? (
                    <Button variant="secondary" className="px-3 py-1 text-xs" onClick={() => update.mutate({ id: device.id, body: { status: "active" } })}>
                      Etkinleştir
                    </Button>
                  ) : (
                    <ConfirmButton label="Pasifleştir" confirmLabel="Pasifleştir" onConfirm={() => update.mutate({ id: device.id, body: { status: "inactive" } })} />
                  ))}
              </td>
            </tr>
          ))}
        </DataTable>
      )}
    </section>
  );
}

function CamerasSection({ canManage, onFeedback }: { canManage: boolean; onFeedback: (f: FeedbackState) => void }) {
  const queryClient = useQueryClient();
  const vehicles = useVehicles();
  const [externalId, setExternalId] = useState("");
  const [position, setPosition] = useState<string>("road");
  const [vehicleId, setVehicleId] = useState("");
  const [deviceId, setDeviceId] = useState("");

  const cameras = useQuery({
    queryKey: ["cameras"],
    queryFn: () => apiFetch("/api/v1/cameras", { schema: z.array(cameraSchema) }),
  });
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => apiFetch("/api/v1/devices?limit=200", { schema: deviceListSchema }),
  });
  const deviceNames = new Map((devices.data?.items ?? []).map((d) => [d.id, d.label ?? d.external_id]));
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["cameras"] });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/cameras", {
        method: "POST",
        body: { external_id: externalId.trim(), position, vehicle_id: vehicleId || null, device_id: deviceId || null },
        schema: cameraSchema,
      }),
    onSuccess: (camera) => {
      setExternalId("");
      setVehicleId("");
      setDeviceId("");
      onFeedback({ kind: "success", text: `${camera.external_id} kamerası kaydedildi.` });
      refresh();
    },
    onError: (err) => onFeedback({ kind: "error", text: errorMessage(err, "Kamera kaydedilemedi.") }),
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, string | null> }) =>
      apiFetch(`/api/v1/cameras/${id}`, { method: "PATCH", body, schema: cameraSchema }),
    onSuccess: () => {
      onFeedback({ kind: "success", text: "Kamera güncellendi." });
      refresh();
    },
    onError: (err) => onFeedback({ kind: "error", text: errorMessage(err, "Kamera güncellenemedi.") }),
  });

  return (
    <section aria-labelledby="cameras-heading">
      <h2 id="cameras-heading" className="mb-3 text-base font-semibold text-ink-900">
        Kameralar
      </h2>
      {canManage && (
        <Card className="mb-4">
          <SectionHeading title="Yeni kamera" />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
            className="grid grid-cols-1 items-start gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_1fr_auto]"
          >
            <TextField label="Kamera dış kimliği" required maxLength={120} value={externalId} onChange={(e) => setExternalId(e.target.value)} placeholder="CAM-0001" />
            <SelectField label="Konum" value={position} onChange={(e) => setPosition(e.target.value)}>
              {CAMERA_POSITIONS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </SelectField>
            <SelectField label="Araç" value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}>
              <option value="">Araç seçilmedi</option>
              {vehicles.items.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.plate ?? v.external_id}
                </option>
              ))}
            </SelectField>
            <SelectField label="Bağlı cihaz" value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
              <option value="">Cihaz seçilmedi</option>
              {(devices.data?.items ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.label ?? d.external_id}
                </option>
              ))}
            </SelectField>
            <Button type="submit" className="lg:mt-6" loading={create.isPending} disabled={!externalId.trim()}>
              Kamera ekle
            </Button>
          </form>
        </Card>
      )}
      {cameras.isLoading ? (
        <SkeletonRows />
      ) : cameras.isError ? (
        <ErrorState message={errorMessage(cameras.error, "Kameralar yüklenemedi.")} onRetry={() => void cameras.refetch()} />
      ) : !cameras.data?.length ? (
        <EmptyState message="Henüz kamera kaydı yok." />
      ) : (
        <DataTable label="Kameralar" headers={["Kamera", "Konum", "Araç", "Bağlı cihaz", "Durum", ""]}>
          {cameras.data.map((camera) => (
            <tr key={camera.id} className="hover:bg-slate-50">
              <td className={`${CELL} font-medium text-ink-900`}>{camera.external_id}</td>
              <td className={`${CELL} text-slate-600`}>{labelOf(CAMERA_POSITIONS, camera.position)}</td>
              <td className={`${CELL} text-slate-600`}>{camera.vehicle_id ? (vehicles.names.get(camera.vehicle_id) ?? "—") : "—"}</td>
              <td className={`${CELL} text-slate-600`}>{camera.device_id ? (deviceNames.get(camera.device_id) ?? "—") : "—"}</td>
              <td className={CELL}>
                <StatusBadge status={camera.status} />
              </td>
              <td className={`${CELL} text-right`}>
                {canManage &&
                  (camera.status === "inactive" ? (
                    <Button variant="secondary" className="px-3 py-1 text-xs" onClick={() => update.mutate({ id: camera.id, body: { status: "active" } })}>
                      Etkinleştir
                    </Button>
                  ) : (
                    <ConfirmButton label="Pasifleştir" confirmLabel="Pasifleştir" onConfirm={() => update.mutate({ id: camera.id, body: { status: "inactive" } })} />
                  ))}
              </td>
            </tr>
          ))}
        </DataTable>
      )}
    </section>
  );
}
