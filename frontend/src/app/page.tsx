import { Activity, RefreshCw } from "lucide-react";
import { NodeGrid } from "@/components/NodeGrid";
import { NetworkHealth } from "@/components/NetworkHealth";
import { RepairHistory } from "@/components/RepairHistory";
import { AuthGuard } from "@/components/AuthGuard";
import { LogoutButton } from "@/components/LogoutButton";

export default function DashboardPage() {
  return (
    <AuthGuard>
      <div className="min-h-screen bg-slate-950">

        {/* ── Navigation ──────────────────────────────────────────────────────── */}
        <header className="sticky top-0 z-50 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">

              {/* Logo */}
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 shadow-lg shadow-blue-600/20">
                  <Activity className="h-4 w-4 text-white" />
                </div>
                <div>
                  <span className="font-bold text-base tracking-tight text-slate-100">
                    CloudVigil
                  </span>
                  <span className="hidden sm:inline text-slate-600 text-sm ml-2">
                    / Tableau de bord
                  </span>
                </div>
              </div>

              {/* Actions droite */}
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <RefreshCw className="h-3 w-3 animate-spin-slow" />
                  <span className="hidden sm:inline">Auto-refresh</span>
                  <span className="font-mono text-slate-400">5s</span>
                </div>
                <LogoutButton />
              </div>

            </div>
          </div>
        </header>

        {/* ── Contenu principal ────────────────────────────────────────────────── */}
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

          <div className="mb-8">
            <h1 className="text-2xl font-bold text-slate-100 tracking-tight">
              Serveurs monitorés
            </h1>
            <p className="text-slate-500 text-sm mt-1">
              Métriques système en temps réel · rafraîchissement automatique toutes les 5 secondes
            </p>
          </div>

          <NodeGrid />

          {/* ── Network Health ──────────────────────────────────────────────────── */}
          <div className="mt-10">
            <div className="mb-4">
              <h2 className="text-lg font-semibold text-slate-200 tracking-tight">
                Network Health
              </h2>
              <p className="text-slate-500 text-sm mt-1">
                Disponibilité et latence des services externes · certificats SSL · mise à jour toutes les 60s
              </p>
            </div>
            <NetworkHealth />
          </div>

          {/* ── Auto-réparation ────────────────────────────────────────────────── */}
          <div className="mt-10">
            <div className="mb-4">
              <h2 className="text-lg font-semibold text-slate-200 tracking-tight">
                Auto-réparation
              </h2>
              <p className="text-slate-500 text-sm mt-1">
                Historique des redémarrages automatiques déclenchés par le Master · mise à jour toutes les 30s
              </p>
            </div>
            <RepairHistory minutes={1440} />
          </div>

        </main>

        {/* ── Pied de page ────────────────────────────────────────────────────── */}
        <footer className="border-t border-slate-800/50 mt-12 py-6">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <p className="text-center text-xs text-slate-700">
              CloudVigil — données stockées dans InfluxDB · gRPC mTLS · JWT
            </p>
          </div>
        </footer>

      </div>
    </AuthGuard>
  );
}
