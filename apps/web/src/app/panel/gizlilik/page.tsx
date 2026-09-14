"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  formatDateTime,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import {
  PRIVACY_ERROR_LABELS,
  PRIVACY_RESULT_LABELS,
  driverSchema,
  memberSchema,
  privacyRequestSchema,
  retentionSchema,
  signedLinkSchema,
  type PrivacyRequest,
  type Retention,
} from "@/lib/schemas";

const STATUS_TONES: Record<PrivacyRequest["status"], "neutral" | "success" | "warning" | "danger" | "info"> = {
  pending: "info",
  processing: "warning",
  completed: "success",
  failed: "danger",
  canceled: "neutral",
};

export default function PrivacyPage() {
  const { user } = useAuth();
  const allowed = can(user, "org.retention.manage");

  if (!allowed) {
    return (
      <div>
        <PageHeader title="Gizlilik (KVKK)" />
        <Alert kind="warning">Bu sayfa yalnızca organizasyon sahipleri ve yöneticileri içindir.</Alert>
      </div>
    );
  }

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Gizlilik (KVKK)"
        description="Kişisel veri dışa aktarma ve silme talepleri ile veri saklama süreleri."
      />
      <Alert kind="info" className="mb-6">
        Talepler arka planda işlenir. Silme işlemi geri alınamaz: kimlik bilgileri anonimleştirilir, ham konum
        verisi ve kanıt medyası silinir; filo güvenlik istatistikleri anonim olarak korunur. İşlem kayıtları yasal
        yükümlülükler için saklanır. Saklama sürelerinin hukuki uygunluğu veri sorumlusunun değerlendirmesindedir.
      </Alert>
      <NewRequest />
      <RequestList />
      <RetentionSettings />
    </div>
  );
}

function NewRequest() {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<"export" | "erasure">("export");
  const [subjectType, setSubjectType] = useState<"driver" | "user">("driver");
  const [subjectId, setSubjectId] = useState("");
  const [reason, setReason] = useState("");
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const drivers = useQuery({
    queryKey: ["drivers", "privacy"],
    queryFn: () =>
      apiFetch("/api/v1/drivers?page_size=100", {
        schema: z.object({ items: z.array(driverSchema) }),
      }),
  });
  const members = useQuery({
    queryKey: ["members"],
    queryFn: () => apiFetch("/api/v1/organizations/current/members", { schema: z.array(memberSchema) }),
  });

  const options =
    subjectType === "driver"
      ? (drivers.data?.items ?? [])
          .filter((d) => d.status !== "erased")
          .map((d) => ({ id: d.id, label: `${d.full_name} (${d.external_id})` }))
      : (members.data ?? []).map((m) => ({ id: m.user_id, label: `${m.full_name} — ${m.email}` }));

  useEffect(() => setSubjectId(""), [subjectType]);

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/privacy/requests", {
        method: "POST",
        body: { kind, subject_type: subjectType, subject_id: subjectId, reason: reason.trim() || null },
        schema: privacyRequestSchema,
      }),
    onSuccess: () => {
      setReason("");
      setSubjectId("");
      setFeedback({ kind: "success", text: "Talep oluşturuldu; birkaç dakika içinde işlenecek." });
      void queryClient.invalidateQueries({ queryKey: ["privacy-requests"] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Talep oluşturulamadı.") }),
  });

  return (
    <Card className="mb-6">
      <h2 className="mb-3 text-sm font-semibold text-ink-900">Yeni talep</h2>
      <form
        className="grid grid-cols-1 gap-4 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (kind === "erasure") {
            const confirmed = window.confirm(
              "Silme talebi onaylandığında kişinin kimlik bilgileri anonimleştirilir ve konum/medya verileri kalıcı olarak silinir. Devam edilsin mi?",
            );
            if (!confirmed) return;
          }
          create.mutate();
        }}
      >
        <label className="text-sm text-slate-700">
          <span className="mb-1 block font-medium">Talep türü</span>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value === "erasure" ? "erasure" : "export")}
            className="w-full rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="export">Veri dışa aktarma (erişim hakkı)</option>
            <option value="erasure">Silme / anonimleştirme</option>
          </select>
        </label>
        <label className="text-sm text-slate-700">
          <span className="mb-1 block font-medium">Kişi türü</span>
          <select
            value={subjectType}
            onChange={(e) => setSubjectType(e.target.value === "user" ? "user" : "driver")}
            className="w-full rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="driver">Sürücü</option>
            <option value="user">Panel kullanıcısı</option>
          </select>
        </label>
        <label className="text-sm text-slate-700 sm:col-span-2">
          <span className="mb-1 block font-medium">Kişi</span>
          <select
            required
            value={subjectId}
            onChange={(e) => setSubjectId(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">Seçin…</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-700 sm:col-span-2">
          <span className="mb-1 block font-medium">
            Gerekçe {kind === "erasure" ? "(zorunlu, en az 10 karakter)" : "(isteğe bağlı)"}
          </span>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
            rows={2}
            required={kind === "erasure"}
            minLength={kind === "erasure" ? 10 : undefined}
            className="w-full rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        <div className="flex items-center gap-3 sm:col-span-2">
          <Button type="submit" variant={kind === "erasure" ? "danger" : "primary"} loading={create.isPending} disabled={!subjectId}>
            {kind === "erasure" ? "Silme talebi oluştur" : "Dışa aktarma talebi oluştur"}
          </Button>
          {feedback && <Alert kind={feedback.kind}>{feedback.text}</Alert>}
        </div>
      </form>
    </Card>
  );
}

