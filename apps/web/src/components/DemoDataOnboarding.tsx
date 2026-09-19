"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRef, useState } from "react";
import { Alert, Button, Card } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import {
  DEMO_DATA_QUERY_KEY,
  SEEDED_QUERY_KEYS,
  seedSummaryText,
  seedUnavailableHint,
  singleFlight,
} from "@/lib/demo-seed";
import { demoDataStatusSchema, demoSeedResponseSchema, type DemoSeedResponse } from "@/lib/schemas";

const OWN_DATA_STEPS = [
  { label: "Araçlarınızı ekleyin", href: "/panel/araclar" },
  { label: "Bir veri kaynağı ve API anahtarı tanımlayın", href: "/panel/entegrasyonlar" },
  { label: "Telemetrinizi ingestion API'sine gönderin", href: "/panel/entegrasyonlar" },
];

/**
 * Overview onboarding: an empty-state card for organizations with no data and,
 * on the demo environment, a one-click synthetic seed that runs server-side
 * through the real ingestion pipeline. Once seeded, a persistent notice marks
 * everything on the dashboard as synthetic.
 */
export function DemoDataOnboarding({ empty }: { empty: boolean }) {
  const queryClient = useQueryClient();
  const [result, setResult] = useState<DemoSeedResponse | null>(null);
  const status = useQuery({
    queryKey: DEMO_DATA_QUERY_KEY,
    queryFn: () => apiFetch("/api/v1/demo-data", { schema: demoDataStatusSchema }),
  });
  // One POST per click burst, even before the button re-renders as disabled.
  const requestSeed = useRef(
    singleFlight(() =>
      apiFetch("/api/v1/demo-data/seed", { method: "POST", schema: demoSeedResponseSchema }),
    ),
  );
  const seed = useMutation({
    mutationFn: () => requestSeed.current(),
    onSuccess: async (response) => {
      setResult(response);
      await Promise.all(
        SEEDED_QUERY_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey: [...queryKey] })),
      );
    },
  });

  if (status.data?.seeded || result) {
    return <SyntheticDataNotice result={result} />;
  }
  if (!empty || status.isLoading) return null;

  const canSeed = status.data?.available === true;
  const hint = seedUnavailableHint(status.data);

  return (
    <Card className="mb-6 overflow-hidden border-brand-100 p-0">
      <div className="grid gap-0 lg:grid-cols-5">
        <div className="p-6 lg:col-span-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">Başlarken</p>
          <h2 className="mt-1 text-lg font-semibold text-ink-900">Paneliniz henüz boş</h2>
          <p className="mt-2 max-w-prose text-sm text-slate-600">
            {canSeed
              ? "Platformu hemen keşfetmek için organizasyonunuza sentetik bir demo filosu ekleyin. Veriler sunucuda gerçek telemetri işlem hattından geçer; genel bakış, harita, seferler ve güvenlik olayları gerçek API üzerinden dolar."
              : "Araçlarınız telemetri göndermeye başladığında güvenlik olayları, seferler ve canlı harita burada görünür."}
          </p>

          {canSeed && (
            <div className="mt-5">
              <Button
                onClick={() => seed.mutate()}
                loading={seed.isPending}
                aria-describedby="demo-seed-note"
              >
                {seed.isPending ? "Sentetik veri oluşturuluyor…" : "Sentetik demo verisi oluştur"}
              </Button>
              <p id="demo-seed-note" className="mt-2 text-xs text-slate-500">
                3 kurgusal araç (DMO plakalı), takma adlı sürücüler ve Ankara&apos;da sentetik rotalar. Tüm
                kayıtlar <code className="font-mono">data_origin=synthetic</code> olarak işaretlenir ve gerçek kanıt
                değildir. Yalnızca bir kez oluşturulur.
              </p>
              {seed.isPending && (
                <div role="status" aria-live="polite" className="mt-4">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-brand-100">
                    <div className="h-full w-1/3 animate-[demo-progress_1.4s_ease-in-out_infinite] rounded-full motion-reduce:w-full motion-reduce:animate-none bg-brand-600" />
                  </div>
                  <p className="mt-2 text-xs text-slate-600">
                    Filo ve sürücüler oluşturuluyor, telemetri işleniyor ve güvenlik olayları hesaplanıyor. Bu
                    işlem birkaç saniye sürebilir.
                  </p>
                </div>
              )}
              {seed.isError && (
                <Alert kind="error" className="mt-4">
                  {errorMessage(seed.error, "Sentetik demo verisi oluşturulamadı. Lütfen tekrar deneyin.")}
                </Alert>
              )}
            </div>
          )}
          {hint && (
            <Alert kind="info" className="mt-5">
              {hint}
            </Alert>
          )}
        </div>

        <div className="border-t border-slate-100 bg-slate-50/70 p-6 lg:col-span-2 lg:border-l lg:border-t-0">
          <h3 className="text-sm font-semibold text-ink-900">Kendi telemetri kaynağınızı bağlayın</h3>
          <ol className="mt-3 space-y-2">
            {OWN_DATA_STEPS.map((step, index) => (
              <li key={step.label}>
                <Link
                  href={step.href}
                  className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-ink-900 transition hover:border-brand-500"
                >
                  <span
                    aria-hidden
                    className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700"
                  >
                    {index + 1}
                  </span>
                  {step.label}
                </Link>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </Card>
  );
}

function SyntheticDataNotice({ result }: { result: DemoSeedResponse | null }) {
  return (
    <Alert kind="warning" className="mb-6">
      <p className="font-medium">Bu paneldeki veriler sentetiktir.</p>
      <p className="mt-1">
        {result
          ? `${result.message} Oluşturulan: ${seedSummaryText(result.summary)}.`
          : "Araçlar, sürücüler, seferler ve güvenlik olayları demo simülatörüyle üretildi ve gerçek kanıt değildir."}{" "}
        Tüm telemetri <code className="font-mono">data_origin=synthetic</code>,{" "}
        <code className="font-mono">environment=demo</code> olarak işaretlidir.
      </p>
    </Alert>
  );
}
