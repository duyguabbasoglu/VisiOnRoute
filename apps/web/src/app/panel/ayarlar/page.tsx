"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Card, PageHeader } from "@/components/ui";

interface Organization {
  id: string;
  name: string;
  slug: string;
  status: string;
  timezone: string;
  currency: string;
}

interface Member {
  membership_id: string;
  email: string;
  full_name: string;
  role: string;
  role_label: string;
  status: string;
}

export default function SettingsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("analyst");
  const [inviteToken, setInviteToken] = useState<string | null>(null);

  const org = useQuery({
    queryKey: ["organization"],
    queryFn: () => apiFetch<Organization>("/api/v1/organizations/current"),
  });
  const members = useQuery({
    queryKey: ["members"],
    queryFn: () => apiFetch<Member[]>("/api/v1/organizations/current/members"),
  });

  useEffect(() => {
    if (org.data) setName(org.data.name);
  }, [org.data]);

  const save = useMutation({
    mutationFn: () =>
      apiFetch<Organization>("/api/v1/organizations/current", {
        method: "PATCH",
        body: { name },
      }),
    onSuccess: () => {
      setMessage("Kaydedildi.");
      void queryClient.invalidateQueries({ queryKey: ["organization"] });
    },
    onError: (err) =>
      setMessage(err instanceof ApiError ? err.message : "Kaydedilemedi."),
  });

  const invite = useMutation({
    mutationFn: () =>
      apiFetch<{ invitation_token: string }>(
        "/api/v1/organizations/current/invitations",
        { method: "POST", body: { email: inviteEmail, role: inviteRole } },
      ),
    onSuccess: (data) => {
      setInviteToken(data.invitation_token);
      setInviteEmail("");
    },
  });

  const canManage = user?.role === "owner" || user?.role === "admin";

  return (
    <div>
      <PageHeader title="Ayarlar" description="Organizasyon ve kullanıcı ayarları." />

      <Card className="mb-6">
        <h2 className="mb-3 text-sm font-semibold text-ink-900">Organizasyon</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-slate-500">Ad</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={!canManage}
              className="mt-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:bg-slate-50"
            />
          </div>
          {canManage && (
            <button
              onClick={() => save.mutate()}
              disabled={save.isPending}
              className="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
            >
              Kaydet
            </button>
          )}
          {message && <p className="text-sm text-slate-600">{message}</p>}
        </div>
        {org.data && (
          <p className="mt-2 text-xs text-slate-400">
            Saat dilimi: {org.data.timezone} · Para birimi: {org.data.currency}
          </p>
        )}
      </Card>

      {canManage && (
        <Card className="mb-6">
          <h2 className="mb-3 text-sm font-semibold text-ink-900">Kullanıcı davet et</h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              invite.mutate();
            }}
            className="flex flex-wrap items-end gap-3"
          >
            <div>
              <label className="block text-xs text-slate-500">E-posta</label>
              <input
                type="email"
                required
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="mt-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500">Rol</label>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="mt-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
              >
                <option value="admin">Organizasyon Yöneticisi</option>
                <option value="safety_manager">Güvenlik Müdürü</option>
                <option value="fleet_manager">Filo Yöneticisi</option>
                <option value="event_reviewer">Olay İnceleyici</option>
                <option value="analyst">Analist</option>
                <option value="auditor">Salt Okunur Denetçi</option>
              </select>
            </div>
            <button
              type="submit"
              disabled={invite.isPending}
              className="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
            >
              Davet oluştur
            </button>
          </form>
          {inviteToken && (
            <div className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
              <p className="font-medium">Davet bağlantısı jetonu (bir kez gösterilir):</p>
              <code className="mt-1 block break-all font-mono text-xs">{inviteToken}</code>
            </div>
          )}
        </Card>
      )}

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-ink-900">Kullanıcılar</h2>
        {members.data && members.data.length > 0 ? (
          <ul className="divide-y divide-slate-100">
            {members.data.map((m) => (
              <li key={m.membership_id} className="flex items-center justify-between py-2.5">
                <div>
                  <p className="text-sm text-ink-900">{m.full_name}</p>
                  <p className="text-xs text-slate-400">{m.email}</p>
                </div>
                <span className="text-xs text-slate-500">{m.role_label}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">Kullanıcı bulunamadı.</p>
        )}
      </Card>
    </div>
  );
}
