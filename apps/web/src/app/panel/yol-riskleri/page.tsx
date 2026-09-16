"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import { FleetMap } from "@/components/FleetMap";
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
  SeverityBadge,
  SkeletonRows,
  TextField,
  formatNumber,
  type FeedbackState,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { geofenceSchema, roadRiskSchema } from "@/lib/schemas";

const GEOFENCE_KINDS = [
  { value: "high_risk", label: "Yüksek riskli alan" },
  { value: "depot", label: "Depo / garaj" },
  { value: "restricted", label: "Kısıtlı alan" },
  { value: "custom", label: "Özel alan" },
] as const;

const REVIEW_LABELS: Record<string, string> = {
  pending: "İnceleme bekliyor",
  confirmed: "Doğrulandı",
  rejected: "Reddedildi",
};

export default function RoadRisksPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canManageRisks = can(user, "risks.manage");
  const canManageGeofences = can(user, "geofences.manage");
  const [feedback, setFeedback] = useState<FeedbackState>(null);
  const [draft, setDraft] = useState({ name: "", kind: "high_risk", latitude: "", longitude: "", radius: "250" });

  const risks = useQuery({
    queryKey: ["road-risks"],
    queryFn: () => apiFetch("/api/v1/road-risks", { schema: z.array(roadRiskSchema) }),
  });
  const geofences = useQuery({
    queryKey: ["geofences"],
    queryFn: () => apiFetch("/api/v1/geofences", { schema: z.array(geofenceSchema) }),
  });

  const rebuild = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/road-risks/rebuild", { method: "POST", schema: z.object({ road_risks: z.number() }) }),
    onSuccess: (data) => {
      setFeedback({ kind: "success", text: `${data.road_risks} yol riski bölgesi hesaplandı.` });
      void queryClient.invalidateQueries({ queryKey: ["road-risks"] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Yol riskleri hesaplanamadı.") }),
  });

  const latitude = Number(draft.latitude);
  const longitude = Number(draft.longitude);
  const radius = Number(draft.radius);
  const latInvalid = draft.latitude !== "" && (!Number.isFinite(latitude) || latitude < -90 || latitude > 90);
  const lonInvalid = draft.longitude !== "" && (!Number.isFinite(longitude) || longitude < -180 || longitude > 180);
  const radiusInvalid = !Number.isFinite(radius) || radius <= 0 || radius > 100_000;
  const draftReady =
    draft.name.trim().length >= 2 && draft.latitude !== "" && draft.longitude !== "" && !latInvalid && !lonInvalid && !radiusInvalid;

  const createGeofence = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/geofences", {
        method: "POST",
        schema: geofenceSchema,
        body: {
          name: draft.name.trim(),
          kind: draft.kind,
          center_latitude: latitude,
          center_longitude: longitude,
          radius_m: radius,
        },
      }),
    onSuccess: (geofence) => {
      setDraft({ name: "", kind: draft.kind, latitude: "", longitude: "", radius: draft.radius });
      setFeedback({ kind: "success", text: `“${geofence.name}” alanı oluşturuldu.` });
      void queryClient.invalidateQueries({ queryKey: ["geofences"] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Coğrafi alan oluşturulamadı.") }),
  });

  const set = (key: keyof typeof draft) => (e: { target: { value: string } }) =>
    setDraft((current) => ({ ...current, [key]: e.target.value }));

  const draftArea =
    draftReady || (draft.latitude !== "" && draft.longitude !== "" && !latInvalid && !lonInvalid)
      ? [
          {
            id: "draft",
            latitude,
            longitude,
            radiusM: radiusInvalid ? 250 : radius,
            label: draft.name.trim() || "Yeni alan (taslak)",
          },
        ]
      : [];

  return (
    <div>
      <PageHeader
        title="Yol Riskleri"
        description="Tekrarlanan sert olaylardan çıkarılan yol riski bölgeleri ve tanımladığınız coğrafi alanlar."
        action={
          canManageRisks ? (
            <Button variant="secondary" loading={rebuild.isPending} onClick={() => rebuild.mutate()}>
              Risk bölgelerini yeniden hesapla
            </Button>
          ) : null
        }
      />
      {feedback && (
        <Alert kind={feedback.kind} className="mb-4">
          {feedback.text}
        </Alert>
      )}

      <FleetMap
        label="Yol riski ve coğrafi alan haritası"
        className="mb-2 h-96"
        data={{
          risks: (risks.data ?? []).map((r) => ({
            id: r.id,
            latitude: r.center_latitude,
            longitude: r.center_longitude,
            radiusM: r.radius_m,
            severity: r.inferred_severity,
            label: "Tekrarlanan sert olay bölgesi",
            detail: `${r.observed_count} gözlem · güven %${Math.round(r.confidence * 100)}`,
          })),
          geofences: [
            ...(geofences.data ?? []).map((g) => ({
              id: g.id,
              latitude: g.center_latitude,
              longitude: g.center_longitude,
              radiusM: g.radius_m,
              label: g.name,
              detail: `${GEOFENCE_KINDS.find((k) => k.value === g.kind)?.label ?? g.kind} · ${Math.round(g.radius_m)} m`,
            })),
            ...draftArea,
          ],
        }}
        onPick={
          canManageGeofences
            ? (lat, lon) => setDraft((current) => ({ ...current, latitude: lat.toFixed(5), longitude: lon.toFixed(5) }))
            : undefined
        }
      />
      {canManageGeofences && (
        <p className="mb-6 text-xs text-slate-500">
          Yeni coğrafi alanın merkezini seçmek için haritada boş bir noktaya tıklayın veya koordinatları elle girin.
        </p>
      )}

      <section aria-labelledby="risks-heading" className="mb-8">
        <h2 id="risks-heading" className="mb-3 text-base font-semibold text-ink-900">
          Yol riski bölgeleri
        </h2>
        {risks.isLoading ? (
          <SkeletonRows />
        ) : risks.isError ? (
          <ErrorState message={errorMessage(risks.error, "Yol riskleri yüklenemedi.")} onRetry={() => void risks.refetch()} />
        ) : !risks.data?.length ? (
          <EmptyState message="Henüz yol riski tespit edilmedi. Aynı bölgede yeterli olay biriktiğinde yeniden hesaplama ile kümeleme yapılır." />
        ) : (
          <DataTable label="Yol riski bölgeleri" headers={["Tür", "Şiddet", "Gözlem", "Güven", "Yarıçap", "Kaynak", "Durum"]}>
            {risks.data.map((r) => (
              <tr key={r.id} className="hover:bg-slate-50">
                <td className={`${CELL} text-ink-900`}>Tekrarlanan sert olay bölgesi</td>
                <td className={CELL}>
                  <SeverityBadge severity={r.inferred_severity} />
                </td>
                <td className={`${CELL} text-slate-600`}>{r.observed_count}</td>
                <td className={`${CELL} text-slate-600`}>%{Math.round(r.confidence * 100)}</td>
                <td className={`${CELL} text-slate-600`}>{formatNumber(r.radius_m, 0)} m</td>
                <td className={`${CELL} text-slate-600`}>{r.source === "derived" ? "Olaylardan türetildi" : r.source}</td>
                <td className={CELL}>
                  <Badge tone={r.review_status === "confirmed" ? "success" : "neutral"}>
                    {REVIEW_LABELS[r.review_status] ?? r.review_status}
                  </Badge>
                </td>
              </tr>
            ))}
          </DataTable>
        )}
      </section>

      <section aria-labelledby="geofences-heading">
        <h2 id="geofences-heading" className="mb-3 text-base font-semibold text-ink-900">
          Coğrafi alanlar
        </h2>
        {canManageGeofences && (
          <Card className="mb-4">
            <SectionHeading title="Yeni coğrafi alan" description="Depo, kısıtlı bölge veya bilinen riskli kavşak gibi alanları işaretleyin." />
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (draftReady) createGeofence.mutate();
              }}
              className="grid grid-cols-1 items-start gap-3 sm:grid-cols-2 lg:grid-cols-5"
            >
              <TextField label="Alan adı" required minLength={2} maxLength={200} value={draft.name} onChange={set("name")} placeholder="Merkez depo" />
              <SelectField label="Alan türü" value={draft.kind} onChange={set("kind")}>
                {GEOFENCE_KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </SelectField>
              <TextField label="Enlem" inputMode="decimal" required value={draft.latitude} onChange={set("latitude")} placeholder="39.92080" error={latInvalid ? "-90 ile 90 arasında olmalı." : undefined} />
              <TextField label="Boylam" inputMode="decimal" required value={draft.longitude} onChange={set("longitude")} placeholder="32.85410" error={lonInvalid ? "-180 ile 180 arasında olmalı." : undefined} />
              <TextField label="Yarıçap (m)" inputMode="numeric" required value={draft.radius} onChange={set("radius")} error={radiusInvalid ? "1–100000 m arasında olmalı." : undefined} />
              <div className="sm:col-span-2 lg:col-span-5">
                <Button type="submit" loading={createGeofence.isPending} disabled={!draftReady}>
                  Alan oluştur
                </Button>
              </div>
            </form>
          </Card>
        )}
        {geofences.isLoading ? (
          <SkeletonRows />
        ) : geofences.isError ? (
          <ErrorState message={errorMessage(geofences.error, "Coğrafi alanlar yüklenemedi.")} onRetry={() => void geofences.refetch()} />
        ) : !geofences.data?.length ? (
          <EmptyState message="Henüz coğrafi alan tanımlanmadı." />
        ) : (
          <DataTable label="Coğrafi alanlar" headers={["Ad", "Tür", "Merkez", "Yarıçap", "Durum"]}>
            {geofences.data.map((g) => (
              <tr key={g.id} className="hover:bg-slate-50">
                <td className={`${CELL} font-medium text-ink-900`}>{g.name}</td>
                <td className={`${CELL} text-slate-600`}>{GEOFENCE_KINDS.find((k) => k.value === g.kind)?.label ?? g.kind}</td>
                <td className={`${CELL} font-mono text-xs text-slate-500`}>
                  {g.center_latitude.toFixed(5)}, {g.center_longitude.toFixed(5)}
                </td>
                <td className={`${CELL} text-slate-600`}>{formatNumber(g.radius_m, 0)} m</td>
                <td className={CELL}>
                  <Badge tone={g.active ? "success" : "neutral"}>{g.active ? "Etkin" : "Pasif"}</Badge>
                </td>
              </tr>
            ))}
          </DataTable>
        )}
      </section>
    </div>
  );
}
