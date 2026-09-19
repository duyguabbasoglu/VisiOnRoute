import Link from "next/link";
import { BrandLogo } from "@/components/BrandLogo";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-ink-900 px-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-xl">
        <BrandLogo size="lg" className="mx-auto" />
        <h1 className="mt-4 text-2xl font-semibold text-ink-900">Sayfa bulunamadı</h1>
        <p className="mt-2 text-sm text-slate-600">
          Aradığınız sayfa taşınmış veya hiç var olmamış olabilir.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link
            href="/panel"
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Panele dön
          </Link>
          <Link
            href="/"
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Ana sayfa
          </Link>
        </div>
      </div>
    </main>
  );
}
