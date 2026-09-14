"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmButton,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  SEVERITY_LABELS,
  TextField,
  formatDateTime,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import {
  messageSchema,
  notificationRuleSchema,
  notificationSchema,
  webhookDeliverySchema,
  webhookSchema,
  type Webhook,
} from "@/lib/schemas";

type Feedback = { kind: "success" | "error"; text: string } | null;

const CHANNEL_LABELS: Record<string, string> = { in_app: "Uygulama içi", webhook: "Webhook" };
const DELIVERY_STATUS: Record<string, string> = {
  pending: "Bekliyor",
  delivered: "Teslim edildi",
  failed: "Başarısız (yeniden denenecek)",
  dead_letter: "Teslim edilemedi",
};

export default function NotificationsPage() {
  const { user } = useAuth();
  const canManage = can(user, "notifications.manage");
  return (
    <div className="max-w-5xl">
      <PageHeader title="Bildirimler" description="Güvenlik olayı bildirimleri, kurallar ve webhook uç noktaları." />
      <InAppNotifications />
      {canManage && <Rules />}
      {canManage && <Webhooks emailVerified={Boolean(user?.email_verified)} />}
    </div>
  );
}

function InAppNotifications() {
  const queryClient = useQueryClient();
  const [unreadOnly, setUnreadOnly] = useState(true);
  const list = useQuery({
    queryKey: ["notifications", unreadOnly],
    queryFn: () =>
      apiFetch(`/api/v1/notifications?unread_only=${unreadOnly}&limit=50`, { schema: z.array(notificationSchema) }),
  });
  const markRead = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  return (
    <Card className="mb-6">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink-900">Uygulama içi bildirimler</h2>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
          Yalnızca okunmamış
        </label>
      </div>
      {list.isLoading ? (
        <LoadingState />
      ) : list.isError ? (
        <ErrorState message={errorMessage(list.error, "Bildirimler yüklenemedi.")} />
      ) : !list.data?.length ? (
        <EmptyState message={unreadOnly ? "Okunmamış bildirim yok." : "Henüz bildirim yok."} />
      ) : (
        <ul className="divide-y divide-slate-100">
          {list.data.map((n) => (
            <li key={n.id} className="flex flex-wrap items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink-900">{n.title_tr}</p>
                <p className="text-sm text-slate-600">{n.body_tr}</p>
                <p className="mt-1 text-xs text-slate-400">{formatDateTime(n.created_at)}</p>
              </div>
              <div className="flex items-center gap-2">
                {n.safety_event_id && (
                  <Link href={`/panel/olaylar/${n.safety_event_id}`} className="text-sm text-brand-700 hover:underline">
                    Olayı aç
                  </Link>
                )}
                {!n.read_at && (
                  <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => markRead.mutate(n.id)}>
                    Okundu işaretle
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Rules() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [minSeverity, setMinSeverity] = useState("high");
  const [channels, setChannels] = useState<string[]>(["in_app"]);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const rules = useQuery({
    queryKey: ["notification-rules"],
    queryFn: () => apiFetch("/api/v1/notification-rules", { schema: z.array(notificationRuleSchema) }),
  });
  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/notification-rules", {
        method: "POST",
        body: { name, min_severity: minSeverity, channels },
        schema: notificationRuleSchema,
      }),
    onSuccess: () => {
      setName("");
      setFeedback({ kind: "success", text: "Kural oluşturuldu." });
      void queryClient.invalidateQueries({ queryKey: ["notification-rules"] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Kural oluşturulamadı.") }),
  });

  return (
    <Card className="mb-6">
      <h2 className="mb-3 text-sm font-semibold text-ink-900">Bildirim kuralları</h2>
      <form
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <TextField label="Kural adı" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
        <div>
          <label htmlFor="rule-severity" className="block text-sm font-medium text-slate-700">
            En düşük şiddet
          </label>
          <select
            id="rule-severity"
            value={minSeverity}
            onChange={(e) => setMinSeverity(e.target.value)}
            className="mt-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            {["low", "medium", "high", "critical"].map((s) => (
              <option key={s} value={s}>
                {SEVERITY_LABELS[s] ?? s}
              </option>
            ))}
          </select>
        </div>
        <fieldset className="flex items-center gap-3 text-sm text-slate-700">
          <legend className="sr-only">Kanallar</legend>
          {Object.entries(CHANNEL_LABELS).map(([value, label]) => (
            <label key={value} className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={channels.includes(value)}
                onChange={(e) =>
                  setChannels((current) =>
                    e.target.checked ? [...current, value] : current.filter((c) => c !== value),
                  )
                }
              />
              {label}
            </label>
          ))}
        </fieldset>
        <Button type="submit" loading={create.isPending} disabled={channels.length === 0}>
          Kural ekle
        </Button>
      </form>
      {feedback && (
        <Alert kind={feedback.kind} className="mb-3">
          {feedback.text}
        </Alert>
      )}
      {rules.isLoading ? (
        <LoadingState />
      ) : rules.isError ? (
        <ErrorState message={errorMessage(rules.error, "Kurallar yüklenemedi.")} />
      ) : !rules.data?.length ? (
        <EmptyState message="Henüz kural yok. Kural tanımlanmadan olay bildirimi üretilmez." />
      ) : (
        <ul className="divide-y divide-slate-100 text-sm">
          {rules.data.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-2 py-2">
              <span className="font-medium text-ink-900">{r.name}</span>
              <Badge>{`${SEVERITY_LABELS[r.min_severity] ?? r.min_severity} ve üzeri`}</Badge>
              {r.channels.map((c) => (
                <Badge key={c} tone="info">
                  {CHANNEL_LABELS[c] ?? c}
                </Badge>
              ))}
              {!r.active && <Badge tone="warning">Pasif</Badge>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Webhooks({ emailVerified }: { emailVerified: boolean }) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const hooks = useQuery({
    queryKey: ["webhooks"],
    queryFn: () => apiFetch("/api/v1/webhooks", { schema: z.array(webhookSchema) }),
  });
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["webhooks"] });
  const onError = (fallback: string) => (err: unknown) => setFeedback({ kind: "error", text: errorMessage(err, fallback) });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/webhooks", {
        method: "POST",
        body: { url, description: description || null },
        schema: webhookSchema,
      }),
    onSuccess: (data) => {
      setUrl("");
      setDescription("");
      setSecret(data.secret ?? null);
      setFeedback({ kind: "success", text: "Webhook oluşturuldu." });
      refresh();
    },
    onError: onError("Webhook oluşturulamadı."),
  });

  return (
    <Card>
      <h2 className="mb-1 text-sm font-semibold text-ink-900">Webhook uç noktaları</h2>
      <p className="mb-3 text-xs text-slate-500">
        Teslimatlar <code>X-VisiOnRoute-Signature: t=&lt;zaman&gt;,v1=&lt;HMAC-SHA256&gt;</code> ile imzalanır; alıcı
        5 dakikadan eski zaman damgalarını reddetmelidir. Özel/yerel ağ adresleri kabul edilmez.
      </p>
      {!emailVerified && (
        <Alert kind="warning" className="mb-3">
          Webhook eklemek için önce Hesabım sayfasından e-posta adresinizi doğrulayın.
        </Alert>
      )}
      <form
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <TextField label="Adres (https)" type="url" required value={url} onChange={(e) => setUrl(e.target.value)} />
        <TextField label="Açıklama" value={description} maxLength={300} onChange={(e) => setDescription(e.target.value)} />
        <Button type="submit" loading={create.isPending} disabled={!emailVerified}>
          Webhook ekle
        </Button>
      </form>
      {secret && (
        <div className="mb-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          <p className="font-medium">İmza sırrı yalnızca bir kez gösterilir; güvenli bir yere kaydedin:</p>
          <code aria-label="Webhook imza sırrı" className="mt-1 block break-all font-mono text-xs">
            {secret}
          </code>
          <Button variant="ghost" className="mt-2 px-2 py-1 text-xs" onClick={() => setSecret(null)}>
            Kaydettim, gizle
          </Button>
        </div>
      )}
      {feedback && (
        <Alert kind={feedback.kind} className="mb-3">
          {feedback.text}
        </Alert>
      )}
      {hooks.isLoading ? (
        <LoadingState />
      ) : hooks.isError ? (
        <ErrorState message={errorMessage(hooks.error, "Webhook'lar yüklenemedi.")} />
      ) : !hooks.data?.length ? (
        <EmptyState message="Henüz webhook tanımlanmamış." />
      ) : (
        <ul className="space-y-3">
          {hooks.data.map((hook) => (
            <WebhookItem
              key={hook.id}
              hook={hook}
              onChanged={refresh}
              onSecret={setSecret}
              onFeedback={setFeedback}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

function WebhookItem({
  hook,
  onChanged,
  onSecret,
  onFeedback,
}: {
  hook: Webhook;
  onChanged: () => void;
  onSecret: (secret: string | null) => void;
  onFeedback: (feedback: Feedback) => void;
}) {
  const [showDeliveries, setShowDeliveries] = useState(false);
  const base = `/api/v1/webhooks/${hook.id}`;
  const onError = (fallback: string) => (err: unknown) => onFeedback({ kind: "error", text: errorMessage(err, fallback) });
  const toggle = useMutation({
    mutationFn: () => apiFetch(base, { method: "PATCH", body: { active: !hook.active }, schema: webhookSchema }),
    onSuccess: onChanged,
    onError: onError("Webhook güncellenemedi."),
  });
  const rotate = useMutation({
    mutationFn: () => apiFetch(`${base}/rotate-secret`, { method: "POST", schema: webhookSchema }),
    onSuccess: (data) => onSecret(data.secret ?? null),
    onError: onError("Sır yenilenemedi."),
  });
  const remove = useMutation({
    mutationFn: () => apiFetch(base, { method: "DELETE" }),
    onSuccess: onChanged,
    onError: onError("Webhook silinemedi."),
  });
  const test = useMutation({
    mutationFn: () => apiFetch(`${base}/test`, { method: "POST", schema: messageSchema }),
    onSuccess: (data) => onFeedback({ kind: "success", text: data.message }),
    onError: onError("Test teslimatı kuyruğa alınamadı."),
  });
  const deliveries = useQuery({
    queryKey: ["webhook-deliveries", hook.id],
    queryFn: () => apiFetch(`${base}/deliveries?limit=20`, { schema: z.array(webhookDeliverySchema) }),
    enabled: showDeliveries,
  });

  return (
    <li className="rounded-lg border border-slate-200 p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="break-all font-mono text-xs text-ink-900">{hook.url}</p>
          {hook.description && <p className="text-slate-600">{hook.description}</p>}
          <p className="mt-1 text-xs text-slate-400">
            Son başarı: {formatDateTime(hook.last_success_at)} · Son hata: {formatDateTime(hook.last_failure_at)}
          </p>
        </div>
        <Badge tone={hook.active ? "success" : "warning"}>{hook.active ? "Etkin" : "Pasif"}</Badge>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button variant="secondary" className="px-2 py-1 text-xs" loading={test.isPending} onClick={() => test.mutate()}>
          Test gönder
        </Button>
        <Button variant="secondary" className="px-2 py-1 text-xs" loading={toggle.isPending} onClick={() => toggle.mutate()}>
          {hook.active ? "Pasifleştir" : "Etkinleştir"}
        </Button>
        <Button variant="secondary" className="px-2 py-1 text-xs" loading={rotate.isPending} onClick={() => rotate.mutate()}>
          Sırrı yenile
        </Button>
        <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => setShowDeliveries((v) => !v)}>
          {showDeliveries ? "Teslimatları gizle" : "Teslimatlar"}
        </Button>
        <ConfirmButton label="Sil" onConfirm={() => remove.mutate()} loading={remove.isPending} />
      </div>
      {showDeliveries &&
        (deliveries.isLoading ? (
          <LoadingState />
        ) : deliveries.isError ? (
          <ErrorState message={errorMessage(deliveries.error, "Teslimatlar yüklenemedi.")} />
        ) : !deliveries.data?.length ? (
          <p className="mt-2 text-xs text-slate-500">Henüz teslimat yok.</p>
        ) : (
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-1 pr-3">Zaman</th>
                  <th className="py-1 pr-3">Olay</th>
                  <th className="py-1 pr-3">Durum</th>
                  <th className="py-1 pr-3">Deneme</th>
                  <th className="py-1">Yanıt</th>
                </tr>
              </thead>
              <tbody>
                {deliveries.data.map((d) => (
                  <tr key={d.id} className="border-t border-slate-100">
                    <td className="py-1 pr-3">{formatDateTime(d.created_at)}</td>
                    <td className="py-1 pr-3 font-mono">{d.event_type}</td>
                    <td className="py-1 pr-3">{DELIVERY_STATUS[d.status] ?? d.status}</td>
                    <td className="py-1 pr-3">{d.attempts}</td>
                    <td className="py-1">{d.response_status ?? d.last_error ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </li>
  );
}
