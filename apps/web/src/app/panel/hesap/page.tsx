"use client";

import QRCode from "qrcode";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { z } from "zod";
import { Alert, Badge, Button, Card, PageHeader, TextField, formatDateTime } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  messageSchema,
  mfaSetupSchema,
  privacyRequestSchema,
  recoveryCodesSchema,
  signedLinkSchema,
} from "@/lib/schemas";

type Feedback = { kind: "success" | "error" | "info"; text: string } | null;

export default function AccountPage() {
  const { user, refreshUser, logout } = useAuth();
  const [verifyFeedback, setVerifyFeedback] = useState<Feedback>(null);
  const [resending, setResending] = useState(false);

  if (!user) return null;

  async function resendVerification() {
    setResending(true);
    try {
      const res = await apiFetch("/api/v1/auth/email/resend-verification", {
        method: "POST",
        schema: messageSchema,
      });
      setVerifyFeedback({ kind: "success", text: res.message });
    } catch (err) {
      setVerifyFeedback({ kind: "error", text: errorMessage(err, "E-posta gönderilemedi.") });
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <PageHeader title="Hesabım" description="Profil bilgileriniz ve hesap güvenliği." />

      {user.mfa_required && !user.mfa_enabled && (
        <Alert kind="warning" className="mb-6">
          Organizasyonunuz iki adımlı doğrulamayı zorunlu kılıyor. Panelin diğer bölümlerine
          erişmek için aşağıdan etkinleştirin.
        </Alert>
      )}

      <Card className="mb-6">
        <h2 className="mb-3 text-sm font-semibold text-ink-900">Profil</h2>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <Row label="Ad soyad" value={user.full_name} />
          <Row label="E-posta" value={user.email} />
          <Row label="Organizasyon" value={user.organization_name ?? "—"} />
          <Row label="Rol" value={user.role_label ?? (user.is_platform_admin ? "Platform yöneticisi" : "—")} />
        </dl>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          {user.email_verified ? (
            <Badge tone="success">E-posta doğrulandı</Badge>
          ) : (
            <>
              <Badge tone="warning">E-posta doğrulanmadı</Badge>
              <Button variant="secondary" loading={resending} onClick={resendVerification}>
                Doğrulama e-postasını yeniden gönder
              </Button>
            </>
          )}
        </div>
        {verifyFeedback && (
          <Alert kind={verifyFeedback.kind} className="mt-3">
            {verifyFeedback.text}
          </Alert>
        )}
      </Card>

      <MfaSection mfaEnabled={user.mfa_enabled} onChanged={refreshUser} />

      {user.organization_id && <PersonalDataSection />}

      <Card>
        <h2 className="mb-2 text-sm font-semibold text-ink-900">Oturum</h2>
        <p className="mb-3 text-sm text-slate-600">
          Bu cihazdaki oturumunuzu kapatır. Parolanızı sıfırladığınızda tüm cihazlardaki
          oturumlar otomatik olarak kapatılır.
        </p>
        <Button
          variant="secondary"
          onClick={() => {
            void logout().then(() => window.location.assign("/giris?cikis=tamam"));
          }}
        >
          Çıkış yap
        </Button>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className="text-ink-900">{value}</dd>
    </div>
  );
}

type SetupState =
  | { step: "idle" }
  | { step: "password" }
  | { step: "scan"; secret: string; qrDataUrl: string }
  | { step: "codes"; codes: string[] };

function MfaSection({
  mfaEnabled,
  onChanged,
}: {
  mfaEnabled: boolean;
  onChanged: () => Promise<void>;
}) {
  const [setup, setSetup] = useState<SetupState>({ step: "idle" });
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [manage, setManage] = useState<"disable" | "regenerate" | null>(null);
  const [savedCodes, setSavedCodes] = useState(false);

  async function startSetup(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFeedback(null);
    try {
      const res = await apiFetch("/api/v1/auth/mfa/setup", {
        method: "POST",
        body: { password },
        schema: mfaSetupSchema,
      });
      const qrDataUrl = await QRCode.toDataURL(res.otpauth_uri, { margin: 1, width: 192 });
      setSetup({ step: "scan", secret: res.secret, qrDataUrl });
      setPassword("");
    } catch (err) {
      setFeedback({ kind: "error", text: errorMessage(err, "Kurulum başlatılamadı.") });
    } finally {
      setBusy(false);
    }
  }

  async function confirmSetup(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFeedback(null);
    try {
      const res = await apiFetch("/api/v1/auth/mfa/confirm", {
        method: "POST",
        body: { code },
        schema: recoveryCodesSchema,
      });
      setSetup({ step: "codes", codes: res.recovery_codes });
      setSavedCodes(false);
      setCode("");
    } catch (err) {
      setFeedback({ kind: "error", text: errorMessage(err, "Kod doğrulanamadı.") });
    } finally {
      setBusy(false);
    }
  }

  async function submitManage(e: FormEvent) {
    e.preventDefault();
    if (!manage) return;
    setBusy(true);
    setFeedback(null);
    try {
      if (manage === "disable") {
        const res = await apiFetch("/api/v1/auth/mfa/disable", {
          method: "POST",
          body: { password, code },
          schema: messageSchema,
        });
        setFeedback({ kind: "success", text: res.message });
        await onChanged();
      } else {
        const res = await apiFetch("/api/v1/auth/mfa/recovery-codes", {
          method: "POST",
          body: { password, code },
          schema: recoveryCodesSchema,
        });
        setSetup({ step: "codes", codes: res.recovery_codes });
        setSavedCodes(false);
      }
      setManage(null);
      setPassword("");
      setCode("");
    } catch (err) {
      setFeedback({ kind: "error", text: errorMessage(err, "İşlem tamamlanamadı.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-6">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink-900">İki adımlı doğrulama (MFA)</h2>
        {mfaEnabled ? <Badge tone="success">Etkin</Badge> : <Badge>Kapalı</Badge>}
      </div>
      <p className="mb-4 text-sm text-slate-600">
        Girişte parolanıza ek olarak kimlik doğrulama uygulamanızdaki (ör. Google Authenticator,
        Microsoft Authenticator) tek kullanımlık kod istenir.
      </p>

      {setup.step === "codes" && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-medium text-amber-900">Kurtarma kodlarınız</p>
          <p className="mt-1 text-sm text-amber-900">
            Telefonunuza erişemezseniz bu kodlarla giriş yapabilirsiniz. Her kod bir kez
            kullanılabilir ve bu kodlar tekrar gösterilmez.
          </p>
          <ul aria-label="Kurtarma kodları" className="mt-3 grid grid-cols-2 gap-2 font-mono text-sm">
            {setup.codes.map((recoveryCode) => (
              <li key={recoveryCode} className="rounded bg-white px-2 py-1 text-ink-900">
                {recoveryCode}
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              onClick={() => void navigator.clipboard?.writeText(setup.codes.join("\n"))}
            >
              Kopyala
            </Button>
            <label className="flex items-center gap-2 text-sm text-amber-900">
              <input
                type="checkbox"
                checked={savedCodes}
                onChange={(e) => setSavedCodes(e.target.checked)}
              />
              Kodları güvenli bir yere kaydettim
            </label>
            <Button
              disabled={!savedCodes}
              onClick={() => {
                setSetup({ step: "idle" });
                void onChanged();
              }}
            >
              Tamam
            </Button>
          </div>
        </div>
      )}

      {!mfaEnabled && setup.step === "idle" && (
        <Button onClick={() => setSetup({ step: "password" })}>İki adımlı doğrulamayı etkinleştir</Button>
      )}

      {!mfaEnabled && setup.step === "password" && (
        <form onSubmit={startSetup} className="flex flex-wrap items-end gap-3">
          <TextField
            label="Güvenlik için parolanızı girin"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Button type="submit" loading={busy}>
            Devam
          </Button>
          <Button variant="ghost" onClick={() => setSetup({ step: "idle" })}>
            Vazgeç
          </Button>
        </form>
      )}

      {!mfaEnabled && setup.step === "scan" && (
        <form onSubmit={confirmSetup} className="space-y-4">
          <div className="flex flex-wrap items-start gap-6">
            {/* eslint-disable-next-line @next/next/no-img-element -- local data URL, generated in the browser */}
            <img
              src={setup.qrDataUrl}
              width={192}
              height={192}
              alt="Kimlik doğrulama uygulaması için QR kodu"
              className="rounded border border-slate-200"
            />
            <div className="min-w-0 flex-1 text-sm text-slate-600">
              <p>1. Uygulamanızda QR kodunu tarayın.</p>
              <p className="mt-2">Tarayamıyorsanız bu anahtarı elle girin:</p>
              <code className="mt-1 block break-all rounded bg-slate-50 p-2 font-mono text-xs text-ink-900">
                {setup.secret}
              </code>
              <p className="mt-2">2. Uygulamanın gösterdiği 6 haneli kodu girin.</p>
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <TextField
              label="Doğrulama kodu"
              required
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
            <Button type="submit" loading={busy}>
              Etkinleştir
            </Button>
          </div>
        </form>
      )}

      {mfaEnabled && setup.step !== "codes" && (
        <div className="space-y-3">
          {manage === null ? (
            <div className="flex flex-wrap gap-3">
              <Button variant="secondary" onClick={() => setManage("regenerate")}>
                Kurtarma kodlarını yenile
              </Button>
              <Button variant="secondary" onClick={() => setManage("disable")}>
                İki adımlı doğrulamayı kapat
              </Button>
            </div>
          ) : (
            <form onSubmit={submitManage} className="space-y-3">
              {manage === "disable" && (
                <Alert kind="warning">
                  Kapatırsanız hesabınız yalnızca parolayla korunur. Organizasyonunuz MFA&apos;yı
                  zorunlu kılıyorsa panele erişiminiz kısıtlanır.
                </Alert>
              )}
              <div className="flex flex-wrap items-end gap-3">
                <TextField
                  label="Parola"
                  type="password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <TextField
                  label="Doğrulama veya kurtarma kodu"
                  required
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
                <Button type="submit" variant={manage === "disable" ? "danger" : "primary"} loading={busy}>
                  {manage === "disable" ? "Kapat" : "Yeni kodlar üret"}
                </Button>
                <Button variant="ghost" onClick={() => setManage(null)}>
                  Vazgeç
                </Button>
              </div>
            </form>
          )}
        </div>
      )}

      {feedback && (
        <Alert kind={feedback.kind} className="mt-4">
          {feedback.text}
        </Alert>
      )}
    </Card>
  );
}

function PersonalDataSection() {
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState<Feedback>(null);
  const requests = useQuery({
    queryKey: ["my-privacy-requests"],
    queryFn: () => apiFetch("/api/v1/privacy/me/requests", { schema: z.array(privacyRequestSchema) }),
    refetchInterval: (query) =>
      query.state.data?.some((r) => r.status === "pending" || r.status === "processing") ? 5000 : false,
  });
  const exportData = useMutation({
    mutationFn: () => apiFetch("/api/v1/privacy/me/export", { method: "POST", schema: privacyRequestSchema }),
    onSuccess: () => {
      setFeedback({ kind: "success", text: "Talebiniz alındı. Dosya hazır olduğunda e-posta ile bilgilendirileceksiniz." });
      void queryClient.invalidateQueries({ queryKey: ["my-privacy-requests"] });
    },
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "Talep oluşturulamadı.") }),
  });
  const download = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/v1/privacy/me/requests/${id}/download`, { schema: signedLinkSchema }),
    onSuccess: ({ url }) => window.open(url, "_blank", "noopener,noreferrer"),
    onError: (err) => setFeedback({ kind: "error", text: errorMessage(err, "İndirme bağlantısı alınamadı.") }),
  });
  const active = requests.data?.some((r) => r.status === "pending" || r.status === "processing") ?? false;

  return (
    <Card className="mb-6">
      <h2 className="mb-2 text-sm font-semibold text-ink-900">Kişisel verilerim (KVKK)</h2>
      <p className="mb-3 text-sm text-slate-600">
        Bu organizasyonda sizinle ilişkili kişisel verilerin bir kopyasını (JSON/CSV) indirebilirsiniz. Dosya 7 gün
        boyunca saklanır. Verilerinizin silinmesi için organizasyon yöneticinize başvurun.
      </p>
      <Button variant="secondary" loading={exportData.isPending} disabled={active} onClick={() => exportData.mutate()}>
        {active ? "Talebiniz işleniyor" : "Verilerimin kopyasını iste"}
      </Button>
      {feedback && (
        <Alert kind={feedback.kind} className="mt-3">
          {feedback.text}
        </Alert>
      )}
      {requests.data && requests.data.length > 0 && (
        <ul className="mt-4 space-y-2 text-sm">
          {requests.data.slice(0, 5).map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-2">
              <span>{formatDateTime(r.created_at)}</span>
              <Badge tone={r.status === "completed" ? "success" : r.status === "failed" ? "danger" : "info"}>
                {r.status_label}
              </Badge>
              {r.download_available && (
                <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => download.mutate(r.id)}>
                  İndir
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
