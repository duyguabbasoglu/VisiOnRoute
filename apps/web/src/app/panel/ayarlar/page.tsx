"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmButton,
  ErrorState,
  LoadingState,
  PageHeader,
  TextField,
  formatDateTime,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { INVITABLE_ROLES, can } from "@/lib/permissions";
import {
  invitationSchema,
  memberSchema,
  organizationSchema,
  organizationSecuritySchema,
  type Invitation,
  type Member,
} from "@/lib/schemas";

type Feedback = { kind: "success" | "error"; text: string } | null;

const INVITATION_STATUS: Record<string, { label: string; tone: "info" | "success" | "neutral" | "warning" }> = {
  pending: { label: "Bekliyor", tone: "info" },
  accepted: { label: "Kabul edildi", tone: "success" },
  revoked: { label: "İptal edildi", tone: "neutral" },
  expired: { label: "Süresi doldu", tone: "warning" },
};

const EMAIL_STATUS: Record<string, string> = {
  pending: "E-posta sırada",
  sending: "E-posta gönderiliyor",
  sent: "E-posta gönderildi",
  dead_letter: "E-posta gönderilemedi",
};

const TIMEZONES = ["Europe/Istanbul", "Europe/Berlin", "Europe/London", "UTC"];

export default function OrganizationSettingsPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div>
      <PageHeader
        title="Organizasyon"
        description="Organizasyon bilgileri, güvenlik politikası, kullanıcılar ve davetler."
      />
      <OrganizationCard canEdit={can(user, "org.update")} />
      <SecurityPolicyCard canEdit={can(user, "org.update")} actorHasMfa={user.mfa_enabled} />
      {can(user, "org.members.read") && (
        <MembersCard
          canManage={can(user, "org.members.manage")}
          isOwner={user.role === "owner"}
          currentUserId={user.id}
        />
      )}
      {can(user, "org.invitations.manage") && <InvitationsCard emailVerified={user.email_verified} />}
    </div>
  );
}

function OrganizationCard({ canEdit }: { canEdit: boolean }) {
  const queryClient = useQueryClient();
  const org = useQuery({
    queryKey: ["organization"],
    queryFn: () => apiFetch("/api/v1/organizations/current", { schema: organizationSchema }),
  });
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("Europe/Istanbul");
  const [feedback, setFeedback] = useState<Feedback>(null);

  useEffect(() => {
    if (org.data) {
      setName(org.data.name);
      setTimezone(org.data.timezone);
    }
  }, [org.data]);

  const save = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/organizations/current", {
        method: "PATCH",
        body: { name, timezone },
        schema: organizationSchema,
      }),
    onSuccess: () => {
      setFeedback({ kind: "success", text: "Organizasyon bilgileri kaydedildi." });
      void queryClient.invalidateQueries({ queryKey: ["organization"] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Kaydedilemedi.") }),
  });

  return (
    <Card className="mb-6">
      <h2 className="mb-3 text-sm font-semibold text-ink-900">Organizasyon bilgileri</h2>
      {org.isLoading && <LoadingState />}
      {org.isError && (
        <ErrorState message={errorMessage(org.error, "Bilgiler yüklenemedi.")} onRetry={() => void org.refetch()} />
      )}
      {org.data && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
          className="flex flex-wrap items-end gap-3"
        >
          <TextField label="Ad" value={name} disabled={!canEdit} onChange={(e) => setName(e.target.value)} />
          <div>
            <label htmlFor="org-timezone" className="block text-sm font-medium text-slate-700">
              Saat dilimi
            </label>
            <select
              id="org-timezone"
              value={timezone}
              disabled={!canEdit}
              onChange={(e) => setTimezone(e.target.value)}
              className="mt-1 rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-50"
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>
          {canEdit && (
            <Button type="submit" loading={save.isPending}>
              Kaydet
            </Button>
          )}
          <p className="w-full text-xs text-slate-400">
            Kısa ad: {org.data.slug} · Para birimi: {org.data.currency}
          </p>
        </form>
      )}
      {feedback && (
        <Alert kind={feedback.kind} className="mt-3">
          {feedback.text}
        </Alert>
      )}
    </Card>
  );
}

