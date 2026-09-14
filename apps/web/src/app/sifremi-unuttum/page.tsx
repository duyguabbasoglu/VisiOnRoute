"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { AuthCard } from "@/components/AuthCard";
import { Alert, Button, TextField } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { messageSchema } from "@/lib/schemas";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const response = await apiFetch("/api/v1/auth/password/forgot", {
        method: "POST",
        body: { email },
        schema: messageSchema,
        retryOnUnauthorized: false,
      });
      setSent(response.message);
    } catch (err) {
      setError(errorMessage(err, "İstek gönderilemedi. Lütfen tekrar deneyin."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Parolanızı mı unuttunuz?"
      description="Hesabınızın e-posta adresini girin; size parola sıfırlama bağlantısı gönderelim."
      footer={
        <Link href="/giris" className="text-brand-700 hover:underline">
          Giriş sayfasına dön
        </Link>
      }
    >
      {sent ? (
        <Alert kind="success">{sent}</Alert>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <TextField
            label="E-posta"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {error && <Alert kind="error">{error}</Alert>}
          <Button type="submit" className="w-full" loading={submitting}>
            Sıfırlama bağlantısı gönder
          </Button>
        </form>
      )}
    </AuthCard>
  );
}
