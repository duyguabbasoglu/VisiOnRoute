"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { AuthCard } from "@/components/AuthCard";
import { Alert, Button, LoadingState, TextField } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { consumeFragmentToken, passwordProblems } from "@/lib/text";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [password, setPassword] = useState("");
  const [passwordAgain, setPasswordAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => setToken(consumeFragmentToken()), []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    const problems = passwordProblems(password);
    if (problems.length) return setError(problems.join(" "));
    if (password !== passwordAgain) return setError("Parolalar eşleşmiyor.");
    setError(null);
    setSubmitting(true);
    try {
      await apiFetch("/api/v1/auth/password/reset", {
        method: "POST",
        body: { token, password },
        retryOnUnauthorized: false,
      });
      router.replace("/giris?sifre=guncellendi");
    } catch (err) {
      setError(errorMessage(err, "Parola güncellenemedi."));
    } finally {
      setSubmitting(false);
    }
  }

  const footer = (
    <Link href="/sifremi-unuttum" className="text-brand-700 hover:underline">
      Yeni sıfırlama bağlantısı iste
    </Link>
  );

  if (token === undefined) {
    return (
      <AuthCard title="Yeni parola belirleyin">
        <LoadingState />
      </AuthCard>
    );
  }
  if (!token) {
    return (
      <AuthCard title="Bağlantı bulunamadı" footer={footer}>
        <Alert kind="error">
          Sıfırlama bağlantısı eksik. Lütfen e-postanızdaki bağlantıyı yeniden açın.
        </Alert>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Yeni parola belirleyin"
      description="Parolanız değiştiğinde açık olan tüm oturumlarınız güvenliğiniz için kapatılır."
      footer={footer}
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <TextField
          label="Yeni parola"
          type="password"
          required
          autoComplete="new-password"
          hint="En az 12 karakter; harf ile rakam veya sembol karışımı."
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          label="Yeni parola (tekrar)"
          type="password"
          required
          autoComplete="new-password"
          value={passwordAgain}
          onChange={(e) => setPasswordAgain(e.target.value)}
        />
        {error && <Alert kind="error">{error}</Alert>}
        <Button type="submit" className="w-full" loading={submitting}>
          Parolayı güncelle
        </Button>
      </form>
    </AuthCard>
  );
}
