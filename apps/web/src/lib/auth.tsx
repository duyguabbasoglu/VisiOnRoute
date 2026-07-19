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
import { apiFetch, setAccessToken } from "./api";
import type { AuthResponse, SessionUser } from "./types";

interface AuthState {
  user: SessionUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  // On mount, try to restore a session via the HttpOnly refresh cookie.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const auth = await apiFetch<AuthResponse>("/api/v1/auth/refresh", {
          method: "POST",
          retryOnUnauthorized: false,
        });
        setAccessToken(auth.access_token);
        if (!cancelled) setUser(auth.user);
      } catch {
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const auth = await apiFetch<AuthResponse>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
      retryOnUnauthorized: false,
    });
    setAccessToken(auth.access_token);
    setUser(auth.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiFetch("/api/v1/auth/logout", { method: "POST", retryOnUnauthorized: false });
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
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
