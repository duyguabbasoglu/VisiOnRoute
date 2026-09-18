"use client";

import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";
import { FleetMap, type FleetMapData, type MapSelection } from "@/components/FleetMap";
import { PublicFooter, PublicHeader, SyntheticNotice } from "@/components/PublicSite";
import { CTA_STYLES } from "@/components/public-styles";
import { ReviewBadge, SEVERITY_LABELS, SeverityBadge, formatNumber } from "@/components/ui";
import {
  DEMO_DRIVER_TOTAL,
  DEMO_EVENTS,
  DEMO_EVENT_LABELS,
  DEMO_HOURLY_EVENTS_24H,
  DEMO_ORGANIZATION,
  DEMO_PENDING_REVIEW,
  DEMO_ROAD_RISKS,
  DEMO_SEVERITIES,
  DEMO_SEVERITY_COUNTS_24H,
  DEMO_TRIPS_24H,
  DEMO_TYPE_COUNTS_24H,
  DEMO_VEHICLES,
  DEMO_VEHICLE_TOTAL,
  MIN_EXPOSURE_KM,
  activeDriverCount,
  activeVehicleCount,
  averageRiskIndex,
  driverRanking,
  eventsPer100Km,
  explainEvent,
  relativeMinutes,
  totalEvents24h,
  type DemoEvent,
  type DemoEventType,
} from "@/lib/demo-data";

/**
 * Public, read-only showcase of the overview screen. Renders only the
 * synthetic fixtures in lib/demo-data — it never calls the API, so no tenant
 * data can reach this page and no action here can change anything.
 */

const SEVERITY_BAR: Record<string, string> = {
  low: "bg-risk-low",
  medium: "bg-risk-medium",
  high: "bg-orange-600",
  critical: "bg-red-700",
};