function SecurityPolicyCard({ canEdit, actorHasMfa }: { canEdit: boolean; actorHasMfa: boolean }) {
  const queryClient = useQueryClient();
  const policy = useQuery({
    queryKey: ["organization-security"],
    queryFn: () => apiFetch("/api/v1/organizations/current/security", { schema: organizationSecuritySchema }),
  });
  const [feedback, setFeedback] = useState<Feedback>(null);
  const update = useMutation({
    mutationFn: (mfaRequired: boolean) =>
      apiFetch("/api/v1/organizations/current/security", {
        method: "PATCH",
        body: { mfa_required: mfaRequired },
        schema: organizationSecuritySchema,
      }),
    onSuccess: (data) => {
      setFeedback({
        kind: "success",
        text: data.mfa_required
          ? "İki adımlı doğrulama tüm kullanıcılar için zorunlu hale getirildi."
          : "İki adımlı doğrulama zorunluluğu kaldırıldı.",
      });
      void queryClient.invalidateQueries({ queryKey: ["organization-security"] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Politika güncellenemedi.") }),
  });

  return (
    <Card className="mb-6">
      <h2 className="mb-2 text-sm font-semibold text-ink-900">Güvenlik politikası</h2>
      {policy.isLoading && <LoadingState />}
      {policy.isError && <ErrorState message={errorMessage(policy.error, "Politika yüklenemedi.")} />}
      {policy.data && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm text-slate-600">
            <p>
              İki adımlı doğrulama zorunluluğu:{" "}
              {policy.data.mfa_required ? <Badge tone="success">Açık</Badge> : <Badge>Kapalı</Badge>}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Açıkken MFA kurmamış kullanıcılar yalnızca Hesabım sayfasına erişebilir.
            </p>
          </div>
          {canEdit && (
            <Button
              variant="secondary"
              loading={update.isPending}
              disabled={!policy.data.mfa_required && !actorHasMfa}
              onClick={() => update.mutate(!policy.data.mfa_required)}
            >
              {policy.data.mfa_required ? "Zorunluluğu kaldır" : "Zorunlu kıl"}
            </Button>
          )}
        </div>
      )}
      {canEdit && policy.data && !policy.data.mfa_required && !actorHasMfa && (
        <p className="mt-2 text-xs text-slate-500">
          Politikayı açmadan önce Hesabım sayfasından kendi hesabınızda MFA&apos;yı etkinleştirin.
        </p>
      )}
      {feedback && (
        <Alert kind={feedback.kind} className="mt-3">
          {feedback.text}
        </Alert>
      )}
    </Card>
  );
}

function MembersCard({
  canManage,
  isOwner,
  currentUserId,
}: {
  canManage: boolean;
  isOwner: boolean;
  currentUserId: string;
}) {
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState<Feedback>(null);
  const members = useQuery({
    queryKey: ["members"],
    queryFn: () => apiFetch("/api/v1/organizations/current/members", { schema: z.array(memberSchema) }),
  });
  const done = (text: string) => {
    setFeedback({ kind: "success", text });
    void queryClient.invalidateQueries({ queryKey: ["members"] });
  };
  const fail = (err: unknown) => setFeedback({ kind: "error", text: errorMessage(err, "İşlem tamamlanamadı.") });

  const changeRole = useMutation({
    mutationFn: ({ id, role }: { id: string; role: string }) =>
      apiFetch(`/api/v1/organizations/current/members/${id}`, { method: "PATCH", body: { role }, schema: memberSchema }),
    onSuccess: () => done("Rol güncellendi."),
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/organizations/current/members/${id}`, { method: "DELETE" }),
    onSuccess: () => done("Kullanıcı organizasyondan çıkarıldı."),
    onError: fail,
  });
  const resetMfa = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/organizations/current/members/${id}/mfa`, { method: "DELETE" }),
    onSuccess: () => done("Kullanıcının iki adımlı doğrulaması sıfırlandı ve oturumları kapatıldı."),
    onError: fail,
  });

  return (
    <Card className="mb-6">
      <h2 className="mb-3 text-sm font-semibold text-ink-900">Kullanıcılar</h2>
      {members.isLoading && <LoadingState />}
      {members.isError && (
        <ErrorState message={errorMessage(members.error, "Kullanıcılar yüklenemedi.")} onRetry={() => void members.refetch()} />
      )}
      {members.data && (
        <ul className="divide-y divide-slate-100">
          {members.data.map((m: Member) => {
            const isSelf = m.user_id === currentUserId;
            const editable = canManage && m.role !== "owner" && !isSelf;
            return (
              <li key={m.membership_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="text-sm text-ink-900">
                    {m.full_name} {isSelf && <span className="text-xs text-slate-400">(siz)</span>}
                  </p>
                  <p className="truncate text-xs text-slate-500">{m.email}</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {m.mfa_enabled ? <Badge tone="success">MFA etkin</Badge> : <Badge>MFA kapalı</Badge>}
                    {!m.email_verified && <Badge tone="warning">E-posta doğrulanmadı</Badge>}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {editable ? (
                    <select
                      aria-label={`${m.full_name} rolü`}
                      value={m.role}
                      onChange={(e) => changeRole.mutate({ id: m.membership_id, role: e.target.value })}
                      className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                    >
                      {INVITABLE_ROLES.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-sm text-slate-600">{m.role_label}</span>
                  )}
                  {isOwner && !isSelf && m.mfa_enabled && (
                    <ConfirmButton label="MFA sıfırla" onConfirm={() => resetMfa.mutate(m.membership_id)} loading={resetMfa.isPending} />
                  )}
                  {editable && (
                    <ConfirmButton label="Çıkar" onConfirm={() => remove.mutate(m.membership_id)} loading={remove.isPending} />
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {feedback && (
        <Alert kind={feedback.kind} className="mt-3">
          {feedback.text}
        </Alert>
      )}
    </Card>
  );
}

function InvitationsCard({ emailVerified }: { emailVerified: boolean }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("analyst");
  const [feedback, setFeedback] = useState<Feedback>(null);
  const invitations = useQuery({
    queryKey: ["invitations"],
    queryFn: () => apiFetch("/api/v1/organizations/current/invitations", { schema: z.array(invitationSchema) }),
    refetchInterval: (query) =>
      query.state.data?.some((i) => i.status === "pending" && (i.email_status === "pending" || i.email_status === "sending"))
        ? 5000
        : false,
  });
  const refresh = (text: string) => {
    setFeedback({ kind: "success", text });
    void queryClient.invalidateQueries({ queryKey: ["invitations"] });
  };
  const fail = (err: unknown) => setFeedback({ kind: "error", text: errorMessage(err, "İşlem tamamlanamadı.") });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/organizations/current/invitations", {
        method: "POST",
        body: { email, role },
        schema: invitationSchema,
      }),
    onSuccess: (inv) => {
      setEmail("");
      refresh(`Davet ${inv.email} adresine e-postayla gönderiliyor.`);
    },
    onError: fail,
  });
  const resend = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/v1/organizations/current/invitations/${id}/resend`, { method: "POST", schema: invitationSchema }),
    onSuccess: () => refresh("Davet yeni bir bağlantıyla yeniden gönderiliyor; önceki bağlantı geçersiz oldu."),
    onError: fail,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/organizations/current/invitations/${id}`, { method: "DELETE" }),
    onSuccess: () => refresh("Davet iptal edildi."),
    onError: fail,
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFeedback(null);
    create.mutate();
  }

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink-900">Davetler</h2>
      {!emailVerified && (
        <Alert kind="warning" className="mb-3">
          Davet gönderebilmek için önce Hesabım sayfasından e-posta adresinizi doğrulayın.
        </Alert>
      )}
      <form onSubmit={onSubmit} className="mb-4 flex flex-wrap items-end gap-3">
        <TextField label="E-posta" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <div>
          <label htmlFor="invite-role" className="block text-sm font-medium text-slate-700">
            Rol
          </label>
          <select
            id="invite-role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="mt-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            {INVITABLE_ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit" loading={create.isPending}>
          Davet gönder
        </Button>
      </form>
      {feedback && (
        <Alert kind={feedback.kind} className="mb-3">
          {feedback.text}
        </Alert>
      )}
      {invitations.isLoading && <LoadingState />}
      {invitations.isError && <ErrorState message={errorMessage(invitations.error, "Davetler yüklenemedi.")} />}
      {invitations.data && invitations.data.length === 0 && (
        <p className="text-sm text-slate-500">Henüz davet gönderilmedi. Ekip arkadaşlarınızı yukarıdan davet edin.</p>
      )}
      {invitations.data && invitations.data.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {invitations.data.map((inv: Invitation) => {
            const status = INVITATION_STATUS[inv.status] ?? { label: inv.status, tone: "neutral" as const };
            const open = inv.status === "pending" || inv.status === "expired";
            return (
              <li key={inv.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm text-ink-900">{inv.email}</p>
                  <p className="text-xs text-slate-500">
                    {inv.role_label} · Son geçerlilik {formatDateTime(inv.expires_at)}
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    <Badge tone={status.tone}>{status.label}</Badge>
                    {inv.email_status && inv.status === "pending" && (
                      <Badge tone={inv.email_status === "dead_letter" ? "danger" : "neutral"}>
                        {EMAIL_STATUS[inv.email_status] ?? inv.email_status}
                      </Badge>
                    )}
                  </div>
                </div>
                {open && (
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" loading={resend.isPending} onClick={() => resend.mutate(inv.id)}>
                      Yeniden gönder
                    </Button>
                    {inv.status === "pending" && (
                      <ConfirmButton label="İptal et" onConfirm={() => revoke.mutate(inv.id)} loading={revoke.isPending} />
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
