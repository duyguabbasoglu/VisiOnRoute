"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can, type Permission } from "@/lib/permissions";
import { messageSchema } from "@/lib/schemas";

const NAV: { href: string; label: string; permission: Permission | null }[] = [
  { href: "/panel", label: "Genel Bakış", permission: null },
  { href: "/panel/canli", label: "Canlı Operasyon", permission: "trips.read" },
  { href: "/panel/olaylar", label: "Güvenlik Olayları", permission: "events.read" },
  { href: "/panel/kocluk", label: "Koçluk", permission: "coaching.read" },
  { href: "/panel/yol-riskleri", label: "Yol Riskleri", permission: "risks.read" },
  { href: "/panel/surucular", label: "Sürücüler", permission: "fleet.read" },
  { href: "/panel/araclar", label: "Araçlar", permission: "fleet.read" },
  { href: "/panel/seferler", label: "Seferler", permission: "trips.read" },
  { href: "/panel/analizler", label: "Analizler", permission: "analytics.read" },
  { href: "/panel/entegrasyonlar", label: "Entegrasyonlar", permission: "integrations.read" },
  { href: "/panel/ayarlar", label: "Organizasyon", permission: "org.read" },
  { href: "/panel/hesap", label: "Hesabım", permission: null },
];

const ACCOUNT_PATH = "/panel/hesap";

export function AppShell({ children }: { children: ReactNode }) {
  const { user, loading, sessionExpired, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [resendState, setResendState] = useState<string | null>(null);

  const mfaEnrollmentRequired = Boolean(user?.mfa_required && !user.mfa_enabled);

  useEffect(() => {
    if (!loading && !user) {
      router.replace(sessionExpired ? "/giris?oturum=sona-erdi" : "/giris");
    }
  }, [loading, user, sessionExpired, router]);

  useEffect(() => {
    if (mfaEnrollmentRequired && pathname !== ACCOUNT_PATH) router.replace(ACCOUNT_PATH);
  }, [mfaEnrollmentRequired, pathname, router]);

  useEffect(() => setMenuOpen(false), [pathname]);

  if (loading) {
    return (
      <div role="status" className="flex min-h-screen items-center justify-center text-slate-500">
        Yükleniyor…
      </div>
    );
  }
  if (!user) return null;

  const items = NAV.filter((item) => item.permission === null || can(user, item.permission)).filter(
    (item) => !mfaEnrollmentRequired || item.href === ACCOUNT_PATH,
  );

  async function resendVerification() {
    try {
      const res = await apiFetch("/api/v1/auth/email/resend-verification", {
        method: "POST",
        schema: messageSchema,
      });
      setResendState(res.message);
    } catch (err) {
      setResendState(errorMessage(err, "E-posta gönderilemedi."));
    }
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <a
        href="#icerik"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2"
      >
        İçeriğe geç
      </a>
      <aside
        className={`${menuOpen ? "flex" : "hidden"} fixed inset-y-0 left-0 z-40 w-64 flex-col bg-ink-900 text-slate-100 md:static md:flex`}
      >
        <div className="px-6 py-5">
          <span className="text-lg font-semibold text-white">VISiOnRoute</span>
          <p className="mt-0.5 text-xs text-slate-400">Ulaşım Güvenliği</p>
        </div>
        <nav aria-label="Ana menü" className="flex-1 space-y-1 overflow-y-auto px-3">
          {items.map((item) => {
            const active =
              pathname === item.href || (item.href !== "/panel" && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`block rounded-lg px-3 py-2 text-sm transition ${
                  active ? "bg-brand-600 text-white" : "text-slate-300 hover:bg-ink-700 hover:text-white"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-ink-700 px-4 py-4 text-xs text-slate-400">
          <p className="truncate text-slate-200">{user.full_name}</p>
          <p className="truncate">{user.role_label ?? (user.is_platform_admin ? "Platform yöneticisi" : "Kullanıcı")}</p>
          <button
            onClick={() => {
              void logout().then(() => router.replace("/giris?cikis=tamam"));
            }}
            className="mt-3 w-full rounded-md border border-ink-700 px-2 py-1.5 text-slate-200 transition hover:bg-ink-700"
          >
            Çıkış yap
          </button>
        </div>
      </aside>
      {menuOpen && (
        <button
          aria-label="Menüyü kapat"
          className="fixed inset-0 z-30 bg-black/30 md:hidden"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-slate-200 bg-white px-4 sm:px-6">
          <button
            className="rounded-md border border-slate-300 px-2 py-1 text-sm md:hidden"
            aria-expanded={menuOpen}
            aria-label="Menüyü aç"
            onClick={() => setMenuOpen(true)}
          >
            Menü
          </button>
          <span className="truncate text-sm text-slate-500">
            {user.organization_name ?? (user.is_platform_admin ? "Platform yönetimi" : "Organizasyon")}
          </span>
        </header>
        {!user.email_verified && (
          <div role="status" className="flex flex-wrap items-center gap-3 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900 sm:px-6">
            <span>
              E-posta adresiniz henüz doğrulanmadı. Davet gönderme ve API anahtarı oluşturma için
              doğrulama gerekir.
            </span>
            {resendState ? (
              <span className="font-medium">{resendState}</span>
            ) : (
              <button className="font-medium underline" onClick={() => void resendVerification()}>
                Doğrulama e-postasını yeniden gönder
              </button>
            )}
          </div>
        )}
        {mfaEnrollmentRequired && (
          <div role="alert" className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800 sm:px-6">
            Organizasyonunuz iki adımlı doğrulamayı zorunlu kılıyor. Devam etmek için Hesabım
            sayfasından etkinleştirin.
          </div>
        )}
        <main id="icerik" className="flex-1 overflow-auto p-4 sm:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
