"use client";

/**
 * LogConsole — Terminal temps-réel affichant les logs d'un conteneur Docker.
 *
 * - Fond noir, texte vert (stdout) / rouge (stderr) façon terminal
 * - Connexion WebSocket au serveur CloudVigil via le hub ws_hub
 * - Auto-scroll vers le bas, avec pause si l'utilisateur remonte
 * - Bouton "Fermer" et indicateur de statut de connexion
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { X, Terminal, Wifi, WifiOff, Loader } from "lucide-react";
import { getStoredToken } from "@/hooks/useAuth";

// ── Types ─────────────────────────────────────────────────────────────────────

interface LogEntry {
  id:     number;
  stream: "stdout" | "stderr" | "system";
  line:   string;
  ts:     number; // Date.now()
}

type WsStatus = "connecting" | "open" | "closed" | "error";

interface LogConsoleProps {
  nodeId:        string;
  containerId:   string;
  containerName: string;
  onClose:       () => void;
}

// ── Constantes ────────────────────────────────────────────────────────────────

const MAX_LINES    = 2_000; // garde les N dernières lignes en mémoire
const API_URL      = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_API_URL   = toWsUrl(API_URL);

function toWsUrl(api: string): string {
  if (api.startsWith("/")) {
    // URL relative — dériver depuis l'origine de la page
    if (typeof window === "undefined") return "ws://localhost:8000";
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}${api}`;
  }
  return api.replace(/^https/, "wss").replace(/^http/, "ws");
}

// ── Composant ─────────────────────────────────────────────────────────────────

export function LogConsole({
  nodeId,
  containerId,
  containerName,
  onClose,
}: LogConsoleProps) {
  const [logs,       setLogs]       = useState<LogEntry[]>([]);
  const [wsStatus,   setWsStatus]   = useState<WsStatus>("connecting");
  const [autoScroll, setAutoScroll] = useState(true);

  const wsRef        = useRef<WebSocket | null>(null);
  const bottomRef    = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const counterRef   = useRef(0);

  // ── Connexion WebSocket ──────────────────────────────────────────────────
  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setWsStatus("error");
      addSystem("Erreur : token JWT manquant. Reconnectez-vous.");
      return;
    }

    const url = `${WS_API_URL}/ws/logs/${encodeURIComponent(nodeId)}/${encodeURIComponent(containerId)}?token=${token}&tail=100`;
    const ws  = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus("open");
      addSystem(`Connecté — flux de logs du conteneur ${containerName}`);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as {
          type:    "log" | "eof" | "error";
          stream?: "stdout" | "stderr";
          line?:   string;
        };

        if (msg.type === "log") {
          addLine(msg.stream ?? "stdout", msg.line ?? "");
        } else if (msg.type === "eof") {
          setWsStatus("closed");
          addSystem("── Fin du flux (conteneur arrêté ou déconnexion) ──");
        } else if (msg.type === "error") {
          addLine("stderr", `[ERREUR] ${msg.line ?? "inconnue"}`);
          setWsStatus("error");
        }
      } catch {
        // Message non-JSON ignoré
      }
    };

    ws.onerror = () => {
      setWsStatus("error");
      addSystem("Erreur WebSocket — vérifiez que le serveur est accessible.");
    };

    ws.onclose = (ev) => {
      setWsStatus("closed");
      if (ev.code !== 1000 && ev.code !== 1001) {
        addSystem(`Connexion fermée (code ${ev.code})`);
      }
    };

    return () => {
      ws.close(1000, "Composant démonté");
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeId, containerId]);

  // ── Auto-scroll ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "instant" });
    }
  }, [logs, autoScroll]);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
    setAutoScroll(atBottom);
  }, []);

  // ── Helpers ──────────────────────────────────────────────────────────────
  const addLine = (stream: "stdout" | "stderr", line: string) => {
    setLogs((prev) => {
      const entry: LogEntry = { id: ++counterRef.current, stream, line, ts: Date.now() };
      const next = prev.length >= MAX_LINES ? prev.slice(-MAX_LINES + 1) : prev;
      return [...next, entry];
    });
  };

  const addSystem = (line: string) => {
    setLogs((prev) => {
      const entry: LogEntry = { id: ++counterRef.current, stream: "system", line, ts: Date.now() };
      return [...prev, entry];
    });
  };

  const clearLogs = () => setLogs([]);

  // ── Rendu ─────────────────────────────────────────────────────────────────
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-label={`Logs de ${containerName}`}
    >
      {/* Overlay sombre */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Fenêtre terminal */}
      <div className="relative z-10 flex flex-col w-full max-w-4xl h-[80vh] rounded-xl overflow-hidden border border-slate-700 shadow-2xl shadow-black/60">

        {/* ── Barre de titre ─────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900 border-b border-slate-700/80 shrink-0">
          <div className="flex items-center gap-2.5">
            {/* Pastilles macOS style */}
            <div className="flex gap-1.5">
              <div className="h-3 w-3 rounded-full bg-red-500/80" />
              <div className="h-3 w-3 rounded-full bg-yellow-500/80" />
              <div className="h-3 w-3 rounded-full bg-green-500/80" />
            </div>
            <Terminal className="h-3.5 w-3.5 text-slate-500" />
            <span className="text-xs font-mono text-slate-300 font-medium">
              {containerName}
              <span className="text-slate-600 ml-1.5">— {nodeId}</span>
            </span>
          </div>

          <div className="flex items-center gap-3">
            {/* Statut connexion */}
            <StatusBadge status={wsStatus} />

            {/* Bouton clear */}
            <button
              onClick={clearLogs}
              className="text-[10px] text-slate-500 hover:text-slate-300 px-2 py-0.5 rounded border border-slate-700 hover:border-slate-600 transition-colors"
            >
              clear
            </button>

            {/* Bouton fermer */}
            <button
              onClick={onClose}
              className="text-slate-500 hover:text-slate-200 transition-colors"
              aria-label="Fermer la console"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* ── Zone de logs ────────────────────────────────────────────────── */}
        <div
          ref={containerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto bg-[#0d1117] font-mono text-xs leading-relaxed px-4 py-3 select-text"
        >
          {logs.length === 0 && wsStatus === "connecting" && (
            <div className="flex items-center gap-2 text-slate-600 mt-2">
              <Loader className="h-3 w-3 animate-spin" />
              <span>Connexion au flux de logs…</span>
            </div>
          )}

          {logs.map((entry) => (
            <LogRow key={entry.id} entry={entry} />
          ))}

          {/* Ancre auto-scroll */}
          <div ref={bottomRef} />
        </div>

        {/* ── Pied de page ────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-4 py-1.5 bg-slate-900 border-t border-slate-700/80 shrink-0">
          <span className="text-[10px] text-slate-600 font-mono">
            {logs.filter((l) => l.stream !== "system").length} ligne{logs.length > 1 ? "s" : ""}
          </span>
          {!autoScroll && (
            <button
              onClick={() => {
                setAutoScroll(true);
                bottomRef.current?.scrollIntoView({ behavior: "smooth" });
              }}
              className="text-[10px] text-blue-400 hover:text-blue-300 transition-colors"
            >
              ↓ Reprendre le défilement automatique
            </button>
          )}
          <span className="text-[10px] text-slate-600 font-mono">
            {containerId.slice(0, 12)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Sous-composants ───────────────────────────────────────────────────────────

function LogRow({ entry }: { entry: LogEntry }) {
  const colorClass =
    entry.stream === "stderr" ? "text-red-400" :
    entry.stream === "system" ? "text-slate-500 italic" :
    "text-green-400";

  // Nettoyer les éventuels escape codes ANSI basiques (non rendus dans un div)
  const clean = entry.line.replace(/\x1B\[[0-9;]*[mGKHF]/g, "");

  return (
    <div className={`whitespace-pre-wrap break-all ${colorClass}`}>
      {clean}
    </div>
  );
}

function StatusBadge({ status }: { status: WsStatus }) {
  const map: Record<WsStatus, { icon: React.ReactNode; label: string; cls: string }> = {
    connecting: {
      icon:  <Loader className="h-3 w-3 animate-spin" />,
      label: "Connexion…",
      cls:   "text-yellow-400",
    },
    open: {
      icon:  <Wifi className="h-3 w-3" />,
      label: "En direct",
      cls:   "text-emerald-400",
    },
    closed: {
      icon:  <WifiOff className="h-3 w-3" />,
      label: "Fermé",
      cls:   "text-slate-500",
    },
    error: {
      icon:  <WifiOff className="h-3 w-3" />,
      label: "Erreur",
      cls:   "text-red-400",
    },
  };

  const { icon, label, cls } = map[status];
  return (
    <span className={`flex items-center gap-1 text-[10px] font-medium ${cls}`}>
      {icon}
      {label}
    </span>
  );
}
