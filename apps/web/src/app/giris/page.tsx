import type { Metadata } from "next";

export const metadata: Metadata = { title: "Giriş" };

// Gerçek kimlik doğrulama formu M8'de API'ye bağlanır (bkz. docs/PROGRESS.md).
// Bu sayfa sahte bir giriş akışı sunmaz; backend hazır olana kadar bilgi verir.
export default function GirisPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-ink-900 p-6">
      <div className="w-full max-w-md rounded-xl bg-white p-8 shadow-lg">
        <h1 className="text-2xl font-semibold text-ink-900">VISiOnRoute</h1>
        <p className="mt-2 text-sm text-slate-600">
          Ulaşım güvenliği platformu kurulum aşamasındadır. Giriş akışı, kimlik
          servisi devreye alındığında burada etkinleşecektir.
        </p>
      </div>
    </main>
  );
}
