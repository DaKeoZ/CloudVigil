"use client";

import { Globe, Lock, RefreshCw, Wifi, WifiOff, AlertTriangle, CheckCircle2 } from "lucide-react";
import { useNetwork } from "@/hooks/useNetwork";
import type { NetworkTarget, SslStatus } from "@/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatLatency(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000)   return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "—";
  const delta = Date.now() - new Date(iso).getTime();
  const s = Math.floor(delta / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}min`;
  return `${Math.floor(m / 60)}h`;
}

// ── Micro-sparkline SVG ───────────────────────────────────────────────────────

function LatencySparkline({ points }: { points: { latency_ms: number | null; up: boolean }[] }) {
  const valid = points.filter((p) => p.latency_ms !== null && p.up);
  if (valid.length < 2) {
    return <div className="h-8 w-full" />;
  }

  const vals  = valid.map((p) => p.latency_ms as number);
  const min   = Math.min(...vals);
  const max   = Math.max(...vals);
  const range = Math.max(max - min, 1);

  const W = 120, H = 28, pad = 2;
  const step = (W - pad * 2) / (valid.length - 1);

  const pts = valid
    .map((p, i) => {
      const x = pad + i * step;
      const y = H - pad - ((p.latency_ms as number - min) / range) * (H - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg width={W} height={H} className="overflow-visible">
      <polyline
        points={pts}
        fill="none"
        stroke="#3b82f6"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity="0.7"
      />
    </svg>
  );
}

// ── Badge SSL ─────────────────────────────────────────────────────────────────

const SSL_BADGE: Record<SslStatus, { label: string; cls: string }> = {
  ok:       { label: "SSL OK",    cls: "text-emerald-400 bg-emerald-500/10 ring-emerald-500/20" },
  warning:  { label: "SSL ⚠",    cls: "text-amber-400  bg-amber-500/10  ring-amber-500/20"  },
  critical: { label: "SSL !",     cls: "text-red-400    bg-red-500/10    ring-red-500/20"    },
  expired:  { label: "SSL exp.", cls: "text-red-500    bg-red-500/15    ring-red-600/30"    },
  na:       { label: "No SSL",   cls: "text-slate-600  bg-slate-800     ring-slate-700/50"  },
};

function SslBadge({ status, days }: { status: SslStatus; days: number | null }) {
  const b = SSL_BADGE[status] ?? SSL_BADGE.na;
  const label = days !== null && days >= 0 ? `${days}j` : b.label;
  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${b.cls}`}
      title={`Certificat SSL : ${b.label}${days !== null ? ` (${days} jours restants)` : ""}`}
    >
      <Lock className="h-2.5 w-2.5" />
      {label}
    </span>
  );
}

// ── Carte d'une cible ─────────────────────────────────────────────────────────

function TargetCard({ target }: { target: NetworkTarget }) {
  const isUp      = target.status === "up";
  const isPending = target.status === "pending";

  return (
    <div
      className={`
        relative flex flex-col gap-3 rounded-xl border p-4 transition-all
        ${isUp
          ? "border-slate-800/80 bg-slate-900/60"
          : isPending
            ? "border-slate-800/60 bg-slate-900/40"
            : "border-red-900/50 bg-red-950/20"
        }
      `}
    >
      {/* En-tête */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {/* Indicateur statut */}
            <span
              className={`
                inline-block h-2 w-2 flex-shrink-0 rounded-full
                ${isUp      ? "bg-emerald-400 shadow-[0_0_6px_#34d399]"
                : isPending ? "bg-slate-600 animate-pulse"
                :             "bg-red-500 shadow-[0_0_6px_#f87171] animate-pulse"}
              `}
            />
            <h3 className="truncate text-sm font-semibold text-slate-100">
              {target.name}
            </h3>
          </div>
          <p className="mt-0.5 truncate text-[11px] text-slate-600" title={target.url}>
            {target.url}
          </p>
        </div>

        {/* Badge statut */}
        {isUp ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-400 ring-1 ring-inset ring-emerald-500/20 flex-shrink-0">
            <CheckCircle2 className="h-3 w-3" />
            UP
          </span>
        ) : isPending ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-500 ring-1 ring-inset ring-slate-700">
            <RefreshCw className="h-3 w-3 animate-spin" />
            …
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-[11px] font-medium text-red-400 ring-1 ring-inset ring-red-500/20 flex-shrink-0">
            <WifiOff className="h-3 w-3" />
            DOWN
          </span>
        )}
      </div>

      {/* Métriques */}
      <div className="flex items-center gap-4">
        {/* Latence */}
        <div className="text-center">
          <div className={`text-base font-mono font-bold leading-none
            ${isUp ? "text-slate-100" : "text-slate-600"}`}>
            {formatLatency(target.latency_ms)}
          </div>
          <div className="mt-0.5 text-[9px] uppercase tracking-wider text-slate-600">Latence</div>
        </div>

        {/* Code HTTP */}
        {target.status_code !== null && (
          <div className="text-center">
            <div className={`text-base font-mono font-bold leading-none
              ${target.status_code < 400 ? "text-emerald-400" : "text-red-400"}`}>
              {target.status_code}
            </div>
            <div className="mt-0.5 text-[9px] uppercase tracking-wider text-slate-600">HTTP</div>
          </div>
        )}

        {/* Sparkline */}
        <div className="ml-auto flex-shrink-0 opacity-70">
          <LatencySparkline points={target.history} />
        </div>
      </div>

      {/* Pied : SSL + horodatage */}
      <div className="flex items-center justify-between border-t border-slate-800/60 pt-2">
        <SslBadge status={target.ssl_status} days={target.ssl_days_remaining} />
        <span className="text-[10px] text-slate-700">
          {target.last_checked
            ? `il y a ${formatRelativeTime(target.last_checked)}`
            : "pas encore sondé"}
        </span>
      </div>

      {/* Message d'erreur */}
      {!isUp && target.error && (
        <div className="flex items-start gap-1.5 rounded-lg bg-red-950/40 px-3 py-2 text-[11px] text-red-400">
          <AlertTriangle className="mt-0.5 h-3 w-3 flex-shrink-0" />
          <span className="line-clamp-2">{target.error}</span>
        </div>
      )}
    </div>
  );
}

