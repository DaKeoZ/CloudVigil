"use client";

import { LogOut } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

/**
 * Bouton de déconnexion affiché dans la barre de navigation.
 * Affiche également le nom d'utilisateur connecté.
 */
export function LogoutButton() {
  const { username, logout } = useAuth();

  return (
    <div className="flex items-center gap-2">
      {username && (
        <span className="hidden sm:inline text-xs text-slate-500">
          {username}
        </span>
      )}
      <button
        onClick={logout}
        title="Se déconnecter"
        className="flex items-center gap-1.5 rounded-lg border border-slate-700/60 bg-slate-800/50
                   px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 hover:border-slate-600
                   hover:bg-slate-800 transition-colors focus:outline-none focus:ring-2
                   focus:ring-blue-500/40"
      >
        <LogOut className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Déconnexion</span>
      </button>
    </div>
  );
}
