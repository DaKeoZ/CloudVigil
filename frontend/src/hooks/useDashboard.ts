"use client";

import useSWR from "swr";
import type { DashboardData } from "@/types";
import { clearStoredToken, getStoredToken } from "@/hooks/useAuth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const fetcher = async (url: string): Promise<DashboardData> => {
  const token = getStoredToken();

  const res = await fetch(url, {
    cache: "no-store",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  // Session expirée → déconnexion automatique
  if (res.status === 401) {
    clearStoredToken();
    window.location.replace("/login");
    throw new Error("Session expirée. Reconnexion requise.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`[${res.status}] ${text}`);
  }

  return res.json();
};

/**
 * Hook SWR qui interroge GET /dashboard toutes les 5 secondes.
 * Retourne les données de tous les nœuds avec historique + conteneurs.
 * Redirige automatiquement vers /login en cas de token invalide/expiré.
 */
export function useDashboard() {
  return useSWR<DashboardData>(`${API_URL}/dashboard`, fetcher, {
    refreshInterval:      5_000,
    revalidateOnFocus:    true,
    revalidateOnReconnect: true,
    errorRetryCount:      3,
    errorRetryInterval:   3_000,
    keepPreviousData:     true,
  });
}
