"use client";

import useSWR from "swr";
import type { DashboardData } from "@/types";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const fetcher = async (url: string): Promise<DashboardData> => {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`[${res.status}] ${text}`);
  }
  return res.json();
};

/**
 * Hook SWR qui interroge GET /dashboard toutes les 5 secondes.
 * Retourne les données de tous les nœuds avec historique + conteneurs.
 */
export function useDashboard() {
  return useSWR<DashboardData>(`${API_URL}/dashboard`, fetcher, {
    refreshInterval: 5_000,
    revalidateOnFocus: true,
    revalidateOnReconnect: true,
    errorRetryCount: 3,
    errorRetryInterval: 3_000,
    // Garder les données précédentes pendant le rechargement (pas de flash)
    keepPreviousData: true,
  });
}
