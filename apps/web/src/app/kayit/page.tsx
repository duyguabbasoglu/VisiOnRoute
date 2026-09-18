"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { AuthCard } from "@/components/AuthCard";
import { Alert, Button, TextField } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { SLUG_PATTERN, passwordProblems, slugify } from "@/lib/text";

export default function RegisterPage() {
  const { user, loading, register } = useAuth();
  const router = useRouter();
  const [organizationName, setOrganizationName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordAgain, setPasswordAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/panel");
  }, [loading, user, router]);

  const problems = passwordProblems(password);
  const slugError = slug && !SLUG_PATTERN.test(slug)
    ? "3–80 karakter; küçük harf, rakam ve tire kullanın."
    : undefined;
  const mismatch = passwordAgain && password !== passwordAgain ? "Parolalar eşleşmiyor." : undefined;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (problems.length || slugError || mismatch || !slug) return;
    setSubmitting(true);
    try {
      await register({ organization_name: organizationName, slug, email, full_name: fullName, password });
      router.replace("/panel");
    } catch (err) {
      setError(errorMessage(err, "Kayıt tamamlanamadı. Lütfen tekrar deneyin."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Organizasyon oluşturun"
      description="Filonuz için VisiOnRoute hesabı açın. 30 günlük deneme ile başlarsınız."
      footer={
        <p className="text-slate-600">
          Zaten hesabınız var mı?{" "}
          <Link href="/giris" className="font-medium text-brand-700 hover:underline">
            Giriş yapın
          </Link>
        </p>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <TextField
          label="Organizasyon adı"
          required
          minLength={2}
          value={organizationName}
          onChange={(e) => {
            setOrganizationName(e.target.value);
            if (!slugEdited) setSlug(slugify(e.target.value));
          }}
        />
        <TextField
          label="Kısa ad"
          required
          value={slug}
          hint="Organizasyonunuzu tanımlar; daha sonra değiştirilemez."
          error={touched || slug ? slugError : undefined}
          onChange={(e) => {
            setSlugEdited(true);
            setSlug(e.target.value.toLowerCase());
          }}
        />
        <TextField
          label="Ad soyad"
          required
          autoComplete="name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
        />
        <TextField
          label="E-posta"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          label="Parola"
          type="password"
          required
          autoComplete="new-password"
          value={password}
          hint="En az 12 karakter; harf ile rakam veya sembol karışımı."
          error={touched && problems.length ? problems.join(" ") : undefined}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          label="Parola (tekrar)"
          type="password"
          required
          autoComplete="new-password"
          value={passwordAgain}
          error={mismatch}
          onChange={(e) => setPasswordAgain(e.target.value)}
        />
        {error && <Alert kind="error">{error}</Alert>}
        <Button type="submit" className="w-full" loading={submitting}>
          {submitting ? "Hesap oluşturuluyor…" : "Hesap oluştur"}
        </Button>
        <p className="text-xs text-slate-500">
          Kayıttan sonra e-posta adresinize bir doğrulama bağlantısı gönderilir.
        </p>
      </form>
    </AuthCard>
  );
}
