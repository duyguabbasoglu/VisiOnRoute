"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { CTA_STYLES } from "@/components/public-styles";
import { useAuth } from "@/lib/auth";

/** Shared chrome for the public landing page and the /demo showcase. */

export function LogoMark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={className}>
      <rect width="32" height="32" rx="8" fill="#1d4ed8" />
      <path
        d="M7 23c3.5 0 4.5-4 8-7s6.5-4 10-4"
        fill="none"
        stroke="#fff"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <circle cx="25" cy="12" r="3" fill="#fbbf24" />
      <circle cx="7" cy="23" r="1.8" fill="#bfdbfe" />
    </svg>
  );
}

export function Wordmark({ tone = "light" }: { tone?: "light" | "dark" }) {
  return (
    <span className="flex items-center gap-2.5">
      <LogoMark />
      <span className={`text-lg font-semibold tracking-tight ${tone === "light" ? "text-white" : "text-ink-900"}`}>
        VisiOnRoute
      </span>
    </span>
  );
}

const NAV_LINKS = [
  { href: "/#yetenekler", label: "Yetenekler" },
  { href: "/#nasil-calisir", label: "Nasıl çalışır" },
  { href: "/#mimari", label: "Mimari" },
  { href: "/demo", label: "Demo panel" },
];

/** Account actions that follow the session: signed-in users get "Panele git". */
export function AccountActions({ compact = false }: { compact?: boolean }) {
  const { user } = useAuth();
  if (user) {
    return (
      <Link href="/panel" className={CTA_STYLES.primary}>
        Panele git
      </Link>
    );
  }
  return (
    <>
      <Link href="/giris" className={CTA_STYLES.ghost}>
        Giriş yap
      </Link>
      <span className={compact ? "hidden sm:contents" : "contents"}>
        <Link href="/kayit" className={CTA_STYLES.primary}>
          Organizasyon oluştur
        </Link>
      </span>
    </>
  );
}

export function PublicHeader({ wide = false }: { wide?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-ink-900">
      <div className={`mx-auto flex h-16 ${wide ? "max-w-7xl" : "max-w-6xl"} items-center justify-between gap-3 px-4 sm:px-6`}>
        <Link href="/" aria-label="VisiOnRoute ana sayfa" className="rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50">
          <Wordmark />
        </Link>
        <nav aria-label="Genel menü" className="hidden items-center gap-1 lg:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="rounded-md px-3 py-2 text-sm text-slate-300 transition hover:bg-white/5 hover:text-white"
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-1 sm:gap-2">
          <AccountActions compact />
          <button
            type="button"
            className="rounded-md p-2 text-slate-300 hover:bg-white/10 lg:hidden"
            aria-label={open ? "Menüyü kapat" : "Menüyü aç"}
            aria-expanded={open}
            aria-controls="genel-menu-mobil"
            onClick={() => setOpen((v) => !v)}
          >
            <svg viewBox="0 0 20 20" className="h-5 w-5" aria-hidden>
              {open ? (
                <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              ) : (
                <path d="M3 6h14M3 10h14M3 14h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              )}
            </svg>
          </button>
        </div>
      </div>
      {open && (
        <nav id="genel-menu-mobil" aria-label="Genel menü (mobil)" className="border-t border-white/10 px-4 pb-4 lg:hidden">
          <ul className="grid gap-1 pt-2">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  onClick={() => setOpen(false)}
                  className="block rounded-md px-3 py-2 text-sm text-slate-200 hover:bg-white/5"
                >
                  {link.label}
                </Link>
              </li>
            ))}
            <li>
              <Link href="/kayit" className="block rounded-md px-3 py-2 text-sm font-semibold text-brand-100 hover:bg-white/5 sm:hidden">
                Yeni organizasyon oluştur
              </Link>
            </li>
          </ul>
        </nav>
      )}
    </header>
  );
}

