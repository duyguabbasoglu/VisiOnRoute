"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useAuth } from "@/lib/auth";

const NAV: { href: string; label: string }[] = [
  { href: "/panel", label: "Genel Bakış" },
  { href: "/panel/canli", label: "Canlı Operasyon" },
  { href: "/panel/olaylar", label: "Güvenlik Olayları" },
  { href: "/panel/yol-riskleri", label: "Yol Riskleri" },
  { href: "/panel/surucular", label: "Sürücüler" },
  { href: "/panel/araclar", label: "Araçlar" },
  { href: "/panel/seferler", label: "Seferler" },
  { href: "/panel/analizler", label: "Analizler" },
  { href: "/panel/entegrasyonlar", label: "Entegrasyonlar" },
  { href: "/panel/ayarlar", label: "Ayarlar" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/giris");
    }
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        Yükleniyor…
      </div>
    );
  }
  if (!user) {
    return null;
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="flex w-64 flex-col border-r border-slate-200 bg-ink-900 text-slate-100">
        <div className="px-6 py-5">
          <span className="text-lg font-semibold text-white">VISiOnRoute</span>
          <p className="mt-0.5 text-xs text-slate-400">Ulaşım Güvenliği</p>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.map((item) => {
            const active =
              pathname === item.href ||
              (item.href !== "/panel" && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`block rounded-lg px-3 py-2 text-sm transition ${
                  active
                    ? "bg-brand-600 text-white"
                    : "text-slate-300 hover:bg-ink-700 hover:text-white"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-ink-700 px-4 py-4 text-xs text-slate-400">
          <p className="truncate text-slate-200">{user.full_name}</p>
          <p className="truncate">{user.role_label ?? "Kullanıcı"}</p>
          <button
            onClick={() => {
              void logout().then(() => router.replace("/giris"));
            }}
            className="mt-3 w-full rounded-md border border-ink-700 px-2 py-1.5 text-slate-200 transition hover:bg-ink-700"
          >
            Çıkış yap
          </button>
        </div>
      </aside>
      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6">
          <span className="text-sm text-slate-500">
            {user.organization_name ?? "Organizasyon"}
          </span>
        </header>
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}
