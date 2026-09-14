"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { apiFetch, onSessionExpired, refreshSession, setAccessToken } from "./api";
import {
  authResponseSchema,
  loginResponseSchema,
  sessionUserSchema,
  type SessionUser,
} from "./schemas";

export type LoginResult =
  | { status: "authenticated" }
  | { status: "mfa_required"; mfaToken: string };

export interface RegisterInput {
  organization_name: string;
  slug: string;
  email: string;
  full_name: string;
  password: string;
}

interface AuthState {
  user: SessionUser | null;
  loading: boolean;
  sessionExpired: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  verifyMfa: (mfaToken: string, input: { code?: string; recoveryCode?: string }) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  refreshUser: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);

  // Restore a session from the HttpOnly refresh cookie (single-flight refresh).
  useEffect(() => {
    let cancelled = false;
    void refreshSession().then((auth) => {
      if (cancelled) return;
      setUser(auth?.user ?? null);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(
    () =>
      onSessionExpired(() => {
        setUser(null);
        setSessionExpired(true);
      }),
    [],
  );

  const login = useCallback(async (email: string, password: string): Promise<LoginResult> => {
    const result = await apiFetch("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
      schema: loginResponseSchema,
      retryOnUnauthorized: false,
    });
    if ("mfa_token" in result) {
      return { status: "mfa_required", mfaToken: result.mfa_token };
    }
    setAccessToken(result.access_token);
    setSessionExpired(false);
    setUser(result.user);
    return { status: "authenticated" };
  }, []);

  const verifyMfa = useCallback(
    async (mfaToken: string, input: { code?: string; recoveryCode?: string }) => {
      const auth = await apiFetch("/api/v1/auth/mfa/verify", {
        method: "POST",
        body: {
          mfa_token: mfaToken,
          code: input.code || null,
          recovery_code: input.recoveryCode || null,
        },
        schema: authResponseSchema,
        retryOnUnauthorized: false,
      });
      setAccessToken(auth.access_token);
      setSessionExpired(false);
      setUser(auth.user);
    },
    [],
  );

  const register = useCallback(async (input: RegisterInput) => {
    const auth = await apiFetch("/api/v1/auth/register", {
      method: "POST",
      body: input,
      schema: authResponseSchema,
      retryOnUnauthorized: false,
    });
    setAccessToken(auth.access_token);
    setSessionExpired(false);
    setUser(auth.user);
  }, []);

  const refreshUser = useCallback(async () => {
    const me = await apiFetch("/api/v1/auth/me", { schema: sessionUserSchema });
    setUser(me);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiFetch("/api/v1/auth/logout", { method: "POST", retryOnUnauthorized: false });
    } catch {
      // Local sign-out must succeed even if the server is unreachable.
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, sessionExpired, login, verifyMfa, register, refreshUser, logout }),
    [user, loading, sessionExpired, login, verifyMfa, register, refreshUser, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth AuthProvider içinde kullanılmalıdır.");
  }
  return ctx;
}
