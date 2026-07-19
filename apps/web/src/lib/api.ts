/**
 * Typed API client for VISiOnRoute.
 *
 * The access token is held in memory only (never localStorage — see CLAUDE.md
 * security rules). The refresh token lives in an HttpOnly cookie and is used
 * transparently to mint new access tokens on 401.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
  }
}

interface ErrorEnvelope {
  error: { code: string; message: string; details?: unknown };
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ErrorEnvelope;
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

async function refreshAccessToken(): Promise<boolean> {
  const response = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) {
    return false;
  }
  const body = (await response.json()) as { access_token: string };
  accessToken = body.access_token;
  return true;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  retryOnUnauthorized?: boolean;
}

export async function apiFetch<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, retryOnUnauthorized = true } = options;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && retryOnUnauthorized && accessToken) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiFetch<T>(path, { ...options, retryOnUnauthorized: false });
    }
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
