"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API_URL   = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "cloudvigil_token";

// ── Helpers localStorage (côté client uniquement) ─────────────────────────────

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function clearStoredToken(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
  }
}

// ── Hook principal ────────────────────────────────────────────────────────────

export interface AuthState {
  token:     string | null;
  username:  string | null;
  isLoading: boolean;
  error:     string | null;
  login:     (username: string, password: string) => Promise<void>;
  logout:    () => void;
}

export function useAuth(): AuthState {
  const [token,     setToken]     = useState<string | null>(null);
  const [username,  setUsername]  = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const router = useRouter();

  // Recharger le token au montage (hydrater depuis localStorage)
  useEffect(() => {
    const stored = getStoredToken();
    if (stored) {
      setToken(stored);
      setUsername(_extractUsername(stored));
    }
  }, []);

  const login = useCallback(
    async (user: string, password: string) => {
      setIsLoading(true);
      setError(null);
      try {
        // OAuth2 Password Flow : application/x-www-form-urlencoded
        const body = new URLSearchParams({ username: user, password });
        const res = await fetch(`${API_URL}/auth/token`, {
          method:  "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body:    body.toString(),
        });

        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail ?? "Identifiants incorrects.");
        }

        const data: { access_token: string } = await res.json();
        localStorage.setItem(TOKEN_KEY, data.access_token);
        setToken(data.access_token);
        setUsername(user);
        router.push("/");
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Erreur de connexion.";
        setError(msg);
      } finally {
        setIsLoading(false);
      }
    },
    [router],
  );

  const logout = useCallback(() => {
    clearStoredToken();
    setToken(null);
    setUsername(null);
    router.push("/login");
  }, [router]);

  return { token, username, isLoading, error, login, logout };
}

// ── Utilitaire : extraire le username du payload JWT ─────────────────────────

function _extractUsername(token: string): string | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.sub ?? null;
  } catch {
    return null;
  }
}
