"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  CELL,
  Card,
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
import { VEHICLE_STATUS } from "@/lib/fleet";
import { can } from "@/lib/permissions";
import { fleetSchema, vehicleListSchema, vehicleSchema } from "@/lib/schemas";

type Vehicle = z.infer<typeof vehicleSchema>;

export default function VehiclesPage() {
  const { user } = useAuth();
  const canManage = can(user, "fleet.manage");
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ externalId: "", plate: "", make: "", model: "", year: "", fleetId: "" });
  const [fleetFilter, setFleetFilter] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<FeedbackState>(null);

  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get("filo");
    if (initial) setFleetFilter(initial);
  }, []);

  const query = useQuery({
    queryKey: ["vehicles", "page", fleetFilter],
    queryFn: () =>
      apiFetch(`/api/v1/vehicles?limit=200${fleetFilter ? `&fleet_id=${fleetFilter}` : ""}`, {
        schema: vehicleListSchema,
      }),
  });
  const fleets = useQuery({
    queryKey: ["fleets"],
    queryFn: () => apiFetch("/api/v1/fleets", { schema: z.array(fleetSchema) }),
  });
  const fleetNames = new Map((fleets.data ?? []).map((f) => [f.id, f.name]));
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["vehicles"] });

  const year = form.year ? Number(form.year) : null;
  const yearInvalid = year !== null && (!Number.isInteger(year) || year < 1950 || year > 2100);

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/vehicles", {
        schema: vehicleSchema,
        method: "POST",
        body: {
          external_id: form.externalId.trim(),
          plate: form.plate.trim() || null,
          make: form.make.trim() || null,
          model: form.model.trim() || null,
          year,
          fleet_id: form.fleetId || null,
        },
      }),
    onSuccess: (vehicle) => {
      setForm({ externalId: "", plate: "", make: "", model: "", year: "", fleetId: form.fleetId });
      setFeedback({ kind: "success", text: `${vehicle.plate ?? vehicle.external_id} eklendi.` });
      refresh();
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Araç eklenemedi.") }),
  });

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [key]: e.target.value }));

  return (
    <div>
      <PageHeader
        title="Araçlar"
        description="Filonuzdaki araçlar. Dış kimlik, telemetri verisindeki araç kimliğiyle eşleşmelidir."
        action={
          <label className="text-sm text-slate-600">
            <span className="sr-only">Filo filtresi</span>
            <select
              value={fleetFilter}
              onChange={(e) => setFleetFilter(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm"
            >
              <option value="">Tüm filolar</option>
              {(fleets.data ?? []).map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </label>
        }
      />
      {canManage && (
        <Card className="mb-4">
          <SectionHeading title="Yeni araç" />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!yearInvalid) create.mutate();
            }}
            className="grid grid-cols-1 items-start gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6"
          >
            <TextField label="Dış kimlik" required maxLength={120} value={form.externalId} onChange={set("externalId")} placeholder="34ABC123" hint="Telemetri verisindeki araç kimliği." />
            <TextField label="Plaka" maxLength={20} value={form.plate} onChange={set("plate")} placeholder="34 ABC 123" />
            <TextField label="Marka" maxLength={80} value={form.make} onChange={set("make")} placeholder="Ford" />
            <TextField label="Model" maxLength={80} value={form.model} onChange={set("model")} placeholder="Transit" />
            <TextField
              label="Model yılı"
              inputMode="numeric"
              value={form.year}
              onChange={set("year")}
              placeholder="2022"
              error={yearInvalid ? "1950–2100 arasında bir yıl girin." : undefined}
            />
            <SelectField label="Filo" value={form.fleetId} onChange={set("fleetId")}>
              <option value="">Filo seçilmedi</option>
              {(fleets.data ?? []).map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </SelectField>
            <div className="sm:col-span-2 lg:col-span-3 xl:col-span-6">
              <Button type="submit" loading={create.isPending} disabled={!form.externalId.trim() || yearInvalid}>
                Araç ekle
              </Button>
            </div>
          </form>
        </Card>
      )}
      {feedback && (
        <Alert kind={feedback.kind} className="mb-4">
          {feedback.text}
        </Alert>
      )}

      {query.isLoading ? (
        <SkeletonRows rows={4} />
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error, "Araçlar yüklenemedi.")} onRetry={() => void query.refetch()} />
      ) : query.data && query.data.items.length > 0 ? (
        <DataTable label="Araçlar" headers={["Dış kimlik", "Plaka", "Marka / model", "Filo", "Durum", "Eklenme", ""]}>
          {query.data.items.map((v) =>
            editing === v.id ? (
              <EditRow
                key={v.id}
                vehicle={v}
                fleets={fleets.data ?? []}
                onDone={(message) => {
                  setEditing(null);
                  if (message) setFeedback(message);
                  refresh();
                }}
              />
            ) : (
              <tr key={v.id} className="hover:bg-slate-50">
                <td className={`${CELL} text-ink-900`}>
                  {v.external_id}
                  {v.label && <p className="text-xs text-slate-500">{v.label}</p>}
                </td>
                <td className={`${CELL} text-slate-600`}>{v.plate ?? "—"}</td>
                <td className={`${CELL} text-slate-600`}>
                  {[v.make, v.model].filter(Boolean).join(" ") || "—"}
                  {v.year ? <span className="text-slate-400"> · {v.year}</span> : null}
                </td>
                <td className={`${CELL} text-slate-600`}>{v.fleet_id ? (fleetNames.get(v.fleet_id) ?? "—") : "—"}</td>
                <td className={CELL}>
                  <Badge tone={(VEHICLE_STATUS[v.status] ?? { tone: "neutral" as const }).tone}>
                    {VEHICLE_STATUS[v.status]?.label ?? v.status}
                  </Badge>
                </td>
                <td className={`${CELL} text-slate-500`}>{formatDateTime(v.created_at)}</td>
                <td className={`${CELL} text-right`}>
                  {canManage && (
                    <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => setEditing(v.id)} aria-label={`${v.external_id} aracını düzenle`}>
                      Düzenle
                    </Button>
                  )}
                </td>
              </tr>
            ),
          )}
        </DataTable>
      ) : (
        <EmptyState
          message={
            fleetFilter
              ? "Bu filoda araç yok."
              : canManage
                ? "Henüz araç eklenmemiş. Yukarıdaki formu kullanarak ilk aracınızı ekleyin."
                : "Henüz araç eklenmemiş."
          }
        />
      )}
    </div>
  );
}

