"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { z } from "zod";
import { AuthCard } from "@/components/AuthCard";
import { Alert, Button, LoadingState, TextField, formatDateTime } from "@/components/ui";
import { ApiError, apiFetch, errorMessage } from "@/lib/api";
import { invitationPreviewSchema } from "@/lib/schemas";
import { consumeFragmentToken, passwordProblems } from "@/lib/text";

type Preview = z.infer<typeof invitationPreviewSchema>;

export default function InvitationPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [passwordAgain, setPasswordAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const fragmentToken = consumeFragmentToken();
    setToken(fragmentToken);
    if (!fragmentToken) return;
    apiFetch("/api/v1/auth/invitations/preview", {
      method: "POST",
      body: { token: fragmentToken },
      schema: invitationPreviewSchema,
      retryOnUnauthorized: false,
    })
      .then(setPreview)
      .catch((err: unknown) =>
        setLoadError(
          err instanceof ApiError && err.status === 404
            ? "Bu davet bağlantısı geçersiz, iptal edilmiş veya süresi dolmuş. Yöneticinizden yeni bir davet isteyin."
            : errorMessage(err, "Davet bilgileri alınamadı."),
        ),
      );
  }, []);

  const problems = passwordProblems(password);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || !preview) return;
    setError(null);
    if (!preview.account_exists) {
      if (problems.length) return setError(problems.join(" "));
      if (password !== passwordAgain) return setError("Parolalar eşleşmiyor.");
    }
    setSubmitting(true);
    try {
      await apiFetch("/api/v1/auth/invitations/accept", {
        method: "POST",
        body: preview.account_exists
          ? { token }
          : { token, full_name: fullName, password },
        retryOnUnauthorized: false,
      });
      router.replace("/giris?davet=kabul");
    } catch (err) {
      setError(errorMessage(err, "Davet kabul edilemedi."));
    } finally {
      setSubmitting(false);
    }
  }

  if (token === undefined) {
    return (
      <AuthCard title="Davet">
        <LoadingState />
      </AuthCard>
    );
  }

  if (!token || loadError) {
    return (
      <AuthCard
        title="Davet bağlantısı kullanılamıyor"
        footer={
          <Link href="/giris" className="text-brand-700 hover:underline">
            Giriş sayfasına dön
          </Link>
        }
      >
        <Alert kind="error">
          {loadError ??
            "Davet bağlantısı bulunamadı. Lütfen e-postanızdaki bağlantıyı yeniden açın."}
        </Alert>
      </AuthCard>
    );
  }

  if (!preview) {
    return (
      <AuthCard title="Davet">
        <LoadingState message="Davet bilgileri kontrol ediliyor…" />
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title={`${preview.organization_name} davetini kabul edin`}
      description={`${preview.email} adresi ${preview.role_label} rolüyle davet edildi. Bağlantı ${formatDateTime(preview.expires_at)} tarihine kadar geçerlidir.`}
    >
      <form onSubmit={onSubmit} className="space-y-4">
        {preview.account_exists ? (
          <Alert kind="info">
            Bu e-posta adresiyle zaten bir VisiOnRoute hesabınız var. Daveti kabul ettikten sonra
            mevcut parolanızla giriş yapabilirsiniz.
          </Alert>
        ) : (
          <>
            <TextField
              label="Ad soyad"
              required
              autoComplete="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
            <TextField
              label="Parola"
              type="password"
              required
              autoComplete="new-password"
              hint="En az 12 karakter; harf ile rakam veya sembol karışımı."
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <TextField
              label="Parola (tekrar)"
              type="password"
              required
              autoComplete="new-password"
              value={passwordAgain}
              onChange={(e) => setPasswordAgain(e.target.value)}
            />
          </>
        )}
        {error && <Alert kind="error">{error}</Alert>}
        <Button type="submit" className="w-full" loading={submitting}>
          Daveti kabul et
        </Button>
      </form>
    </AuthCard>
  );
}
