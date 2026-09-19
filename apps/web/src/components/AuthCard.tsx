import Link from "next/link";
import { BrandLogo } from "@/components/BrandLogo";
import type { ReactNode } from "react";
import { DemoModeBanner, ServiceStatusBanner } from "@/components/ServiceStatus";

/** Shared frame for public account pages (login, registration, recovery). */
export function AuthCard({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-ink-900 p-4 sm:p-6">
      <div className="fixed inset-x-0 top-0 z-10">
        <DemoModeBanner />
        <ServiceStatusBanner />
      </div>
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl sm:p-8">
        <div className="mb-6">
          <Link href="/" aria-label="VisiOnRoute ana sayfa" className="inline-flex rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40">
            <BrandLogo size="lg" priority />
          </Link>
          <h1 className="mt-2 text-2xl font-semibold text-ink-900">{title}</h1>
          {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
        </div>
        {children}
        {footer && <div className="mt-6 border-t border-slate-100 pt-4 text-sm">{footer}</div>}
      </div>
      <p className="mt-6 max-w-md text-center text-xs text-slate-400">
        VisiOnRoute riskli sürüş davranışlarını ve yol güvenliği sinyallerini görünür kılar; kazaları
        önlediğini iddia etmez ve insan değerlendirmesinin yerini almaz.
      </p>
    </main>
  );
}
