"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { z } from "zod";
import {
  Alert,
  Button,
  CELL,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  PageHeader,
  SectionHeading,
  SkeletonRows,
  TextField,
  type FeedbackState,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useVehicles } from "@/lib/fleet";
import { can } from "@/lib/permissions";
import { fleetSchema } from "@/lib/schemas";

export default function FleetsPage() {
  const { user } = useAuth();
  const canManage = can(user, "fleet.manage");
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [region, setRegion] = useState("");
  const [feedback, setFeedback] = useState<FeedbackState>(null);

  const fleets = useQuery({
    queryKey: ["fleets"],
    queryFn: () => apiFetch("/api/v1/fleets", { schema: z.array(fleetSchema) }),
  });
  const vehicles = useVehicles();

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/fleets", {
        method: "POST",
        body: { name: name.trim(), region: region.trim() || null },
        schema: fleetSchema,
      }),
    onSuccess: (fleet) => {
      setName("");
      setRegion("");
      setFeedback({ kind: "success", text: `“${fleet.name}” filosu oluşturuldu.` });
      void queryClient.invalidateQueries({ queryKey: ["fleets"] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Filo oluşturulamadı.") }),
  });

  const countByFleet = new Map<string, number>();
  let unassigned = 0;
  for (const vehicle of vehicles.items) {
    if (vehicle.fleet_id) countByFleet.set(vehicle.fleet_id, (countByFleet.get(vehicle.fleet_id) ?? 0) + 1);
    else unassigned += 1;
  }

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Filolar"
        description="Araçlarınızı bölge veya işletme birimine göre gruplayın. Araçları filoya Araçlar sayfasından atarsınız."
      />
      {canManage && (
        <Card className="mb-4">
          <SectionHeading title="Yeni filo" />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
            className="grid grid-cols-1 items-start gap-3 sm:grid-cols-[1fr_1fr_auto]"
          >
            <TextField
              label="Filo adı"
              required
              minLength={2}
              maxLength={200}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Marmara Dağıtım"
            />
            <TextField
              label="Bölge"
              maxLength={120}
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              placeholder="İstanbul Avrupa Yakası"
            />
            <Button type="submit" className="sm:mt-6" loading={create.isPending} disabled={name.trim().length < 2}>
              Filo oluştur
            </Button>
          </form>
        </Card>
      )}
      {feedback && (
        <Alert kind={feedback.kind} className="mb-4">
          {feedback.text}
        </Alert>
      )}

      {fleets.isLoading ? (
        <SkeletonRows />
      ) : fleets.isError ? (
        <ErrorState message={errorMessage(fleets.error, "Filolar yüklenemedi.")} onRetry={() => void fleets.refetch()} />
      ) : !fleets.data?.length ? (
        <EmptyState
          message={
            canManage
              ? "Henüz filo tanımlanmadı. Araçları gruplamak için yukarıdan ilk filonuzu oluşturun."
              : "Henüz filo tanımlanmadı."
          }
        />
      ) : (
        <>
          <DataTable label="Filolar" headers={["Filo", "Bölge", "Araç sayısı", ""]}>
            {fleets.data.map((fleet) => (
              <tr key={fleet.id} className="hover:bg-slate-50">
                <td className={`${CELL} font-medium text-ink-900`}>{fleet.name}</td>
                <td className={`${CELL} text-slate-600`}>{fleet.region ?? "—"}</td>
                <td className={`${CELL} text-slate-600`}>
                  {vehicles.query.isLoading ? "…" : (countByFleet.get(fleet.id) ?? 0)}
                </td>
                <td className={`${CELL} text-right`}>
                  <Link href={`/panel/araclar?filo=${fleet.id}`} className="text-xs font-medium text-brand-700 hover:underline">
                    Araçları gör
                  </Link>
                </td>
              </tr>
            ))}
          </DataTable>
          {!vehicles.query.isLoading && unassigned > 0 && (
            <p className="mt-3 text-xs text-slate-500">{unassigned} araç henüz bir filoya atanmamış.</p>
          )}
        </>
      )}
    </div>
  );
}
