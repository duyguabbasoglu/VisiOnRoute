"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";

/** Shown on public pages when a session is already open. */
export function SessionHint() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <Link
      href="/panel"
      className="mb-5 inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs font-medium text-emerald-200 hover:bg-emerald-400/15"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden />
      Oturumunuz açık — panele git
      <span aria-hidden>→</span>
    </Link>
  );
}
