"use client";

import { Button, Card } from "@/components/ui";

/** Route-level error boundary: never shows raw exception text to customers. */
export default function PanelError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <Card className="mx-auto mt-10 max-w-lg text-center">
      <h1 className="text-lg font-semibold text-ink-900">Bu bölüm yüklenemedi</h1>
      <p className="mt-2 text-sm text-slate-600">
        Beklenmeyen bir sorun oluştu. Sayfayı yeniden deneyebilir veya başka bir bölüme geçebilirsiniz.
      </p>
      <Button className="mt-5" onClick={reset}>
        Tekrar dene
      </Button>
    </Card>
  );
}
