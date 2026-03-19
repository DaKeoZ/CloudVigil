"use client";

import useSWR from "swr";
import type { RepairsData } from "@/types";
import { clearStoredToken, getStoredToken } from "@/hooks/useAuth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const fetcher = async (url: string): Promise<RepairsData> => {
  const token = getStoredToken();

  const res = await fetch(url, {
    cache: "no-store",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (res.status === 401) {
    clearStoredToken();
    window.location.replace("/login");
    throw new Error("Session expirée.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`[${res.status}] ${text}`);
  }

  return res.json();
};

/**
 * Hook SWR qui interroge GET /repairs toutes les 30 secondes.
 * Retourne l'historique des tentatives d'auto-réparation.
 */
export function useRepairs(minutes = 1440) {
  return useSWR<RepairsData>(
    `${API_URL}/repairs?minutes=${minutes}`,
    fetcher,
    {
      refreshInterval:       30_000,
      revalidateOnFocus:     true,
      revalidateOnReconnect: true,
      errorRetryCount:       3,
      errorRetryInterval:    5_000,
      keepPreviousData:      true,
    },
  );
}
