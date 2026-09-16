"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { z } from "zod";
import { DemoModeBanner, ServiceStatusBanner } from "@/components/ServiceStatus";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can, type Permission } from "@/lib/permissions";
import { messageSchema, notificationSchema } from "@/lib/schemas";

interface NavItem {
  href: string;
  label: string;
  permission: Permission | null;
  platformOnly?: boolean;
}

const NAV_GROUPS: { label: string | null; items: NavItem[] }[] = [
  { label: null, items: [{ href: "/panel", label: "Genel Bakış", permission: null }] },
  {
    label: "Operasyon",
    items: [
      { href: "/panel/canli", label: "Canlı Operasyon", permission: "trips.read" },
      { href: "/panel/harita", label: "Harita", permission: "events.read" },
      { href: "/panel/seferler", label: "Seferler", permission: "trips.read" },
    ],
  },
  {
    label: "Güvenlik",
    items: [
      { href: "/panel/olaylar", label: "Güvenlik Olayları", permission: "events.read" },
      { href: "/panel/kocluk", label: "Koçluk", permission: "coaching.read" },
      { href: "/panel/yol-riskleri", label: "Yol Riskleri", permission: "risks.read" },
      { href: "/panel/analizler", label: "Analizler", permission: "analytics.read" },
      { href: "/panel/raporlar", label: "Raporlar", permission: "reports.read" },
    ],
  },
  {
    label: "Filo",
    items: [
      { href: "/panel/filolar", label: "Filolar", permission: "fleet.read" },
      { href: "/panel/araclar", label: "Araçlar", permission: "fleet.read" },
      { href: "/panel/surucular", label: "Sürücüler", permission: "fleet.read" },
      { href: "/panel/cihazlar", label: "Cihazlar ve Kameralar", permission: "fleet.read" },
    ],
  },
  {
    label: "Yönetim",
    items: [
      { href: "/panel/bildirimler", label: "Bildirimler", permission: "events.read" },
      { href: "/panel/entegrasyonlar", label: "Entegrasyonlar", permission: "integrations.read" },
      { href: "/panel/ayarlar", label: "Organizasyon", permission: "org.read" },
      { href: "/panel/gizlilik", label: "Gizlilik (KVKK)", permission: "org.retention.manage" },
      { href: "/panel/abonelik", label: "Abonelik", permission: "subscription.read" },
      { href: "/panel/platform", label: "Platform Yönetimi", permission: null, platformOnly: true },
    ],
  },
  { label: "Hesap", items: [{ href: "/panel/hesap", label: "Hesabım", permission: null }] },
];

const ACCOUNT_PATH = "/panel/hesap";

function isActive(pathname: string, href: string): boolean {
  return pathname === href || (href !== "/panel" && pathname.startsWith(`${href}/`));
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, loading, sessionExpired, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [resendState, setResendState] = useState<string | null>(null);

  const mfaEnrollmentRequired = Boolean(user?.mfa_required && !user.mfa_enabled);
  const canNotifications = can(user, "events.read") && !mfaEnrollmentRequired;

  const unread = useQuery({
    queryKey: ["notifications", true],
    queryFn: () =>
      apiFetch("/api/v1/notifications?unread_only=true&limit=50", { schema: z.array(notificationSchema) }),
    enabled: canNotifications,
    refetchInterval: 60_000,
  });

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
      <div className="flex min-h-screen flex-col">
        <ServiceStatusBanner />
        <div role="status" className="flex flex-1 items-center justify-center text-slate-500">
          Yükleniyor…
        </div>
      </div>
    );
  }
  if (!user) return null;

  const allowed = (item: NavItem) =>
    (item.platformOnly ? user.is_platform_admin : item.permission === null || can(user, item.permission)) &&
    (!mfaEnrollmentRequired || item.href === ACCOUNT_PATH);
  const groups = NAV_GROUPS.map((group) => ({ ...group, items: group.items.filter(allowed) })).filter(
    (group) => group.items.length > 0,
  );
  const current = NAV_GROUPS.flatMap((group) => group.items.map((item) => ({ group: group.label, item }))).find(
    ({ item }) => isActive(pathname, item.href),
  );
  const unreadCount = unread.data?.length ?? 0;

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
        className={`${menuOpen ? "flex" : "hidden"} fixed inset-y-0 left-0 z-40 w-64 flex-col bg-ink-900 text-slate-100 md:sticky md:top-0 md:flex md:h-screen`}
      >
        <div className="flex items-start justify-between px-5 py-5">
          <Link href="/panel" className="block">
            <span className="text-lg font-semibold tracking-tight text-white">VISiOnRoute</span>
            <span className="mt-0.5 block text-xs text-slate-400">Ulaşım Güvenliği</span>
          </Link>
          <button
            className="rounded-md px-2 py-1 text-sm text-slate-300 hover:bg-ink-700 md:hidden"
            aria-label="Menüyü kapat"
            onClick={() => setMenuOpen(false)}
          >
            ✕
          </button>
        </div>
        <nav aria-label="Ana menü" className="flex-1 overflow-y-auto px-3 pb-4">
          {groups.map((group) => (
            <div key={group.label ?? "genel"} className="mt-3 first:mt-0">
              {group.label && (
                <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  {group.label}
                </p>
              )}
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const active = isActive(pathname, item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={`flex items-center justify-between rounded-lg px-3 py-1.5 text-sm transition ${
                          active ? "bg-brand-600 text-white" : "text-slate-300 hover:bg-ink-700 hover:text-white"
                        }`}
                      >
                        {item.label}
                        {item.href === "/panel/bildirimler" && unreadCount > 0 && (
                          <span className="rounded-full bg-amber-400 px-1.5 text-[11px] font-semibold text-ink-900">
                            {unreadCount >= 50 ? "50+" : unreadCount}
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
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
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <DemoModeBanner />
        <header className="flex h-14 items-center gap-3 border-b border-slate-200 bg-white px-4 sm:px-6">
          <button
            className="rounded-md border border-slate-300 px-2 py-1 text-sm md:hidden"
            aria-expanded={menuOpen}
            aria-label="Menüyü aç"
            onClick={() => setMenuOpen(true)}
          >
            Menü
          </button>
          <nav aria-label="Sayfa yolu" className="min-w-0 flex-1 truncate text-sm text-slate-500">
            {current?.group && <span>{current.group}</span>}
            {current?.group && <span className="mx-1.5 text-slate-300">/</span>}
            <span className="font-medium text-slate-700">{current?.item.label ?? "Panel"}</span>
          </nav>
          {canNotifications && (
            <Link
              href="/panel/bildirimler"
              className="hidden rounded-md px-2 py-1 text-sm text-slate-600 hover:bg-slate-100 sm:inline-flex"
            >
              Bildirimler
              {unreadCount > 0 && (
                <span className="ml-1.5 rounded-full bg-amber-100 px-1.5 text-xs font-semibold text-amber-900">
                  {unreadCount >= 50 ? "50+" : unreadCount}
                </span>
              )}
            </Link>
          )}
          <span className="hidden max-w-[16rem] truncate text-sm text-slate-500 lg:inline">
            {user.organization_name ?? (user.is_platform_admin ? "Platform yönetimi" : "Organizasyon")}
          </span>
        </header>
        <ServiceStatusBanner />
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
        <main id="icerik" className="flex-1 p-4 sm:p-6 lg:p-8">
          <div className="mx-auto w-full max-w-7xl">{children}</div>
        </main>
      </div>
    </div>
  );
}
