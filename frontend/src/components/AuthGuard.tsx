"use client";

/**
 * AuthGuard : redirige vers /login si aucun token JWT n'est présent dans
 * localStorage. Ce composant est purement côté client (le middleware Next.js
 * n'a pas accès à localStorage).
 *
 * Usage :
 *   <AuthGuard><MonContenu /></AuthGuard>
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity } from "lucide-react";
import { getStoredToken } from "@/hooks/useAuth";

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const [checked, setChecked] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (!getStoredToken()) {
      router.replace("/login");
    } else {
      setChecked(true);
    }
  }, [router]);

  if (!checked) {
    // Splash minimaliste pendant la vérification du token
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex items-center gap-3 text-slate-500">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600/20">
            <Activity className="h-4 w-4 text-blue-400 animate-pulse" />
          </div>
          <span className="text-sm">Vérification de la session…</span>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
