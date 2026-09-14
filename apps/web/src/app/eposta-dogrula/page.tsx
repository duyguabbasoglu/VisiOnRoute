"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AuthCard } from "@/components/AuthCard";
import { Alert, LoadingState } from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { consumeFragmentToken } from "@/lib/text";

type State = { kind: "loading" } | { kind: "success" } | { kind: "error"; message: string };

export default function VerifyEmailPage() {
  const { user, refreshUser } = useAuth();
  const [state, setState] = useState<State>({ kind: "loading" });
  const started = useRef(false);

  useEffect(() => {
    // The token is single-use: guard against React StrictMode's double effect.
    if (started.current) return;
    started.current = true;
    const token = consumeFragmentToken();
    if (!token) {
      setState({
        kind: "error",
        message: "Doğrulama bağlantısı eksik. Lütfen e-postanızdaki bağlantıyı yeniden açın.",
      });
      return;
    }
    apiFetch("/api/v1/auth/email/verify", {
      method: "POST",
      body: { token },
      retryOnUnauthorized: false,
    })
      .then(() => setState({ kind: "success" }))
      .catch((err: unknown) =>
        setState({ kind: "error", message: errorMessage(err, "E-posta doğrulanamadı.") }),
      );
  }, []);

  useEffect(() => {
    if (state.kind === "success" && user) void refreshUser().catch(() => undefined);
  }, [state.kind, user, refreshUser]);

  return (
    <AuthCard
      title="E-posta doğrulama"
      footer={
        <Link href={user ? "/panel" : "/giris"} className="text-brand-700 hover:underline">
          {user ? "Panele dön" : "Giriş sayfasına git"}
        </Link>
      }
    >
      {state.kind === "loading" && <LoadingState message="E-posta adresiniz doğrulanıyor…" />}
      {state.kind === "success" && (
        <Alert kind="success">E-posta adresiniz doğrulandı. Teşekkürler!</Alert>
      )}
      {state.kind === "error" && (
        <Alert kind="error">
          {state.message} Panelde oturum açıkken Hesabım sayfasından yeni bir doğrulama e-postası
          isteyebilirsiniz.
        </Alert>
      )}
    </AuthCard>
  );
}
