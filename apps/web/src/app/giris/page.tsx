"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { AuthCard } from "@/components/AuthCard";
import { Alert, Button, TextField } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const NOTICES: Record<string, { kind: "success" | "warning"; text: string }> = {
  "oturum:sona-erdi": {
    kind: "warning",
    text: "Oturumunuzun süresi doldu veya oturum kapatıldı. Lütfen yeniden giriş yapın.",
  },
  "sifre:guncellendi": {
    kind: "success",
    text: "Parolanız güncellendi. Yeni parolanızla giriş yapabilirsiniz.",
  },
  "davet:kabul": {
    kind: "success",
    text: "Davet kabul edildi. Giriş yaparak organizasyonunuza erişebilirsiniz.",
  },
  "cikis:tamam": { kind: "success", text: "Oturumunuz kapatıldı." },
};

export default function LoginPage() {
  const { user, loading, login, verifyMfa } = useAuth();
  const router = useRouter();
  const [notice, setNotice] = useState<{ kind: "success" | "warning"; text: string } | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    for (const [key, value] of params) {
      const found = NOTICES[`${key}:${value}`];
      if (found) setNotice(found);
    }
  }, []);

  useEffect(() => {
    if (!loading && user) router.replace("/panel");
  }, [loading, user, router]);

  async function onPasswordSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await login(email, password);
      if (result.status === "mfa_required") {
        setMfaToken(result.mfaToken);
        setPassword("");
      } else {
        router.replace("/panel");
      }
    } catch (err) {
      setError(errorMessage(err, "Giriş sırasında bir hata oluştu."));
    } finally {
      setSubmitting(false);
    }
  }

  async function onMfaSubmit(e: FormEvent) {
    e.preventDefault();
    if (!mfaToken) return;
    setError(null);
    setSubmitting(true);
    try {
      await verifyMfa(mfaToken, useRecovery ? { recoveryCode: code } : { code });
      router.replace("/panel");
    } catch (err) {
      setError(errorMessage(err, "Doğrulama tamamlanamadı."));
    } finally {
      setSubmitting(false);
    }
  }

  if (mfaToken) {
    return (
      <AuthCard
        title="İki adımlı doğrulama"
        description={
          useRecovery
            ? "Kaydettiğiniz kurtarma kodlarından birini girin. Her kod yalnızca bir kez kullanılabilir."
            : "Kimlik doğrulama uygulamanızdaki 6 haneli kodu girin."
        }
        footer={
          <button
            type="button"
            className="text-brand-700 hover:underline"
            onClick={() => {
              setMfaToken(null);
              setCode("");
              setError(null);
            }}
          >
            Farklı bir hesapla giriş yap
          </button>
        }
      >
        <form onSubmit={onMfaSubmit} className="space-y-4">
          <TextField
            label={useRecovery ? "Kurtarma kodu" : "Doğrulama kodu"}
            required
            autoFocus
            autoComplete="one-time-code"
            inputMode={useRecovery ? "text" : "numeric"}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          {error && <Alert kind="error">{error}</Alert>}
          <Button type="submit" className="w-full" loading={submitting}>
            Doğrula ve giriş yap
          </Button>
          <button
            type="button"
            className="text-sm text-brand-700 hover:underline"
            onClick={() => {
              setUseRecovery((v) => !v);
              setCode("");
            }}
          >
            {useRecovery ? "Doğrulama uygulaması kodunu kullan" : "Kurtarma kodu kullan"}
          </button>
        </form>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Giriş yapın"
      description="VisiOnRoute ulaşım güvenliği platformu"
      footer={
        <div className="flex flex-wrap justify-between gap-2">
          <Link href="/sifremi-unuttum" className="text-brand-700 hover:underline">
            Parolamı unuttum
          </Link>
          <Link href="/kayit" className="text-brand-700 hover:underline">
            Yeni organizasyon oluştur
          </Link>
        </div>
      }
    >
      {notice && (
        <Alert kind={notice.kind} className="mb-4">
          {notice.text}
        </Alert>
      )}
      <form onSubmit={onPasswordSubmit} className="space-y-4">
        <TextField
          label="E-posta"
          type="email"
          required
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          label="Parola"
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <Alert kind="error">{error}</Alert>}
        <Button type="submit" className="w-full" loading={submitting}>
          {submitting ? "Giriş yapılıyor…" : "Giriş yap"}
        </Button>
      </form>
    </AuthCard>
  );
}
