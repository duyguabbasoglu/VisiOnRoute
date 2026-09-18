import type { Metadata } from "next";
import Link from "next/link";
import {
  Icon,
  PublicFooter,
  PublicHeader,
  SyntheticNotice,
  type IconName,
} from "@/components/PublicSite";
import { CTA_STYLES } from "@/components/public-styles";
import { SessionHint } from "@/components/SessionHint";

export const metadata: Metadata = {
  title: { absolute: "VisiOnRoute — Ulaşım güvenliği platformu" },
  description:
    "VisiOnRoute araç telemetrisini açıklanabilir kurallarla işler; riskli sürüş davranışlarını ve yol güvenliği sinyallerini görünür kılar. Hobi demo, yalnızca sentetik veri.",
};

const CAPABILITIES: { icon: IconName; title: string; body: string; tags: string[] }[] = [
  {
    icon: "live",
    title: "Gerçek zamanlı operasyon",
    body: "Aktif seferler ve araç konumları sunucu olaylarıyla (SSE) canlı akar; bağlantı koparsa yoklamaya düşer, eski konumlar açıkça işaretlenir.",
    tags: ["SSE", "Sefer oluşturma"],
  },
  {
    icon: "alert",
    title: "Riskli sürüş olayları",
    body: "Sert fren, sert hızlanma, sert viraj ve hız aşımı sürümlenmiş kurallarla tespit edilir. Şiddet ve güven ayrı hesaplanır; zayıf veri insan incelemesine gider.",
    tags: ["Deterministik kurallar", "İnceleme akışı"],
  },
  {
    icon: "fleet",
    title: "Filo ve sürücü izleme",
    body: "Filolar, araçlar, sürücüler, cihazlar ve zaman aralıklı sürücü–araç atamaları; plan limitleri sunucu tarafında uygulanır.",
    tags: ["Atamalar", "Cihaz ve kamera"],
  },
  {
    icon: "evidence",
    title: "Kanıt yönetimi",
    body: "Olaylara bağlı medya özel depolamada tutulur, yalnızca kısa ömürlü imzalı bağlantılarla açılır ve her erişim denetim kaydına yazılır.",
    tags: ["İmzalı URL", "Erişim kaydı"],
  },
  {
    icon: "coach",
    title: "Koçluk",
    body: "Onaylanan olaylardan koçluk görevi atanır; başlatma, tamamlama, sonuç ve gecikme takibiyle cezalandırıcı değil gelişim odaklı bir döngü kurulur.",
    tags: ["Görev takibi", "Sonuç kaydı"],
  },
  {
    icon: "chart",
    title: "Analiz ve raporlama",
    body: "Şiddet dağılımı, 100 km başına olay, onay oranı ve maruziyete göre normalize sürücü skorları; CSV dışa aktarım ve Türkçe yönetici PDF raporu.",
    tags: ["100 km başına", "PDF rapor"],
  },
  {
    icon: "map",
    title: "Yol riski ve harita",
    body: "Tekrarlayan sert olaylar yol riski kümelerine dönüşür. Araçlar, olaylar, risk alanları ve coğrafi sınırlar tek haritada, klavyeyle erişilebilir listeyle birlikte.",
    tags: ["PostGIS", "MapLibre + OSM"],
  },
  {
    icon: "shield",
    title: "Gizlilik ve güvenlik",
    body: "Her kiracı tablosunda satır düzeyi güvenlik, MFA, rol tabanlı izinler ve KVKK veri sahibi talepleri; saklama süreleri kategori bazında yönetilir.",
    tags: ["RLS", "KVKK"],
  },
];

