"use client";

import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold text-ink-900">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
      {children}
    </div>
  );
}

export function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-ink-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </Card>
  );
}

const SEVERITY_STYLES: Record<string, string> = {
  low: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  medium: "bg-amber-50 text-amber-700 ring-amber-600/20",
  high: "bg-orange-50 text-orange-700 ring-orange-600/20",
  critical: "bg-red-50 text-red-700 ring-red-600/20",
};

export function SeverityBadge({ severity, label }: { severity: string; label: string }) {
  const style = SEVERITY_STYLES[severity] ?? "bg-slate-100 text-slate-700 ring-slate-500/20";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${style}`}>
      {label}
    </span>
  );
}

const REVIEW_LABELS: Record<string, string> = {
  pending: "Beklemede",
  confirmed: "Onaylandı",
  rejected: "Reddedildi",
  uncertain: "Belirsiz",
};

export function ReviewBadge({ status }: { status: string }) {
  const label = REVIEW_LABELS[status] ?? status;
  const style =
    status === "confirmed"
      ? "bg-emerald-50 text-emerald-700"
      : status === "rejected"
        ? "bg-slate-100 text-slate-600"
        : status === "uncertain"
          ? "bg-amber-50 text-amber-700"
          : "bg-blue-50 text-blue-700";
  return <span className={`rounded-full px-2 py-0.5 text-xs ${style}`}>{label}</span>;
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
      {message}
    </div>
  );
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Istanbul",
  }).format(new Date(iso));
}
