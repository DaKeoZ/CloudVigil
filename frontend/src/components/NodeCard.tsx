"use client";

import { useState } from "react";
import { Server, Container, Clock, Terminal } from "lucide-react";
import { Card, CardHeader, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MetricGauge } from "@/components/MetricGauge";
import { MetricSparkline } from "@/components/MetricSparkline";
import { LogConsole } from "@/components/LogConsole";
import { timeAgo } from "@/lib/utils";
import type { ContainerSummary, NodeSummary } from "@/types";

interface NodeCardProps {
  node: NodeSummary;
}

export function NodeCard({ node }: NodeCardProps) {
  const { node_id, status, latest, history, containers, container_count } = node;

  const isOnline = status === "online";
  const cpu  = latest?.cpu_usage  ?? 0;
  const ram  = latest?.ram_usage  ?? 0;
  const disk = latest?.disk_usage ?? 0;
  const lastTs = latest?.timestamp;

  const runningCount = containers.filter((c) => c.state === "running").length;

  // ── Log Viewer ─────────────────────────────────────────────────────────────
  const [activeContainer, setActiveContainer] = useState<ContainerSummary | null>(null);

  return (
    <>
      <Card className="flex flex-col hover:border-slate-700 transition-colors duration-200">

        {/* ── En-tête ─────────────────────────────────────────────────────── */}
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <div className={`shrink-0 rounded-md p-1.5 ${isOnline ? "bg-blue-500/10" : "bg-slate-800"}`}>
                <Server className={`h-3.5 w-3.5 ${isOnline ? "text-blue-400" : "text-slate-600"}`} />
              </div>
              <span
                className="font-mono text-sm font-semibold text-slate-200 truncate"
                title={node_id}
              >
                {node_id}
              </span>
            </div>
            <Badge variant={isOnline ? "online" : "offline"} className="shrink-0">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isOnline ? "bg-emerald-400 animate-pulse" : "bg-slate-500"
                }`}
              />
              {isOnline ? "En ligne" : "Hors ligne"}
            </Badge>
          </div>

          {lastTs && (
            <p className="flex items-center gap-1 text-xs text-slate-600 mt-1.5 pl-0.5">
              <Clock className="h-3 w-3" />
              Mis à jour {timeAgo(lastTs)}
            </p>
          )}
        </CardHeader>

        {/* ── Jauges CPU / RAM / Disque ────────────────────────────────────── */}
        <CardContent>
          <div className="grid grid-cols-3 gap-1 mb-1">
            <MetricGauge value={cpu}  label="CPU"    baseColor="#3b82f6" />
            <MetricGauge value={ram}  label="RAM"    baseColor="#a855f7" />
            <MetricGauge value={disk} label="DISQUE" baseColor="#f59e0b" />
          </div>

          {history.length >= 2 && (
            <div className="mt-4 space-y-3">
              <div>
                <p className="text-[11px] text-slate-500 mb-1 flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-sm bg-blue-500/60" />
                  CPU — 10 dernières minutes
                </p>
                <MetricSparkline data={history} metric="cpu_usage" color="blue" label="CPU %" />
              </div>
              <div>
                <p className="text-[11px] text-slate-500 mb-1 flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-sm bg-violet-500/60" />
                  RAM — 10 dernières minutes
                </p>
                <MetricSparkline data={history} metric="ram_usage" color="violet" label="RAM %" />
              </div>
            </div>
          )}
        </CardContent>

        {/* ── Pied de page Docker ─────────────────────────────────────────── */}
        {container_count > 0 && (
          <CardFooter className="border-t border-slate-800/80 pt-3 flex-col items-start gap-2">

            {/* Compteurs */}
            <div className="flex items-center gap-3 text-xs text-slate-500 w-full">
              <div className="flex items-center gap-1.5">
                <Container className="h-3.5 w-3.5 text-slate-600" />
                <span>{container_count} conteneur{container_count > 1 ? "s" : ""}</span>
              </div>
              <span className="text-slate-700">·</span>
              <span className="text-emerald-500 font-medium">
                {runningCount} actif{runningCount > 1 ? "s" : ""}
              </span>
              {container_count - runningCount > 0 && (
                <>
                  <span className="text-slate-700">·</span>
                  <span>{container_count - runningCount} arrêté{container_count - runningCount > 1 ? "s" : ""}</span>
                </>
              )}
            </div>

            {/* Liste des conteneurs cliquables */}
            <ul className="w-full space-y-1">
              {containers.map((c) => (
                <ContainerRow
                  key={c.id}
                  container={c}
                  onClick={() => setActiveContainer(c)}
                />
              ))}
            </ul>

          </CardFooter>
        )}
      </Card>

      {/* ── Overlay Log Viewer ──────────────────────────────────────────────── */}
      {activeContainer && (
        <LogConsole
          nodeId={node_id}
          containerId={activeContainer.id}
          containerName={activeContainer.name}
          onClose={() => setActiveContainer(null)}
        />
      )}
    </>
  );
}

// ── Sous-composant : ligne de conteneur ───────────────────────────────────────

function ContainerRow({
  container,
  onClick,
}: {
  container: ContainerSummary;
  onClick:   () => void;
}) {
  const isRunning = container.state === "running";

  return (
    <li>
      <button
        onClick={onClick}
        className="group w-full flex items-center justify-between gap-2 px-2.5 py-1.5
                   rounded-lg border border-transparent hover:border-slate-700
                   hover:bg-slate-800/60 transition-all text-left"
        title={`Voir les logs de ${container.name}`}
      >
        {/* Icône état + nom */}
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`shrink-0 h-1.5 w-1.5 rounded-full ${
              isRunning ? "bg-emerald-400" : "bg-slate-600"
            }`}
          />
          <span className="font-mono text-[11px] text-slate-300 truncate">
            {container.name.replace(/^\//, "")}
          </span>
        </div>

        {/* Métriques + icône terminal */}
        <div className="flex items-center gap-2.5 shrink-0">
          {isRunning && (
            <span className="text-[10px] text-slate-500">
              {container.cpu_percent.toFixed(1)}%
              <span className="text-slate-700 mx-1">·</span>
              {container.mem_usage_mb.toFixed(0)} Mo
            </span>
          )}
          {!isRunning && (
            <span className="text-[10px] text-slate-600 italic">{container.state}</span>
          )}
          <Terminal
            className="h-3 w-3 text-slate-600 group-hover:text-blue-400 transition-colors"
          />
        </div>
      </button>
    </li>
  );
}