const STEPS = [
  {
    title: "Telemetri alınır",
    body: "Sürümlenmiş REST sözleşmesi veya CSV; API anahtarı kapsamlarıyla. Yinelenenler ayıklanır, hatalı kayıtlar Türkçe gerekçeyle karantinaya alınır.",
  },
  {
    title: "Kurallar değerlendirir",
    body: "Deterministik kurallar ölçülen değeri eşikle karşılaştırır. Hiçbir büyük dil modeli sayısal telemetriyi sınıflandırmaz.",
  },
  {
    title: "Olay açıklanır",
    body: "Hangi kural, hangi veri, hangi eşik, ölçülen değer ve güven düzeyi. Düşük veri kalitesi skoru şişirmez, incelemeye işaretler.",
  },
  {
    title: "İnsan karar verir",
    body: "Güvenlik sorumlusu olayı onaylar, reddeder veya belirsiz işaretler; koçluk atar, raporlar. Son söz her zaman insandadır.",
  },
];

const PRINCIPLES = [
  "Sürücü skoru 100 km başına ağırlıklı olaydır; 50 km altında skor üretilmez.",
  "Demografik veya gizli değişken yok; her sayı kural sürümüne ve veri penceresine izlenebilir.",
  "Yapay zekâ yardımı varsayılan olarak kapalıdır ve disiplin kararı veremez, kanıt üretemez.",
  "Sentetik veriler data_origin=\"synthetic\" etiketi taşır ve üretim kanıtı olarak gösterilmez.",
];

const ARCHITECTURE = [
  { title: "Modüler monolit", body: "FastAPI · domain → application → infrastructure katmanları import-linter ile zorunlu." },
  { title: "Tek doğruluk kaynağı", body: "PostgreSQL 17 + PostGIS, her kiracı tablosunda satır düzeyi güvenlik (RLS)." },
  { title: "Güvenilir olay akışı", body: "Transactional outbox; worker'lar FOR UPDATE SKIP LOCKED ile tüketir." },
  { title: "Oturum güvenliği", body: "RS256 JWT, dönen yenileme belirteci ve yeniden kullanım tespiti, TOTP MFA, Argon2id." },
];

