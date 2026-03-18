"use client";

import { useDashboard } from "@/hooks/useDashboard";
import { NodeCard } from "@/components/NodeCard";
import { Skeleton } from "@/components/ui/skeleton";
import { WifiOff, Radio } from "lucide-react";

// ── Squelette de chargement ───────────────────────────────────────────────────

function NodeCardSkeleton() {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-36" />
        <Skeleton className="h-5 w-20 rounded-full" />
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-[72px] rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-14 rounded-lg" />
      <Skeleton className="h-14 rounded-lg" />
    </div>
  );
}

// ── État vide / erreur ────────────────────────────────────────────────────────

function EmptyState({ icon: Icon, title, subtitle }: {
  icon: React.ElementType;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="col-span-full flex flex-col items-center justify-center py-28 text-center">
      <div className="rounded-full bg-slate-800/80 p-5 mb-5">
        <Icon className="h-8 w-8 text-slate-500" />
      </div>
      <p className="text-slate-200 font-semibold text-lg">{title}</p>
      <p className="text-slate-500 text-sm mt-2 max-w-xs">{subtitle}</p>
    </div>
  );
}

// ── Barre de stats globale ────────────────────────────────────────────────────

function GlobalStats({ total, online }: { total: number; online: number }) {
  return (
    <div className="flex items-center gap-6 text-sm text-slate-500 mb-6">
      <span>
        <span className="text-slate-200 font-semibold">{total}</span> nœud{total > 1 ? "s" : ""}
      </span>
      <span className="text-slate-700">·</span>
      <span className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
        <span className="text-emerald-400 font-medium">{online}</span> en ligne
      </span>
      {total - online > 0 && (
        <>
          <span className="text-slate-700">·</span>
          <span>{total - online} hors ligne</span>
        </>
      )}
    </div>
  );
}

// ── Grille principale ─────────────────────────────────────────────────────────

export function NodeGrid() {
  const { data, error, isLoading } = useDashboard();

  if (error) {
    return (
      <div className="grid">
        <EmptyState
          icon={WifiOff}
          title="Serveur CloudVigil inaccessible"
          subtitle={`Vérifiez que le serveur FastAPI est démarré sur le port 8000. (${error.message})`}
        />
      </div>
    );
  }

  if (isLoading && !data) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <NodeCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (!data || data.nodes.length === 0) {
    return (
      <div className="grid">
        <EmptyState
          icon={Radio}
          title="Aucun agent connecté"
          subtitle="Démarrez un agent CloudVigil pour commencer à recevoir des métriques."
        />
      </div>
    );
  }

  const onlineCount = data.nodes.filter((n) => n.status === "online").length;

  return (
    <>
      <GlobalStats total={data.total} online={onlineCount} />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {data.nodes.map((node) => (
          <NodeCard key={node.node_id} node={node} />
        ))}
      </div>
    </>
  );
}