function EditRow({
  vehicle,
  fleets,
  onDone,
}: {
  vehicle: Vehicle;
  fleets: { id: string; name: string }[];
  onDone: (feedback: FeedbackState) => void;
}) {
  const [plate, setPlate] = useState(vehicle.plate ?? "");
  const [label, setLabel] = useState(vehicle.label ?? "");
  const [status, setStatus] = useState(vehicle.status);
  const [fleetId, setFleetId] = useState(vehicle.fleet_id ?? "");
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/vehicles/${vehicle.id}`, {
        method: "PATCH",
        schema: vehicleSchema,
        body: { plate: plate.trim() || null, label: label.trim() || null, status, fleet_id: fleetId || null },
      }),
    onSuccess: () => onDone({ kind: "success", text: "Araç güncellendi." }),
    onError: (err) => setError(errorMessage(err, "Araç güncellenemedi.")),
  });
  return (
    <tr className="bg-brand-50/40">
      <td colSpan={7} className="px-4 py-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
          className="grid grid-cols-1 items-start gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_1fr_auto]"
          aria-label={`${vehicle.external_id} aracını düzenle`}
        >
          <TextField label="Plaka" maxLength={20} value={plate} onChange={(e) => setPlate(e.target.value)} />
          <TextField label="Etiket" maxLength={200} value={label} onChange={(e) => setLabel(e.target.value)} />
          <SelectField label="Durum" value={status} onChange={(e) => setStatus(e.target.value)}>
            {Object.entries(VEHICLE_STATUS).map(([value, s]) => (
              <option key={value} value={value}>
                {s.label}
              </option>
            ))}
          </SelectField>
          <SelectField label="Filo" value={fleetId} onChange={(e) => setFleetId(e.target.value)}>
            <option value="">Filo yok</option>
            {fleets.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </SelectField>
          <div className="flex gap-2 lg:mt-6">
            <Button type="submit" loading={save.isPending}>
              Kaydet
            </Button>
            <Button variant="secondary" onClick={() => onDone(null)}>
              Vazgeç
            </Button>
          </div>
        </form>
        {error && (
          <Alert kind="error" className="mt-2">
            {error}
          </Alert>
        )}
      </td>
    </tr>
  );
}
