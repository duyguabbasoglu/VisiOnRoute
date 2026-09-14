import Link from "next/link";
import type { ReactNode } from "react";

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
    <main className="flex min-h-screen items-center justify-center bg-ink-900 p-4 sm:p-6">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl sm:p-8">
        <div className="mb-6">
          <Link href="/giris" className="text-sm font-semibold tracking-wide text-brand-700">
            VISiOnRoute
          </Link>
          <h1 className="mt-2 text-2xl font-semibold text-ink-900">{title}</h1>
          {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
        </div>
        {children}
        {footer && <div className="mt-6 border-t border-slate-100 pt-4 text-sm">{footer}</div>}
      </div>
    </main>
  );
}