function Panel({
  title,
  description,
  action,
  children,
  className = "",
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink-900">
            {title}
            <SyntheticTag />
          </h2>
          {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function SyntheticTag() {
  return (
    <span className="rounded bg-amber-100 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-amber-900">
      Sentetik
    </span>
  );
}

function Kpi({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-slate-500">{label}</p>
        <SyntheticTag />
      </div>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-ink-900">{value}</p>
      <p className="mt-1 text-xs text-slate-400">{hint}</p>
    </div>
  );
}

/** Where the real product would act, the demo explains and points to sign-in. */
function GatedCallout({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-brand-100 bg-brand-50 p-3 text-sm text-brand-900">
      <p>{children}</p>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm font-medium">
        <Link href="/giris" className="text-brand-700 hover:underline">
          Giriş yap
        </Link>
        <Link href="/kayit" className="text-brand-700 hover:underline">
          Yeni organizasyon oluştur
        </Link>
      </div>
    </div>
  );
}

export function DemoDashboard() {
  const [selectedId, setSelectedId] = useState<string>(DEMO_EVENTS[0]?.id ?? "");
  const [vehicleNotice, setVehicleNotice] = useState<string | null>(null);
  const selected = DEMO_EVENTS.find((e) => e.id === selectedId) ?? null;

  const total = totalEvents24h();
  const ranking = useMemo(() => driverRanking(), []);

  const mapData = useMemo<FleetMapData>(
    () => ({
      vehicles: DEMO_VEHICLES.map((v) => ({
        id: v.id,
        latitude: v.latitude,
        longitude: v.longitude,
        label: `${v.plate} (sentetik)`,
        detail: `${v.driver} · ${v.area} · ${v.stale ? "konum eski" : `${v.speedKph} km/sa`}`,
        stale: v.stale,
      })),
      events: DEMO_EVENTS.map((e) => ({
        id: e.id,
        latitude: e.latitude,
        longitude: e.longitude,
        label: `${DEMO_EVENT_LABELS[e.type]} · ${SEVERITY_LABELS[e.severity]}`,
        detail: `${e.vehicle} · ${relativeMinutes(e.minutesAgo)} (sentetik)`,
        severity: e.severity,
      })),
      risks: DEMO_ROAD_RISKS.map((r) => ({
        id: r.id,
        latitude: r.latitude,
        longitude: r.longitude,
        radiusM: r.radiusM,
        severity: r.severity,
        label: `Yol riski · ${r.name}`,
        detail: `${r.eventCount} olay · baskın: ${DEMO_EVENT_LABELS[r.dominant]} (sentetik)`,
      })),
    }),
    [],
  );

  function onMapSelect(selection: MapSelection) {
    if (selection.kind === "event") {
      setSelectedId(selection.id);
      setVehicleNotice(null);
    } else if (selection.kind === "vehicle") {
      const vehicle = DEMO_VEHICLES.find((v) => v.id === selection.id);
      setVehicleNotice(vehicle ? vehicle.plate : null);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <PublicHeader wide />

      <div className="bg-ink-900 pb-24 pt-8 text-slate-200">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded-full bg-white/10 px-2.5 py-1 text-slate-200">{DEMO_ORGANIZATION}</span>
                <span className="rounded-full bg-amber-400/15 px-2.5 py-1 font-medium text-amber-200">Sentetik veri</span>
                <span className="rounded-full bg-white/5 px-2.5 py-1 text-slate-400">Salt okunur önizleme</span>
              </div>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white">Demo panel · Genel Bakış</h1>
              <p className="mt-2 max-w-2xl text-sm text-slate-400">
                Gerçek uygulamanın genel bakış ekranı, kurgusal bir filo ile. Hiçbir değer API&apos;den gelmez; sayılar
                sabit, tekrarlanabilir demo verileridir ve zamanlar sabit bir demo anına göredir.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href="/kayit" className={CTA_STYLES.primary}>
                Kendi organizasyonunu oluştur
              </Link>
              <Link href="/giris" className={CTA_STYLES.secondary}>
                Giriş yap
              </Link>
            </div>
          </div>
          <div className="mt-6">
            <SyntheticNotice />
          </div>
        </div>
      </div>

      <main id="icerik" className="mx-auto -mt-16 max-w-7xl space-y-6 px-4 pb-16 sm:px-6">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <Kpi label="Aktif araç" value={`${activeVehicleCount()} / ${DEMO_VEHICLE_TOTAL}`} hint="1 aracın konumu eski" />
          <Kpi label="Aktif sürücü" value={`${activeDriverCount()} / ${DEMO_DRIVER_TOTAL}`} hint="Şu an atanmış sürücü" />
          <Kpi label="Güvenlik olayı" value={String(total)} hint={`Son 24 saat · ${DEMO_PENDING_REVIEW} inceleme bekliyor`} />
          <Kpi
            label="Ort. risk endeksi"
            value={formatNumber(averageRiskIndex(), 2)}
            hint="Ağırlıklı olay / 100 km · düşük = iyi"
          />
          <div className="col-span-2 lg:col-span-1">
            <Kpi label="100 km başına olay" value={formatNumber(eventsPer100Km(), 2)} hint={`${formatNumber(DEMO_TRIPS_24H.distanceKm, 0)} km · son 24 saat`} />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
          <Panel
            title="Operasyon haritası"
            description="Kurgusal araç konumları, olaylar ve yol riski alanları"
            className="lg:col-span-3"
          >
            <FleetMap label="Sentetik araçlar, olaylar ve yol riski alanları" className="h-80 sm:h-96" data={mapData} onSelect={onMapSelect} />
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
              <LegendDot className="border-2 border-blue-400 bg-ink-900" label="Araç" />
              <LegendDot className="border-2 border-blue-400 bg-slate-400" label="Eski konum" />
              <LegendDot className="bg-risk-medium" label="Olay (renk = şiddet)" />
              <LegendDot className="bg-orange-500/30 ring-1 ring-orange-500" label="Yol riski alanı" />
            </div>
            {vehicleNotice && (
              <div className="mt-3">
                <GatedCallout>
                  <strong>{vehicleNotice}</strong> için sefer detayı ve rota izi gerçek uygulamada, oturum açtıktan sonra
                  görüntülenir.
                </GatedCallout>
              </div>
            )}
          </Panel>

          <Panel title="Son güvenlik olayları" description="Ayrıntı için bir olay seçin" className="lg:col-span-2">
            <ul className="divide-y divide-slate-100" aria-label="Son güvenlik olayları (sentetik)">
              {DEMO_EVENTS.slice(0, 7).map((event) => {
                const active = event.id === selectedId;
                return (
                  <li key={event.id}>
                    <button
                      type="button"
                      aria-pressed={active}
                      onClick={() => {
                        setSelectedId(event.id);
                        setVehicleNotice(null);
                      }}
                      className={`flex w-full items-center justify-between gap-3 rounded-lg px-2 py-2.5 text-left transition ${
                        active ? "bg-brand-50" : "hover:bg-slate-50"
                      }`}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm text-ink-900">
                          {DEMO_EVENT_LABELS[event.type]} · {event.vehicle}
                        </span>
                        <span className="block text-xs text-slate-500">
                          {event.place} · {relativeMinutes(event.minutesAgo)}
                        </span>
                      </span>
                      <SeverityBadge severity={event.severity} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </Panel>
        </div>

        {selected && <EventDetail key={selected.id} event={selected} />}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Panel title="Saatlik olay dağılımı" description="Son 24 saat · Europe/Istanbul" className="lg:col-span-2">
            <HourlyChart />
          </Panel>
          <Panel title="Sefer ve aktivite özeti" description="Son 24 saat">
            <dl className="grid grid-cols-2 gap-3">
              <SummaryItem label="Tamamlanan sefer" value={String(DEMO_TRIPS_24H.completed)} />
              <SummaryItem label="Devam eden sefer" value={String(DEMO_TRIPS_24H.ongoing)} />
              <SummaryItem label="Toplam mesafe" value={`${formatNumber(DEMO_TRIPS_24H.distanceKm, 0)} km`} />
              <SummaryItem label="Sürüş süresi" value={`${DEMO_TRIPS_24H.drivingHours} sa`} />
              <SummaryItem label="İnceleme bekleyen" value={String(DEMO_PENDING_REVIEW)} />
              <SummaryItem label="Açık koçluk görevi" value={String(DEMO_TRIPS_24H.openCoaching)} />
            </dl>
          </Panel>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Panel title="Şiddet dağılımı" description={`Son 24 saat · ${total} olay`}>
            <BarList
              label="Şiddete göre olay sayısı"
              rows={DEMO_SEVERITIES.map((s) => ({
                key: s,
                label: SEVERITY_LABELS[s] ?? s,
                value: DEMO_SEVERITY_COUNTS_24H[s],
                color: SEVERITY_BAR[s] ?? "bg-slate-400",
              }))}
              total={total}
            />
          </Panel>
          <Panel title="Kurala göre olaylar" description="Deterministik kural setleri">
            <BarList
              label="Kurala göre olay sayısı"
              rows={(Object.keys(DEMO_TYPE_COUNTS_24H) as DemoEventType[]).map((t) => ({
                key: t,
                label: DEMO_EVENT_LABELS[t],
                value: DEMO_TYPE_COUNTS_24H[t],
                color: "bg-brand-500",
              }))}
              total={total}
            />
          </Panel>
          <Panel title="Yol riski bölgeleri" description="Tekrarlayan sert olay kümeleri">
            <ul className="space-y-3">
              {DEMO_ROAD_RISKS.map((risk) => (
                <li key={risk.id} className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm text-ink-900">{risk.name}</p>
                    <p className="text-xs text-slate-500">
                      {risk.eventCount} olay · baskın: {DEMO_EVENT_LABELS[risk.dominant].toLocaleLowerCase("tr-TR")} ·{" "}
                      {formatNumber(risk.radiusM / 1000, 1)} km yarıçap
                    </p>
                  </div>
                  <SeverityBadge severity={risk.severity} />
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        <Panel
          title="Sürücü risk sıralaması"
          description={`Son 7 gün · risk endeksi = ağırlıklı olay / 100 km · ${MIN_EXPOSURE_KM} km altında skor üretilmez`}
        >
          <div className="-mx-5 overflow-x-auto">
            <table aria-label="Sürücü risk sıralaması (sentetik)" className="w-full min-w-[40rem] text-sm">
              <thead className="border-y border-slate-200 bg-slate-50 text-left text-xs text-slate-500">
                <tr>
                  <th scope="col" className="px-5 py-2.5 font-medium">#</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Sürücü</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">Mesafe</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">Olay</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Risk endeksi</th>
                  <th scope="col" className="px-5 py-2.5 text-right font-medium">Güvenlik skoru</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {ranking.map((driver, index) => {
                  const maxIndex = ranking[0]?.riskIndex ?? 1;
                  return (
                    <tr key={driver.code}>
                      <td className="px-5 py-2.5 text-slate-400 tabular-nums">{driver.riskIndex === null ? "—" : index + 1}</td>
                      <td className="px-3 py-2.5 text-ink-900">{driver.code}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-slate-600">
                        {formatNumber(driver.exposureKm, 0)} km
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-slate-600">{driver.eventCount}</td>
                      <td className="px-3 py-2.5">
                        {driver.riskIndex === null ? (
                          <span className="text-xs text-slate-500">Yetersiz maruziyet</span>
                        ) : (
                          <span className="flex items-center gap-2">
                            <span className="h-1.5 w-24 rounded-full bg-slate-100 sm:w-32">
                              <span
                                className="block h-1.5 rounded-full bg-brand-500"
                                style={{ width: `${Math.max(4, (driver.riskIndex / maxIndex) * 100)}%` }}
                              />
                            </span>
                            <span className="tabular-nums text-slate-700">{formatNumber(driver.riskIndex, 2)}</span>
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-2.5 text-right tabular-nums font-medium text-ink-900">
                        {driver.score === null ? "—" : formatNumber(driver.score, 1)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-xs leading-relaxed text-slate-500">
            Skorlar gerçek üründeki formülle hesaplanır (şiddet ağırlıkları 1 / 2,5 / 5 / 9; skor = 100·e^(−endeks/14,43)).
            Sıralama bir koçluk önceliği önerisidir; disiplin kararı değildir ve demografik değişken içermez.
          </p>
        </Panel>

        <section className="rounded-2xl bg-ink-900 px-6 py-8 text-slate-300 sm:px-10">
          <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr] lg:items-center">
            <div>
              <h2 className="text-xl font-semibold text-white">Bu bir önizleme; gerçek uygulama daha fazlasını yapar.</h2>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">
                Olay incelemesi, koçluk ataması, kanıt erişimi, bildirim kuralları, raporlar ve KVKK iş akışları kimlik
                doğrulaması, rol tabanlı izinler ve kiracı izolasyonuyla çalışır. Kendi organizasyonunuzda simülatörle
                sentetik telemetri üretebilirsiniz.
              </p>
            </div>
            <div className="flex flex-wrap gap-3 lg:justify-end">
              <Link href="/kayit" className={CTA_STYLES.amber}>
                Yeni organizasyon oluştur
              </Link>
              <Link href="/giris" className={CTA_STYLES.secondary}>
                Giriş yap
              </Link>
            </div>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}

function EventDetail({ event }: { event: DemoEvent }) {
  const [gated, setGated] = useState<string | null>(null);
  return (
    <section
      aria-label="Seçili olay ayrıntısı"
      aria-live="polite"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs text-slate-500">
            Olay ayrıntısı <SyntheticTag />
          </p>
          <h2 className="mt-1 text-lg font-semibold text-ink-900">
            {DEMO_EVENT_LABELS[event.type]} · {event.vehicle}
          </h2>
          <p className="text-sm text-slate-500">
            {event.driver} · {event.place} · {relativeMinutes(event.minutesAgo)}
          </p>
        </div>
        <div className="flex gap-2">
          <SeverityBadge severity={event.severity} />
          <ReviewBadge status={event.review} />
        </div>
      </div>

      <div className="mt-5 grid gap-5 md:grid-cols-3">
        <div className="md:col-span-2">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Neden tetiklendi?</p>
          <p className="mt-1 text-sm text-slate-800">{explainEvent(event)}</p>
          <div className="mt-4">
            <div className="flex justify-between text-xs text-slate-500">
              <span>Güven</span>
              <span className="tabular-nums">%{Math.round(event.confidence * 100)}</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-slate-100">
              <div
                className={`h-1.5 rounded-full ${event.confidence < 0.6 ? "bg-risk-medium" : "bg-brand-500"}`}
                style={{ width: `${event.confidence * 100}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Şiddet ve güven ayrı hesaplanır; düşük güvenli olaylar skoru şişirmez, incelemeye işaretlenir.
            </p>
          </div>
          <p className="mt-4 text-sm text-slate-600">
            Kanıt medyası:{" "}
            {event.hasEvidence
              ? "var — gerçek uygulamada özel depolamadan kısa ömürlü imzalı bağlantıyla açılır ve erişim kaydedilir."
              : "yok."}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">İnceleme işlemleri</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {["Onayla", "Reddet", "Koçluk ata"].map((action) => (
              <button
                key={action}
                type="button"
                onClick={() => setGated(action)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
              >
                <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden>
                  <rect x="3" y="7" width="10" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
                  <path d="M5.5 7V5a2.5 2.5 0 015 0v2" fill="none" stroke="currentColor" strokeWidth="1.4" />
                </svg>
                {action}
              </button>
            ))}
          </div>
          <div className="mt-3">
            {gated ? (
              <GatedCallout>
                “{gated}” demo panelde çalışmaz. İnceleme ve koçluk işlemleri yalnızca oturum açmış, yetkili kullanıcılarca
                kendi organizasyonlarında yapılır.
              </GatedCallout>
            ) : (
              <p className="text-xs text-slate-500">Demo salt okunurdur; hiçbir işlem veri değiştirmez.</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function LegendDot({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden className={`inline-block h-3 w-3 rounded-full ${className}`} />
      {label}
    </span>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold tabular-nums text-ink-900">{value}</dd>
    </div>
  );
}

function BarList({
  label,
  rows,
  total,
}: {
  label: string;
  rows: { key: string; label: string; value: number; color: string }[];
  total: number;
}) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <ul aria-label={label} className="space-y-3">
      {rows.map((row) => (
        <li key={row.key} title={`${row.label}: ${row.value} olay (%${Math.round((row.value / total) * 100)})`}>
          <div className="flex justify-between text-sm">
            <span className="text-slate-700">{row.label}</span>
            <span className="tabular-nums text-slate-900">
              {row.value} <span className="text-xs text-slate-400">%{Math.round((row.value / total) * 100)}</span>
            </span>
          </div>
          <div className="mt-1 h-2 rounded-full bg-slate-100">
            <div className={`h-2 rounded-full ${row.color}`} style={{ width: `${(row.value / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function hourLabel(hour: number): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(hour)}:00–${pad((hour + 1) % 24)}:00`;
}

function HourlyChart() {
  const peak = DEMO_HOURLY_EVENTS_24H.indexOf(Math.max(...DEMO_HOURLY_EVENTS_24H));
  const [hovered, setHovered] = useState<number | null>(null);
  const shown = hovered ?? peak;
  const max = Math.max(...DEMO_HOURLY_EVENTS_24H, 1);
  return (
    <div>
      <p className="text-sm text-slate-600" aria-live="polite">
        <span className="font-medium text-ink-900">{hourLabel(shown)}</span> · {DEMO_HOURLY_EVENTS_24H[shown]} olay
        {hovered === null && <span className="text-slate-400"> (en yoğun saat)</span>}
      </p>
      <div className="relative mt-4 h-40" onMouseLeave={() => setHovered(null)}>
        <div aria-hidden className="absolute inset-x-0 top-0 border-t border-dashed border-slate-200" />
        <div aria-hidden className="absolute inset-x-0 top-1/2 border-t border-dashed border-slate-200" />
        <div aria-hidden className="relative flex h-full items-end gap-[2px]">
          {DEMO_HOURLY_EVENTS_24H.map((count, hour) => (
            <div
              key={hour}
              className="flex h-full flex-1 items-end"
              onMouseEnter={() => setHovered(hour)}
            >
              <div
                className={`w-full rounded-t-[4px] transition-colors ${
                  hour === shown ? "bg-brand-600" : "bg-brand-500/40"
                }`}
                style={{ height: `${Math.max(2, (count / max) * 100)}%` }}
              />
            </div>
          ))}
        </div>
      </div>
      <div aria-hidden className="mt-1.5 flex justify-between text-[11px] text-slate-400">
        <span>00:00</span>
        <span>06:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span>23:00</span>
      </div>
      <table className="sr-only">
        <caption>Saatlik olay sayısı (sentetik)</caption>
        <thead>
          <tr>
            <th scope="col">Saat</th>
            <th scope="col">Olay</th>
          </tr>
        </thead>
        <tbody>
          {DEMO_HOURLY_EVENTS_24H.map((count, hour) => (
            <tr key={hour}>
              <td>{hourLabel(hour)}</td>
              <td>{count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