export function PublicFooter() {
  return (
    <footer className="border-t border-white/10 bg-ink-900 text-slate-400">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <Wordmark />
          <p className="mt-4 max-w-sm text-sm leading-relaxed">
            Riskli sürüş davranışlarını ve yol güvenliği sinyallerini görünür kılar. Kazaları önlediğini iddia etmez;
            hukuki, tıbbi, iş güvenliği veya insan değerlendirmesinin yerini almaz.
          </p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Ürün</p>
          <ul className="mt-3 space-y-2 text-sm">
            <li><Link className="hover:text-white" href="/demo">Demo panel (sentetik)</Link></li>
            <li><Link className="hover:text-white" href="/#yetenekler">Yetenekler</Link></li>
            <li><Link className="hover:text-white" href="/#mimari">Mimari</Link></li>
          </ul>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Hesap</p>
          <ul className="mt-3 space-y-2 text-sm">
            <li><Link className="hover:text-white" href="/giris">Giriş yap</Link></li>
            <li><Link className="hover:text-white" href="/kayit">Yeni organizasyon oluştur</Link></li>
            <li>
              <a className="hover:text-white" href="https://github.com/duyguabbasoglu/VisiOnRoute" rel="noopener noreferrer" target="_blank">
                Kaynak kodu (GitHub)
              </a>
            </li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/5 px-4 py-4 text-center text-xs text-slate-500">
        Hobi / portföy dağıtımı · Genel demo verileri tamamen sentetiktir.
      </div>
    </footer>
  );
}

/** Honest marker shown on every public page that displays product data. */
export function SyntheticNotice({ children }: { children?: ReactNode }) {
  return (
    <div role="note" className="flex items-start gap-2.5 rounded-xl border border-amber-300/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
      <svg viewBox="0 0 20 20" className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" aria-hidden>
        <path d="M10 2.5l8 14H2l8-14z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M10 8v3.5M10 14h.01" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
      <p>
        {children ?? (
          <>
            <strong className="font-semibold text-amber-50">Hobi demo · yalnızca sentetik veri.</strong> Gösterilen araçlar,
            sürücüler, konumlar ve olaylar kurgusaldır; gerçek müşteri veya gerçek yol olayı değildir.
          </>
        )}
      </p>
    </div>
  );
}

type IconName = "live" | "alert" | "fleet" | "evidence" | "coach" | "chart" | "map" | "shield";

const ICON_PATHS: Record<IconName, ReactNode> = {
  live: (
    <>
      <circle cx="12" cy="12" r="2.5" />
      <path d="M7.8 7.8a6 6 0 000 8.4M16.2 7.8a6 6 0 010 8.4M4.9 4.9a10 10 0 000 14.2M19.1 4.9a10 10 0 010 14.2" />
    </>
  ),
  alert: (
    <>
      <path d="M12 3l9.5 16.5h-19L12 3z" />
      <path d="M12 10v4M12 17.2h.01" />
    </>
  ),
  fleet: (
    <>
      <path d="M3 7h11v9H3zM14 10h4l3 3v3h-7" />
      <circle cx="7" cy="17.5" r="1.8" />
      <circle cx="17" cy="17.5" r="1.8" />
    </>
  ),
  evidence: (
    <>
      <rect x="3" y="6" width="18" height="13" rx="2" />
      <circle cx="12" cy="12.5" r="3.2" />
      <path d="M8 6l1.5-2.5h5L16 6" />
    </>
  ),
  coach: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5M15.5 5.5l2 2 3.5-3.5" />
    </>
  ),
  chart: (
    <>
      <path d="M4 20V4M4 20h16" />
      <path d="M8 16v-4M12 16V8M16 16v-6" />
    </>
  ),
  map: (
    <>
      <path d="M9 4L3 6.5v13.5L9 17.5l6 2.5 6-2.5V4l-6 2.5L9 4z" />
      <path d="M9 4v13.5M15 6.5V20" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6l8-3z" />
      <path d="M8.5 12l2.5 2.5 4.5-4.5" />
    </>
  ),
};

export function Icon({ name, className = "h-5 w-5" }: { name: IconName; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {ICON_PATHS[name]}
    </svg>
  );
}

export type { IconName };
