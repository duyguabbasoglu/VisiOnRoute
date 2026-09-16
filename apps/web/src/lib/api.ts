/**
 * Typed API client for VISiOnRoute.
 *
 * - The access token lives in memory only (never localStorage). The refresh
 *   token is an HttpOnly cookie used to mint new access tokens.
 * - Refresh is single-flight: the backend treats reuse of a rotated refresh
 *   token as theft and revokes the whole session family, so two concurrent
 *   refresh calls (parallel 401s, React StrictMode double effects) would log
 *   the user out. All callers share one in-flight refresh.
 * - Responses are validated with Zod when a schema is given; failures surface
 *   as safe Turkish messages, never raw exceptions.
 */
import type { ZodType } from "zod";
import { authResponseSchema, type AuthResponse } from "./schemas";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const NETWORK_MESSAGE =
  "Sunucuya ulaşılamadı. İnternet bağlantınızı kontrol edip tekrar deneyin.";
const INVALID_RESPONSE_MESSAGE =
  "Sunucudan beklenmeyen bir yanıt alındı. Sayfayı yenileyip tekrar deneyin.";

let accessToken: string | null = null;
let refreshInFlight: Promise<AuthResponse | null> | null = null;
const sessionExpiredListeners = new Set<() => void>();

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function onSessionExpired(listener: () => void): () => void {
  sessionExpiredListeners.add(listener);
  return () => sessionExpiredListeners.delete(listener);
}

/**
 * Free-tier hosts put idle servers to sleep; the first request then takes up
 * to a minute. Slow requests flip a "slow" status the UI can explain, and
 * idempotent GETs are retried on gateway errors while the server starts.
 */
export type ServiceStatus = "ok" | "slow";
const SLOW_AFTER_MS = 4_000;
const RETRYABLE_STATUS = new Set([502, 503, 504]);
let retryDelaysMs: number[] = [2_000, 4_000, 8_000, 15_000];
let slowRequests = 0;
const serviceListeners = new Set<(status: ServiceStatus) => void>();

export function onServiceStatus(listener: (status: ServiceStatus) => void): () => void {
  serviceListeners.add(listener);
  if (slowRequests > 0) listener("slow");
  return () => {
    serviceListeners.delete(listener);
  };
}

/** Test hook: shorten or disable GET retry back-off. */
export function setRetryDelays(delays: number[]): void {
  retryDelaysMs = delays;
}

async function tracked<T>(work: () => Promise<T>): Promise<T> {
  let slow = false;
  const timer = setTimeout(() => {
    slow = true;
    slowRequests += 1;
    if (slowRequests === 1) serviceListeners.forEach((listener) => listener("slow"));
  }, SLOW_AFTER_MS);
  try {
    return await work();
  } finally {
    clearTimeout(timer);
    if (slow) {
      slowRequests -= 1;
      if (slowRequests === 0) serviceListeners.forEach((listener) => listener("ok"));
    }
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Safe, user-facing message for any thrown value. */
export function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string; details?: unknown };
    };
    return new ApiError(
      response.status,
      body.error?.code ?? "HTTP_ERROR",
      body.error?.message ?? "İstek işlenemedi.",
      body.error?.details,
    );
  } catch {
    return new ApiError(response.status, "HTTP_ERROR", "İstek işlenemedi.");
  }
}

/** Exchange the refresh cookie for a new session; shared by concurrent callers. */
export function refreshSession(): Promise<AuthResponse | null> {
  if (refreshInFlight === null) {
    refreshInFlight = (async () => {
      try {
        const response = await tracked(() =>
          fetch(`${API_BASE}/api/v1/auth/refresh`, {
            method: "POST",
            credentials: "include",
          }),
        );
        if (!response.ok) return null;
        const parsed = authResponseSchema.safeParse(await response.json());
        if (!parsed.success) return null;
        accessToken = parsed.data.access_token;
        return parsed.data;
      } catch {
        return null;
      }
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

interface RequestOptions<T> {
  method?: string;
  body?: unknown;
  schema?: ZodType<T>;
  retryOnUnauthorized?: boolean;
  signal?: AbortSignal;
}

async function send(path: string, method: string, body: unknown, signal?: AbortSignal) {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  return tracked(async () => {
    for (let attempt = 0; ; attempt += 1) {
      // Only GETs are retried: repeating a write could apply it twice.
      const delay = method === "GET" ? retryDelaysMs[attempt] : undefined;
      try {
        const response = await fetch(`${API_BASE}${path}`, {
          method,
          headers,
          credentials: "include",
          body: body === undefined ? undefined : JSON.stringify(body),
          signal,
        });
        if (delay !== undefined && RETRYABLE_STATUS.has(response.status)) {
          await sleep(delay);
          continue;
        }
        return response;
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") throw err;
        if (delay !== undefined && !signal?.aborted) {
          await sleep(delay);
          continue;
        }
        throw new ApiError(0, "NETWORK_ERROR", NETWORK_MESSAGE);
      }
    }
  });
}

async function authorizedResponse(
  path: string,
  method: string,
  body: unknown,
  retryOnUnauthorized: boolean,
  signal?: AbortSignal,
): Promise<Response> {
  const hadToken = accessToken !== null;
  const response = await send(path, method, body, signal);
  if (response.status === 401 && retryOnUnauthorized && hadToken) {
    if (await refreshSession()) {
      return send(path, method, body, signal);
    }
    accessToken = null;
    sessionExpiredListeners.forEach((listener) => listener());
  }
  return response;
}

export async function apiFetch<T>(path: string, options: RequestOptions<T> = {}): Promise<T> {
  const { method = "GET", body, schema, retryOnUnauthorized = true, signal } = options;
  const response = await authorizedResponse(path, method, body, retryOnUnauthorized, signal);
  if (!response.ok) throw await parseError(response);
  if (response.status === 204 || response.status === 205) return undefined as T;
  let json: unknown;
  try {
    json = await response.json();
  } catch {
    throw new ApiError(response.status, "INVALID_RESPONSE", INVALID_RESPONSE_MESSAGE);
  }
  if (!schema) return json as T;
  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    throw new ApiError(response.status, "INVALID_RESPONSE", INVALID_RESPONSE_MESSAGE);
  }
  return parsed.data;
}

/** Download an authenticated file (CSV/PDF/ZIP) and save it via the browser. */
export async function apiDownload(path: string, fallbackFilename: string): Promise<void> {
  const response = await authorizedResponse(path, "GET", undefined, true);
  if (!response.ok) throw await parseError(response);
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = match?.[1] ?? fallbackFilename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

/** Open a long-lived authenticated response (server-sent events). The access
 * token travels in the Authorization header, never in the URL. */
export function openAuthorizedStream(path: string, signal: AbortSignal): Promise<Response> {
  return authorizedResponse(path, "GET", undefined, true, signal);
}
