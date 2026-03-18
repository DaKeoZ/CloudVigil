import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Retourne une version lisible "il y a Xs" à partir d'un timestamp ISO. */
export function timeAgo(ts: string): string {
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 5) return "à l'instant";
  if (diff < 60) return `il y a ${Math.round(diff)}s`;
  if (diff < 3600) return `il y a ${Math.round(diff / 60)}min`;
  return `il y a ${Math.round(diff / 3600)}h`;
}

/** Formate une valeur float en pourcentage avec 1 décimale. */
export function formatPct(v: number): string {
  return `${v.toFixed(1)}%`;
}

/** Formate un timestamp ISO en HH:MM:SS. */
export function formatTime(ts: string): string {
  return new Date(ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Retourne la couleur de statut selon le pourcentage (bas → vert, haut → rouge). */
export function thresholdColor(value: number): string {
  if (value >= 90) return "#ef4444"; // red-500
  if (value >= 75) return "#f97316"; // orange-500
  return undefined as unknown as string; // garde la couleur par défaut
}