function RequestList() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const requests = useQuery({
    queryKey: ["privacy-requests"],
    queryFn: () => apiFetch("/api/v1/privacy/requests", { schema: z.array(privacyRequestSchema) }),
    // Poll while work is outstanding so status changes appear without reload.
    refetchInterval: (query) =>
      query.state.data?.some((r) => r.status === "pending" || r.status === "processing") ? 5000 : false,
  });

  const cancel = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/privacy/requests/${id}/cancel`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["privacy-requests"] }),
    onError: (err) => setError(errorMessage(err, "Talep iptal edilemedi.")),
  });
  const download = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/privacy/requests/${id}/download`, { schema: signedLinkSchema }),
    onSuccess: ({ url }) => window.open(url, "_blank", "noopener,noreferrer"),
    onError: (err) => setError(errorMessage(err, "İndirme bağlantısı alınamadı.")),
  });

  return (
    <Card className="mb-6">
      <h2 className="mb-3 text-sm font-semibold text-ink-900">Talepler</h2>
      {error && (
        <Alert kind="error" className="mb-3">
          {error}
        </Alert>
      )}
      {requests.isLoading ? (
        <LoadingState />
      ) : requests.isError ? (
        <ErrorState message={errorMessage(requests.error, "Talepler yüklenemedi.")} />
      ) : !requests.data?.length ? (
        <EmptyState message="Henüz KVKK talebi yok." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-xs text-slate-500">
              <tr>
                <th className="py-2 pr-3">Tarih</th>
                <th className="py-2 pr-3">Tür</th>
                <th className="py-2 pr-3">Kişi</th>
                <th className="py-2 pr-3">Durum</th>
                <th className="py-2 pr-3">Sonuç</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {requests.data.map((r) => (
                <tr key={r.id} className="border-b border-slate-100 align-top">
                  <td className="py-2 pr-3 whitespace-nowrap">{formatDateTime(r.created_at)}</td>
                  <td className="py-2 pr-3">{r.kind_label}</td>
                  <td className="py-2 pr-3">
                    <span className="block">{r.subject_name ?? "—"}</span>
                    <span className="text-xs text-slate-500">{r.subject_label}</span>
                  </td>
                  <td className="py-2 pr-3">
                    <Badge tone={STATUS_TONES[r.status]}>{r.status_label}</Badge>
                    {r.error_code && (
                      <span className="mt-1 block text-xs text-red-700">
                        {PRIVACY_ERROR_LABELS[r.error_code] ?? "İşlem tamamlanamadı; sistem yeniden deneyecek."}
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-xs text-slate-600">
                    <ResultSummary result={r.result} />
                    {r.artifact_expires_at && r.download_available && (
                      <span className="block">Son indirme: {formatDateTime(r.artifact_expires_at)}</span>
                    )}
                  </td>
                  <td className="py-2 text-right whitespace-nowrap">
                    {r.download_available && (
                      <Button variant="secondary" className="px-2 py-1 text-xs" loading={download.isPending} onClick={() => download.mutate(r.id)}>
                        İndir
                      </Button>
                    )}
                    {r.status === "pending" && (
                      <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => cancel.mutate(r.id)}>
                        İptal et
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function ResultSummary({ result }: { result: PrivacyRequest["result"] }) {
  const entries = Object.entries(result).filter(([key]) => key in PRIVACY_RESULT_LABELS);
  const flags: string[] = [];
  if (result.account_erased === 1) flags.push("Hesap anonimleştirildi");
  if (result.account_retained_for_other_organizations === 1) flags.push("Hesap başka organizasyonlarda kullanıldığı için korundu");
  if (!entries.length && !flags.length) return <span>—</span>;
  return (
    <ul>
      {entries.map(([key, value]) => (
        <li key={key}>
          {PRIVACY_RESULT_LABELS[key]}: {String(value)}
        </li>
      ))}
      {flags.map((flag) => (
        <li key={flag}>{flag}</li>
      ))}
    </ul>
  );
}

function RetentionSettings() {
  const queryClient = useQueryClient();
  const retention = useQuery({
    queryKey: ["retention"],
    queryFn: () => apiFetch("/api/v1/privacy/retention", { schema: retentionSchema }),
  });

  if (retention.isLoading) return <LoadingState />;
  if (retention.isError || !retention.data) {
    return <ErrorState message={errorMessage(retention.error, "Saklama ayarları yüklenemedi.")} />;
  }
  return (
    <RetentionForm
      key={JSON.stringify(retention.data)}
      data={retention.data}
      onSaved={() => void queryClient.invalidateQueries({ queryKey: ["retention"] })}
    />
  );
}

function RetentionForm({ data, onSaved }: { data: Retention; onSaved: () => void }) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(data.categories.map((c) => [c.key, c.override_days?.toString() ?? ""])),
  );
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const save = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/privacy/retention", {
        method: "PUT",
        body: Object.fromEntries(
          Object.entries(values).map(([key, value]) => [key, value.trim() === "" ? null : Number(value)]),
        ),
        schema: retentionSchema,
      }),
    onSuccess: () => {
      setFeedback({ kind: "success", text: "Saklama süreleri güncellendi." });
      onSaved();
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Saklama süreleri kaydedilemedi.") }),
  });

  return (
    <Card>
      <h2 className="mb-1 text-sm font-semibold text-ink-900">Veri saklama süreleri</h2>
      <p className="mb-4 text-xs text-slate-500">
        Planınız en fazla {data.plan_days} gün saklamaya izin verir. Süreyi {data.min_days} gün ile plan sınırı
        arasında kısaltabilirsiniz; boş bırakılan alan plan süresini kullanır. Süresi dolan veriler saatlik
        bakım görevinde kalıcı olarak silinir.
      </p>
      <form
        className="grid grid-cols-1 gap-4 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        {data.categories.map((category) => (
          <label key={category.key} className="text-sm text-slate-700">
            <span className="mb-1 block font-medium">{category.label}</span>
            <input
              type="number"
              min={data.min_days}
              max={data.plan_days}
              value={values[category.key] ?? ""}
              placeholder={`Plan varsayılanı: ${data.plan_days}`}
              onChange={(e) => setValues((current) => ({ ...current, [category.key]: e.target.value }))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2"
            />
            <span className="mt-1 block text-xs text-slate-500">Geçerli süre: {category.effective_days} gün</span>
          </label>
        ))}
        <div className="flex items-center gap-3 sm:col-span-2">
          <Button type="submit" loading={save.isPending}>
            Kaydet
          </Button>
          {feedback && <Alert kind={feedback.kind}>{feedback.text}</Alert>}
        </div>
      </form>
    </Card>
  );
}
