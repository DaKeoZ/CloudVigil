"use client";

import { FormEvent, useState } from "react";
import { Activity, Eye, EyeOff, Lock } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const { login, isLoading, error } = useAuth();
  const [username,  setUsername]    = useState("");
  const [password,  setPassword]    = useState("");
  const [showPass,  setShowPass]    = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    await login(username, password);
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">

        {/* ── Logo ──────────────────────────────────────────────────────────── */}
        <div className="flex flex-col items-center gap-3 mb-8">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 shadow-xl shadow-blue-600/30">
            <Activity className="h-6 w-6 text-white" />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold text-slate-100 tracking-tight">CloudVigil</h1>
            <p className="text-slate-500 text-sm mt-0.5">Tableau de bord de monitoring</p>
          </div>
        </div>

        {/* ── Formulaire ────────────────────────────────────────────────────── */}
        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-slate-800 bg-slate-900/70 backdrop-blur-sm p-8 space-y-5 shadow-xl"
        >
          <div className="flex items-center gap-2 mb-2">
            <Lock className="h-4 w-4 text-slate-500" />
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-widest">
              Connexion sécurisée
            </h2>
          </div>

          {/* Identifiant */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-400" htmlFor="username">
              Identifiant
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800/80 px-4 py-2.5
                         text-slate-100 placeholder-slate-600 text-sm
                         focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500
                         transition-colors"
              placeholder="admin"
            />
          </div>

          {/* Mot de passe */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-400" htmlFor="password">
              Mot de passe
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPass ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800/80 px-4 py-2.5 pr-10
                           text-slate-100 placeholder-slate-600 text-sm
                           focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500
                           transition-colors"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPass((p) => !p)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                aria-label={showPass ? "Masquer le mot de passe" : "Afficher le mot de passe"}
              >
                {showPass ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {/* Message d'erreur */}
          {error && (
            <div className="flex items-start gap-2.5 rounded-lg border border-red-500/20 bg-red-500/8 px-4 py-3">
              <span className="text-red-400 text-sm">{error}</span>
            </div>
          )}

          {/* Bouton de connexion */}
          <button
            type="submit"
            disabled={isLoading || !username || !password}
            className="w-full rounded-lg bg-blue-600 hover:bg-blue-500 active:bg-blue-700
                       disabled:opacity-40 disabled:cursor-not-allowed
                       text-white font-semibold text-sm py-2.5 mt-1
                       transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500/60 focus:ring-offset-1 focus:ring-offset-slate-900"
          >
            {isLoading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-3.5 w-3.5 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                Connexion en cours…
              </span>
            ) : (
              "Se connecter"
            )}
          </button>
        </form>

        <p className="text-center text-xs text-slate-700 mt-6">
          Accès protégé par JWT · CloudVigil
        </p>
      </div>
    </div>
  );
}
