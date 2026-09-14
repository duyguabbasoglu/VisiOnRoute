import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, onSessionExpired, refreshSession, setAccessToken } from "./api";

const user = {
  id: "u1",
  email: "a@ornek.example",
  full_name: "A B",
  organization_id: "o1",
  organization_name: "Org",
  role: "owner",
  role_label: "Organizasyon Sahibi",
  is_platform_admin: false,
  email_verified: true,
  mfa_enabled: false,
  mfa_required: false,
};

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("refreshSession", () => {
  beforeEach(() => setAccessToken(null));
  afterEach(() => vi.unstubAllGlobals());

  it("shares one in-flight refresh between concurrent callers", async () => {
    let calls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        calls += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return json(200, { access_token: "t2", token_type: "bearer", expires_in: 900, user });
      }),
    );
    const results = await Promise.all([refreshSession(), refreshSession(), refreshSession()]);
    expect(calls).toBe(1);
    expect(results.every((r) => r?.access_token === "t2")).toBe(true);
  });

  it("parallel 401s trigger a single refresh and retry each request", async () => {
    setAccessToken("expired");
    let refreshCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit) => {
        if (url.endsWith("/auth/refresh")) {
          refreshCalls += 1;
          await new Promise((resolve) => setTimeout(resolve, 10));
          return json(200, { access_token: "fresh", token_type: "bearer", expires_in: 900, user });
        }
        const auth = (init.headers as Record<string, string>).Authorization;
        return auth === "Bearer fresh" ? json(200, { ok: true }) : json(401, { error: { code: "UNAUTHORIZED", message: "x" } });
      }),
    );
    const results = await Promise.all([apiFetch("/a"), apiFetch("/b"), apiFetch("/c")]);
    expect(refreshCalls).toBe(1);
    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }]);
  });

  it("notifies session expiry when refresh fails", async () => {
    setAccessToken("expired");
    vi.stubGlobal("fetch", vi.fn(async () => json(401, { error: { code: "UNAUTHORIZED", message: "Kimlik doğrulaması gerekli." } })));
    const listener = vi.fn();
    const unsubscribe = onSessionExpired(listener);
    await expect(apiFetch("/x")).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledOnce();
    unsubscribe();
  });
});

describe("apiFetch errors", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("maps network failures to a safe Turkish message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(apiFetch("/x")).rejects.toMatchObject({ code: "NETWORK_ERROR", message: expect.stringContaining("Sunucuya ulaşılamadı") });
  });

  it("rejects responses that do not match the schema", async () => {
    const { sessionUserSchema } = await import("./schemas");
    vi.stubGlobal("fetch", vi.fn(async () => json(200, { id: 1 })));
    await expect(apiFetch("/x", { schema: sessionUserSchema })).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("uses the backend Turkish error message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(409, { error: { code: "CONFLICT", message: "Bu kısa ad zaten kullanımda." } })));
    await expect(apiFetch("/x", { method: "POST", body: {} })).rejects.toMatchObject({ status: 409, message: "Bu kısa ad zaten kullanımda." });
  });
});
