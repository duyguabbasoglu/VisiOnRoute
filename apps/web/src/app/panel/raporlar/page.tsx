"use client";

import { useState } from "react";
import { Alert, Button, Card, PageHeader } from "@/components/ui";
import { apiDownload, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can, type Permission } from "@/lib/permissions";

const REPORTS: { key: string; title: string; description: string; path: string; filename: string; permission: Permission }[] = [
  {
    key: "events",
    title: "Güvenlik olayları (CSV)",
    description: "Son 90 günün olayları; filtreler, veri kapsamı, metodoloji ve sınırlamalarla birlikte.",
    path: "/api/v1/reports/safety-events.csv",
    filename: "guvenlik-olaylari.csv",
    permission: "reports.read",
  },
  {
    key: "coaching",
    title: "Koçluk görevleri (CSV)",
    description: "Son 90 günde oluşturulan koçluk görevleri, durumları ve sonuçları.",
    path: "/api/v1/reports/coaching.csv",
    filename: "kocluk-gorevleri.csv",
    permission: "coaching.read",
  },
  {
    key: "executive",
    title: "Yönetici raporu (PDF)",
    description: "Şiddet dağılımı, mesafe, onay oranı, metodoloji ve sınırlamalar.",
    path: "/api/v1/reports/executive.pdf",
    filename: "yonetici-raporu.pdf",
    permission: "reports.read",
  },
];

export default function ReportsPage() {
  const { user } = useAuth();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function download(report: (typeof REPORTS)[number]) {
    setBusy(report.key);
    setError(null);
    try {
      await apiDownload(report.path, report.filename);
    } catch (err) {
      setError(errorMessage(err, "Rapor indirilemedi."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="max-w-3xl">
      <PageHeader
        title="Raporlar"
        description="Raporlar indirme anında üretilir ve her üretim denetim kaydına yazılır."
      />
      {error && (
        <Alert kind="error" className="mb-4">
          {error}
        </Alert>
      )}
      <div className="space-y-4">
        {REPORTS.filter((r) => can(user, r.permission)).map((report) => (
          <Card key={report.key} className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-ink-900">{report.title}</h2>
              <p className="mt-1 text-sm text-slate-600">{report.description}</p>
            </div>
            <Button variant="secondary" loading={busy === report.key} onClick={() => void download(report)}>
              İndir
            </Button>
          </Card>
        ))}
      </div>
      <p className="mt-6 text-xs text-slate-500">
        Raporlar kazaların önleneceğini garanti etmez; riskleri veriye dayalı görünür kılar. Düşük kaliteli
        veriden üretilen olaylar insan incelemesi gerektirir.
      </p>
    </div>
  );
}