// ── Composant principal ───────────────────────────────────────────────────────

export function NetworkHealth() {
  const { data, error, isLoading, isValidating } = useNetwork();

  // Résumé global
  const total    = data?.total    ?? 0;
  const upCount  = data?.up       ?? 0;
  const downCount = data?.down    ?? 0;
  const allUp    = total > 0 && downCount === 0;
  const hasDown  = downCount > 0;

  return (
    <section className="rounded-xl border border-slate-800/80 bg-slate-900/40 overflow-hidden">

      {/* En-tête */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800/80 bg-slate-900/60">
        <div className="flex items-center gap-3">
          <Globe className="h-4 w-4 text-blue-400" />
          <h2 className="text-sm font-semibold text-slate-200">Network Health</h2>

          {/* Résumé de santé */}
          {!isLoading && data && total > 0 && (
            <span className={`
              inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset
              ${allUp
                ? "bg-emerald-500/10 text-emerald-400 ring-emerald-500/20"
                : "bg-red-500/10 text-red-400 ring-red-500/20"}
            `}>
              {allUp ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
              {upCount}/{total} en ligne
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-600">
          {isValidating && <RefreshCw className="h-3 w-3 animate-spin text-slate-500" />}
          <span>Sonde toutes les 60s</span>
        </div>
      </div>

      {/* Corps */}
      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-600">
          <RefreshCw className="h-4 w-4 animate-spin" />
          Chargement…
        </div>
      )}

      {error && !isLoading && (
        <div className="flex items-center justify-center gap-2 py-10 text-sm text-red-500">
          <AlertTriangle className="h-4 w-4" />
          Impossible de charger les données réseau
        </div>
      )}

      {!isLoading && !error && data && !data.configured && (
        <div className="flex flex-col items-center justify-center py-12 text-slate-600">
          <Globe className="h-8 w-8 mb-3 text-slate-700" />
          <p className="text-sm">Sonde réseau non configurée</p>
          <p className="text-xs mt-1 text-slate-700">
            Ajouter des cibles dans <code className="text-slate-500">config/alerts.yaml</code>
          </p>
        </div>
      )}

      {!isLoading && !error && data && data.configured && data.targets.length > 0 && (
        <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {data.targets.map((target) => (
            <TargetCard key={target.url} target={target} />
          ))}
        </div>
      )}

      {/* Alerte globale si services down */}
      {!isLoading && hasDown && (
        <div className="border-t border-red-900/40 bg-red-950/20 px-5 py-3 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-red-500 flex-shrink-0" />
          <p className="text-xs text-red-400">
            <span className="font-semibold">{downCount} service(s) injoignable(s).</span>
            {" "}
            Vérifiez vos webhooks pour les alertes.
          </p>
        </div>
      )}

    </section>
  );
}
