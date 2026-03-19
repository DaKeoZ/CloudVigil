"use client";

import { CheckCircle2, XCircle, RefreshCw, Wrench } from "lucide-react";
import { useRepairs } from "@/hooks/useRepairs";
import type { RepairEvent } from "@/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatRelativeTime(isoString: string): string {
  const delta = Date.now() - new Date(isoString).getTime();
  const s = Math.floor(delta / 1000);
  if (s < 60)  return `il y a ${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `il y a ${m}min`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `il y a ${h}h`;
  return `il y a ${Math.floor(h / 24)}j`;
}

function formatTimestamp(isoString: string): string {
  return new Date(isoString).toLocaleString("fr-FR", {
    day:    "2-digit",
    month:  "2-digit",
    year:   "numeric",
    hour:   "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// ── Sous-composants ───────────────────────────────────────────────────────────

function StatusBadge({ success }: { success: boolean }) {
  return success ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-400 ring-1 ring-inset ring-emerald-500/20">
      <CheckCircle2 className="h-3 w-3" />
      Réussi
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-[11px] font-medium text-red-400 ring-1 ring-inset ring-red-500/20">
      <XCircle className="h-3 w-3" />
      Échoué
    </span>
  );
}

function EventRow({ event }: { event: RepairEvent }) {
  return (
    <tr className="border-b border-slate-800/60 hover:bg-slate-800/30 transition-colors">
      <td className="px-4 py-3 whitespace-nowrap">
        <div className="text-xs font-mono text-slate-300">
          {formatTimestamp(event.timestamp)}
        </div>
        <div className="text-[10px] text-slate-600 mt-0.5">
          {formatRelativeTime(event.timestamp)}
        </div>
      </td>
      <td className="px-4 py-3">
        <span className="font-mono text-xs text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">
          {event.node_id}
        </span>
      </td>
      <td className="px-4 py-3">
        <div className="text-xs text-slate-200 font-medium">{event.container_name}</div>
        <div className="text-[10px] font-mono text-slate-600 mt-0.5">{event.container_id}</div>
      </td>
      <td className="px-4 py-3">
        <span className="text-xs font-mono text-slate-400 uppercase tracking-wide">
          {event.action}
        </span>
      </td>
      <td className="px-4 py-3">
        <StatusBadge success={event.success} />
      </td>
      <td className="px-4 py-3 max-w-xs">
        <span className="text-xs text-slate-500 line-clamp-2" title={event.message}>
          {event.message || "—"}
        </span>
      </td>
    </tr>
  );
}

// ── Composant principal ───────────────────────────────────────────────────────

interface RepairHistoryProps {
  /** Fenêtre temporelle en minutes (défaut : 1440 = 24 h) */
  minutes?: number;
}

export function RepairHistory({ minutes = 1440 }: RepairHistoryProps) {
  const { data, error, isLoading, isValidating } = useRepairs(minutes);

  return (
    <section className="rounded-xl border border-slate-800/80 bg-slate-900/60 overflow-hidden">

      {/* En-tête */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800/80">
        <div className="flex items-center gap-2">
          <Wrench className="h-4 w-4 text-amber-400" />
          <h2 className="text-sm font-semibold text-slate-200">
            Incidents résolus automatiquement
          </h2>
          {data && data.total > 0 && (
            <span className="ml-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-400 ring-1 ring-inset ring-amber-500/20">
              {data.total}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-600">
          {isValidating && (
            <RefreshCw className="h-3 w-3 animate-spin text-slate-500" />
          )}
          <span>
            {minutes >= 1440 ? "24 dernières heures" : `${minutes} dernières minutes`}
          </span>
        </div>
      </div>

      {/* Corps */}
      {isLoading && (
        <div className="flex items-center justify-center py-12 text-sm text-slate-600">
          <RefreshCw className="h-4 w-4 animate-spin mr-2" />
          Chargement…
        </div>
      )}

      {error && !isLoading && (
        <div className="flex items-center justify-center py-10 text-sm text-red-500">
          <XCircle className="h-4 w-4 mr-2" />
          Impossible de charger l&apos;historique
        </div>
      )}

      {!isLoading && !error && data && data.total === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-slate-600">
          <CheckCircle2 className="h-8 w-8 mb-3 text-slate-700" />
          <p className="text-sm">Aucun incident dans la période sélectionnée</p>
          <p className="text-xs mt-1 text-slate-700">Les réparations automatiques apparaîtront ici</p>
        </div>
      )}

      {!isLoading && !error && data && data.total > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-900/80">
                <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-slate-500">Date</th>
                <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-slate-500">Nœud</th>
                <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-slate-500">Conteneur</th>
                <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-slate-500">Action</th>
                <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-slate-500">Résultat</th>
                <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-slate-500">Message</th>
              </tr>
            </thead>
            <tbody>
              {data.events.map((event, i) => (
                <EventRow key={`${event.timestamp}-${i}`} event={event} />
              ))}
            </tbody>
          </table>
        </div>
      )}

    </section>
  );
}