const STACK = [
  "Python 3.13",
  "FastAPI",
  "SQLAlchemy 2",
  "PostgreSQL 17",
  "PostGIS",
  "Redis",
  "Next.js 15",
  "React 19",
  "TypeScript",
  "TanStack Query",
  "Zod",
  "Tailwind v4",
  "MapLibre GL",
  "Playwright",
  "Terraform",
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-ink-900 text-slate-200">
      <a
        href="#icerik"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-ink-900"
      >
        İçeriğe geç
      </a>
      <PublicHeader />

      <main id="icerik">
        {/* Hero */}
        <section className="relative overflow-hidden">
          <div aria-hidden className="pointer-events-none absolute inset-0">
            <div className="absolute -top-40 left-1/2 h-[36rem] w-[60rem] -translate-x-1/2 rounded-full bg-brand-600/25 blur-3xl" />
            <div className="absolute inset-0 bg-[linear-gradient(rgba(148,163,184,0.06)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.06)_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_75%)]" />
          </div>
          <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-14 sm:px-6 md:pt-20 lg:grid-cols-[1.05fr_1fr]">
            <div>
              <SessionHint />
              <p className="inline-flex items-center gap-2 rounded-full border border-amber-300/30 bg-amber-400/10 px-3 py-1 text-xs font-medium text-amber-200">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-300" aria-hidden />
                Hobi demo · yalnızca sentetik veri
              </p>
              <h1 className="mt-5 text-4xl font-semibold tracking-tight text-white sm:text-5xl lg:text-[3.4rem] lg:leading-[1.05]">
                VisiOnRoute
                <span className="mt-3 block text-2xl font-medium leading-snug text-slate-300 sm:text-3xl">
                  Riskli sürüşü ve yol güvenliği sinyallerini, büyümeden görün.
                </span>
              </h1>
              <p className="mt-6 max-w-xl text-base leading-relaxed text-slate-400 sm:text-lg">
                Filolar için veri odaklı ulaşım güvenliği platformu. Araç telemetrisini açıklanabilir kurallarla işler; sert
                fren, hız aşımı ve riskli yol kesimlerini inceleme, koçluk ve raporlamaya hazır güvenlik olaylarına
                dönüştürür.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href="/demo" className={`${CTA_STYLES.primary} px-5 py-2.5`}>
                  Demoyu keşfet
                  <span aria-hidden>→</span>
                </Link>
                <Link href="/giris" className={`${CTA_STYLES.secondary} px-5 py-2.5`}>
                  Giriş yap
                </Link>
                <Link href="/kayit" className={`${CTA_STYLES.secondary} px-5 py-2.5`}>
                  Yeni organizasyon oluştur
                </Link>
              </div>
              <dl className="mt-10 grid max-w-lg grid-cols-3 gap-4 border-t border-white/10 pt-6">
                {[
                  ["5", "deterministik kural"],
                  ["2 ayrı", "şiddet ve güven"],
                  ["100 km", "başına normalize skor"],
                ].map(([value, label]) => (
                  <div key={label} className="flex flex-col-reverse">
                    <dt className="mt-0.5 text-xs text-slate-500">{label}</dt>
                    <dd className="text-xl font-semibold text-white">{value}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <HeroPreview />
          </div>
        </section>

        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <SyntheticNotice>
            <strong className="font-semibold text-amber-50">Bu bir hobi / portföy dağıtımıdır.</strong> Genel demo
            paneldeki tüm veriler sentetiktir; gerçek müşteri, sürücü veya yol olayı içermez. Hesap açarsanız lütfen
            yalnızca sentetik veri kullanın — ücretsiz sunucu ilk istekte birkaç saniye uyanabilir.
          </SyntheticNotice>
        </div>

        {/* Capabilities */}
        <section id="yetenekler" aria-labelledby="yetenekler-baslik" className="scroll-mt-20 py-20 sm:py-24">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <SectionIntro
              eyebrow="Yetenekler"
              id="yetenekler-baslik"
              title="Ham telemetriden incelenebilir güvenlik iş akışına"
              body="Her modül aynı ilkeyle çalışır: bulgu açıklanabilir olmalı ve bir insan ona itiraz edebilmeli."
            />
            <ul className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {CAPABILITIES.map((item) => (
                <li
                  key={item.title}
                  className="group flex flex-col rounded-2xl border border-white/10 bg-ink-800/80 p-5 transition hover:border-brand-500/50 hover:bg-ink-800"
                >
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/15 text-brand-100 ring-1 ring-brand-500/30">
                    <Icon name={item.icon} />
                  </span>
                  <h3 className="mt-4 text-base font-semibold text-white">{item.title}</h3>
                  <p className="mt-2 flex-1 text-sm leading-relaxed text-slate-400">{item.body}</p>
                  <div className="mt-4 flex flex-wrap gap-1.5">
                    {item.tags.map((tag) => (
                      <span key={tag} className="rounded-md bg-white/5 px-2 py-0.5 text-[11px] text-slate-300">
                        {tag}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* How it works */}
        <section
          id="nasil-calisir"
          aria-labelledby="nasil-baslik"
          className="scroll-mt-20 border-y border-white/5 bg-ink-800/40 py-20 sm:py-24"
        >
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <SectionIntro
              eyebrow="Nasıl çalışır"
              id="nasil-baslik"
              title="Kara kutu skor yok"
              body="Her güvenlik olayı hangi kuralın, hangi veriyle, hangi eşikte tetiklendiğini ve ne kadar güvenilir olduğunu söyler."
            />
            <ol className="mt-12 grid gap-4 md:grid-cols-4">
              {STEPS.map((step, index) => (
                <li key={step.title} className="relative rounded-2xl border border-white/10 bg-ink-900/60 p-5">
                  <span className="text-xs font-semibold text-brand-100/70">Adım {index + 1}</span>
                  <h3 className="mt-1 text-base font-semibold text-white">{step.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-400">{step.body}</p>
                </li>
              ))}
            </ol>
            <div className="mt-8 grid gap-6 rounded-2xl border border-white/10 bg-ink-900/60 p-6 lg:grid-cols-[1fr_1.3fr] lg:items-center">
              <div>
                <p className="text-sm font-semibold text-white">Örnek olay açıklaması</p>
                <p className="mt-1 text-xs text-slate-500">Sentetik örnek · gerçek bir sürücüye ait değildir</p>
                <div className="mt-4 rounded-xl bg-ink-800 p-4 font-mono text-[13px] leading-relaxed text-slate-300 ring-1 ring-white/10">
                  <p>
                    <span className="text-slate-500">kural</span> sert_fren · v1
                  </p>
                  <p>
                    <span className="text-slate-500">ölçülen</span> −6,1 m/s²{" "}
                    <span className="text-slate-500">eşik</span> 3,5 m/s²
                  </p>
                  <p>
                    <span className="text-slate-500">şiddet</span> <span className="text-orange-300">yüksek</span>{" "}
                    <span className="text-slate-500">güven</span> %94
                  </p>
                  <p>
                    <span className="text-slate-500">veri</span> GPS hdop 0,9 · 12 uydu
                  </p>
                </div>
              </div>
              <ul className="space-y-3">
                {PRINCIPLES.map((p) => (
                  <li key={p} className="flex gap-3 text-sm leading-relaxed text-slate-300">
                    <svg viewBox="0 0 20 20" className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" aria-hidden>
                      <path d="M5 10.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* Architecture */}
        <section id="mimari" aria-labelledby="mimari-baslik" className="scroll-mt-20 py-20 sm:py-24">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <SectionIntro
              eyebrow="Mimari"
              id="mimari-baslik"
              title="Sade ama ciddi bir altyapı"
              body="Tek Python paketi, bağımsız ölçeklenen süreçler: API, worker ve zamanlayıcı. Türkçe arayüz Next.js ile."
            />
            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {ARCHITECTURE.map((item) => (
                <div key={item.title} className="rounded-2xl border border-white/10 bg-ink-800/60 p-5">
                  <h3 className="text-sm font-semibold text-white">{item.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-400">{item.body}</p>
                </div>
              ))}
            </div>
            <ul aria-label="Teknolojiler" className="mt-8 flex flex-wrap gap-2">
              {STACK.map((tech) => (
                <li key={tech} className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-400">
                  {tech}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Final CTA */}
        <section className="px-4 pb-24 sm:px-6">
          <div className="relative mx-auto max-w-6xl overflow-hidden rounded-3xl border border-brand-500/30 bg-gradient-to-br from-brand-700 via-brand-900 to-ink-900 px-6 py-12 sm:px-12">
            <div aria-hidden className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-amber-400/10 blur-3xl" />
            <div className="relative grid gap-8 lg:grid-cols-[1.4fr_1fr] lg:items-center">
              <div>
                <h2 className="text-2xl font-semibold text-white sm:text-3xl">Önce sentetik bir filoyu gezin.</h2>
                <p className="mt-3 max-w-xl text-slate-300">
                  Demo panel, gerçek uygulamanın genel bakış ekranını kurgusal verilerle salt okunur olarak gösterir. Kendi
                  organizasyonunuzu oluşturduğunuzda veriler size özel ve kiracı izolasyonlu olur.
                </p>
              </div>
              <div className="flex flex-wrap gap-3 lg:justify-end">
                <Link href="/demo" className={`${CTA_STYLES.amber} px-5 py-2.5`}>
                  Demoyu keşfet
                </Link>
                <Link href="/kayit" className={`${CTA_STYLES.secondary} px-5 py-2.5`}>
                  Yeni organizasyon oluştur
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}

function SectionIntro({ eyebrow, id, title, body }: { eyebrow: string; id: string; title: string; body: string }) {
  return (
    <div className="max-w-2xl">
      <p className="text-sm font-semibold text-amber-300">{eyebrow}</p>
      <h2 id={id} className="mt-2 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
        {title}
      </h2>
      <p className="mt-4 text-base leading-relaxed text-slate-400">{body}</p>
    </div>
  );
}

/** Static product preview for the hero; illustrative, clearly labeled synthetic. */
function HeroPreview() {
  const bars = [
    { label: "Düşük", value: 64, color: "bg-emerald-500" },
    { label: "Orta", value: 41, color: "bg-amber-500" },
    { label: "Yüksek", value: 18, color: "bg-orange-500" },
    { label: "Kritik", value: 3, color: "bg-red-600" },
  ];
  return (
    <figure className="relative" aria-label="Ürün önizlemesi (sentetik örnek)">
      <div aria-hidden className="absolute -inset-4 rounded-[2rem] bg-brand-500/10 blur-2xl" />
      <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-ink-800 shadow-2xl shadow-black/40">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
          <div className="flex gap-1.5" aria-hidden>
            <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          </div>
          <span className="rounded bg-amber-400/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-200">
            Sentetik örnek
          </span>
        </div>
        <div className="grid gap-3 p-4">
          <div className="grid grid-cols-3 gap-3">
            {[
              ["Aktif araç", "13"],
              ["Olay · 24 sa", "126"],
              ["İnceleme", "23"],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-ink-900/70 p-3 ring-1 ring-white/5">
                <p className="text-[11px] text-slate-500">{label}</p>
                <p className="mt-1 text-lg font-semibold text-white">{value}</p>
              </div>
            ))}
          </div>
          <div className="relative h-40 overflow-hidden rounded-xl bg-[#0e1a30] ring-1 ring-white/5">
            <svg viewBox="0 0 400 160" className="absolute inset-0 h-full w-full" aria-hidden>
              <defs>
                <pattern id="hero-grid" width="20" height="20" patternUnits="userSpaceOnUse">
                  <path d="M20 0H0V20" fill="none" stroke="rgba(148,163,184,0.07)" />
                </pattern>
              </defs>
              <rect width="400" height="160" fill="url(#hero-grid)" />
              <path d="M-10 78 C 60 70, 90 24, 160 32 S 260 76, 320 34 S 390 10, 420 16" fill="none" stroke="#334155" strokeWidth="7" strokeLinecap="round" />
              <path d="M-10 78 C 60 70, 90 24, 160 32 S 260 76, 320 34 S 390 10, 420 16" fill="none" stroke="#3b82f6" strokeWidth="2" strokeDasharray="6 6" />
              <path d="M150 -10 C 150 20, 175 60, 168 170" fill="none" stroke="#334155" strokeWidth="5" />
              <circle cx="244" cy="55" r="24" fill="rgba(234,88,12,0.18)" stroke="rgba(234,88,12,0.5)" strokeDasharray="3 3" />
              <circle cx="244" cy="55" r="6" fill="#ea580c" stroke="#0e1a30" strokeWidth="2" />
              <circle cx="330" cy="30" r="5" fill="#d97706" stroke="#0e1a30" strokeWidth="2" />
              <circle cx="96" cy="50" r="5" fill="#16a34a" stroke="#0e1a30" strokeWidth="2" />
              <circle cx="186" cy="37" r="7" fill="#fff" stroke="#2563eb" strokeWidth="3" />
            </svg>
            <div className="absolute bottom-3 left-3 right-3 rounded-lg bg-ink-900/90 p-3 ring-1 ring-white/10 backdrop-blur sm:right-auto sm:w-64">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-white">Sert fren · 34 DMO 118</p>
                <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[11px] font-medium text-orange-200">Yüksek</span>
              </div>
              <p className="mt-1 text-xs text-slate-400">Ölçülen 6,1 m/s² · eşik 3,5 m/s² · güven %94</p>
            </div>
          </div>
          <div className="rounded-xl bg-ink-900/70 p-3 ring-1 ring-white/5">
            <p className="text-[11px] text-slate-500">Şiddet dağılımı · son 24 saat</p>
            <div className="mt-2 space-y-1.5">
              {bars.map((bar) => (
                <div key={bar.label} className="grid grid-cols-[3.5rem_1fr_2rem] items-center gap-2 text-[11px]">
                  <span className="text-slate-400">{bar.label}</span>
                  <span className="h-1.5 rounded-full bg-white/5">
                    <span className={`block h-1.5 rounded-full ${bar.color}`} style={{ width: `${(bar.value / 64) * 100}%` }} />
                  </span>
                  <span className="text-right tabular-nums text-slate-300">{bar.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      <figcaption className="mt-3 text-center text-xs text-slate-500">
        Önizleme · kurgusal filo, gerçek konum veya kişi içermez
      </figcaption>
    </figure>
  );
}
