"use client";

import { useQuery } from "@tanstack/react-query";
import { Alert, Badge, Card, ErrorState, LoadingState, PageHeader, formatDateTime } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { subscriptionSchema, usageSchema, type Usage } from "@/lib/schemas";

const NUMBER = new Intl.NumberFormat("tr-TR");

function formatValue(value: number, unit: string): string {
  if (unit === "bayt") {
    if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} GB`;
    if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} MB`;
    return `${NUMBER.format(Math.round(value / 1024))} KB`;
  }
  return `${NUMBER.format(value)} ${unit}`;
}

export default function SubscriptionPage() {
  const { user } = useAuth();
  const allowed = can(user, "subscription.read");
  const subscription = useQuery({
    queryKey: ["subscription"],
    queryFn: () => apiFetch("/api/v1/subscription", { schema: subscriptionSchema }),
    enabled: allowed,
  });
  const usage = useQuery({
    queryKey: ["subscription-usage"],
    queryFn: () => apiFetch("/api/v1/subscription/usage?days=30", { schema: usageSchema }),
    enabled: allowed,
  });

  if (!allowed) {
    return (
      <div>
        <PageHeader title="Abonelik" />
        <Alert kind="warning">Abonelik bilgilerini görüntüleme yetkiniz yok.</Alert>
      </div>
    );
  }
  if (subscription.isLoading) return <LoadingState />;
  if (subscription.isError || !subscription.data) {
    return <ErrorState message={errorMessage(subscription.error, "Abonelik bilgileri yüklenemedi.")} />;
  }
  const sub = subscription.data;

  return (
    <div className="max-w-4xl">
      <PageHeader title="Abonelik" description="Planınız, limitleriniz ve günlük kullanım ölçümleri." />

      {sub.growth_blocked && (
        <Alert kind="warning" className="mb-6">
          Aboneliğiniz etkin değil. Yeni araç veya kullanıcı eklenemez; veri alımı ve mevcut verilere erişim
          sürmektedir. Planınızı etkinleştirmek için platform yöneticisiyle iletişime geçin.
        </Alert>
      )}
      {sub.status === "trial" && sub.trial_days_left !== null && (
        <Alert kind="info" className="mb-6">
          Deneme sürenizin bitmesine {sub.trial_days_left} gün kaldı
          {sub.trial_ends_at ? ` (${formatDateTime(sub.trial_ends_at)})` : ""}.
        </Alert>
      )}

      <Card className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-semibold text-ink-900">{sub.plan_name_tr}</h2>
          <Badge tone={sub.growth_blocked ? "warning" : sub.status === "active" ? "success" : "info"}>{sub.status_label}</Badge>
        </div>
        <p className="mt-2 text-sm text-slate-600">
          Faturalama {sub.billing_mode === "manual_invoice" ? "manuel fatura ile" : "ödeme sağlayıcısı üzerinden"} yapılır.
          Veri saklama üst sınırı: {sub.retention_days} gün.
        </p>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <LimitBar label="Araç" used={sub.usage.vehicles ?? 0} limit={sub.vehicle_limit} />
          <LimitBar label="Kullanıcı" used={sub.usage.active_members ?? 0} limit={sub.user_limit} />
        </div>
      </Card>

      <Card>
        <h2 className="mb-1 text-sm font-semibold text-ink-900">Son 30 gün kullanım</h2>
        <p className="mb-4 text-xs text-slate-500">
          Günlük ölçümler saatlik bakım görevinde güncellenir (UTC günleri). Etkinlik ölçümleri gün içindeki kayıtları,
          araç/kullanıcı/depolama ölçümleri ölçüm anındaki değeri gösterir.
        </p>
        {usage.isLoading ? (
          <LoadingState />
        ) : usage.isError || !usage.data ? (
          <ErrorState message={errorMessage(usage.error, "Kullanım ölçümleri yüklenemedi.")} />
        ) : (
          <UsageTable usage={usage.data} />
        )}
      </Card>
    </div>
  );
}

function LimitBar({ label, used, limit }: { label: string; used: number; limit: number }) {
  const unlimited = limit < 0;
  const ratio = unlimited || limit === 0 ? 0 : Math.min(1, used / limit);
  return (
    <div>
      <div className="flex justify-between text-sm">
        <span className="text-slate-700">{label}</span>
        <span className="text-slate-500">
          {NUMBER.format(used)} / {unlimited ? "sınırsız" : NUMBER.format(limit)}
        </span>
      </div>
      {!unlimited && (
        <div
          className="mt-1 h-2 rounded-full bg-slate-100"
          role="progressbar"
          aria-label={`${label} kullanımı`}
          aria-valuemin={0}
          aria-valuemax={limit}
          aria-valuenow={used}
        >
          <div
            className={`h-2 rounded-full ${ratio >= 1 ? "bg-red-500" : ratio >= 0.8 ? "bg-amber-500" : "bg-brand-600"}`}
            style={{ width: `${Math.round(ratio * 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}

function UsageTable({ usage }: { usage: Usage }) {
  const withData = usage.metrics.filter((m) => m.points.length > 0);
  if (withData.length === 0) {
    return <p className="text-sm text-slate-500">Henüz ölçüm yok; ilk ölçüm bir saat içinde oluşturulur.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b border-slate-200 text-left text-xs text-slate-500">
          <tr>
            <th className="py-2 pr-3">Ölçüm</th>
            <th className="py-2 pr-3">Son değer</th>
            <th className="py-2 pr-3">30 gün toplam / en yüksek</th>
          </tr>
        </thead>
        <tbody>
          {withData.map((metric) => {
            const last = metric.points[metric.points.length - 1];
            const isGauge = ["vehicles", "active_members", "evidence_storage_bytes"].includes(metric.metric);
            const aggregate = isGauge
              ? Math.max(...metric.points.map((p) => p.value))
              : metric.points.reduce((sum, p) => sum + p.value, 0);
            return (
              <tr key={metric.metric} className="border-b border-slate-100">
                <td className="py-2 pr-3">{metric.label}</td>
                <td className="py-2 pr-3">{last ? formatValue(last.value, metric.unit) : "—"}</td>
                <td className="py-2 pr-3">
                  {formatValue(aggregate, metric.unit)} {isGauge ? "(en yüksek)" : "(toplam)"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
