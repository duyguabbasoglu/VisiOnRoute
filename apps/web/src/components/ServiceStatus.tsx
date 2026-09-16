"use client";

import { useEffect, useState } from "react";
import { onServiceStatus, type ServiceStatus } from "@/lib/api";

/** Shown while API requests are unusually slow (e.g. a free-tier server waking up). */
export function ServiceStatusBanner({ className = "" }: { className?: string }) {
  const [status, setStatus] = useState<ServiceStatus>("ok");
  useEffect(() => onServiceStatus(setStatus), []);
  if (status === "ok") return null;
  return (
    <div role="status" aria-live="polite" className={`bg-sky-50 px-4 py-2 text-sm text-sky-900 ${className}`}>
      Sunucu yanıt vermekte gecikiyor. Demo sunucusu uyku modundan uyanıyor olabilir; bu bir dakikayı
      bulabilir. İşleminiz otomatik olarak tamamlanacak.
    </div>
  );
}

/** Honest marker for public demo deployments (NEXT_PUBLIC_DEMO_MODE=true). */
export function DemoModeBanner({ className = "" }: { className?: string }) {
  if (process.env.NEXT_PUBLIC_DEMO_MODE !== "true") return null;
  return (
    <div className={`bg-amber-100 px-4 py-1.5 text-center text-xs text-amber-950 ${className}`}>
      Hobi demo ortamı — yalnızca sentetik veri kullanın. Gerçek kişi, araç veya kanıt verisi yüklemeyin.
    </div>
  );
}
