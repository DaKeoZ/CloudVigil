"""
Suivi des cooldowns par (node_id, rule_name).

Le CooldownTracker vit dans la même boucle asyncio que le moteur d'alertes :
pas besoin de Lock asyncio puisque asyncio est mono-thread (cooperative multitasking).
En revanche, les accès sont intrinsèquement thread-safe grâce au GIL Python pour
les types dict natifs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class CooldownTracker:
    """
    Empêche le spam de notifications en mémorisant quand la prochaine alerte
    est autorisée pour chaque couple (node_id, rule_name).
    """

    def __init__(self) -> None:
        # { (node_id, rule_name): expires_at (UTC datetime) }
        self._store: dict[tuple[str, str], datetime] = {}

    # ── API principale ────────────────────────────────────────────────────────

    def is_active(self, node_id: str, rule_name: str) -> bool:
        """Retourne True si le cooldown est encore actif (alerte supprimée)."""
        expires_at = self._store.get((node_id, rule_name))
        if expires_at is None:
            return False
        if datetime.now(tz=timezone.utc) >= expires_at:
            # Nettoyage paresseux
            del self._store[(node_id, rule_name)]
            return False
        return True

    def set(self, node_id: str, rule_name: str, cooldown_minutes: int) -> None:
        """Démarre un cooldown de `cooldown_minutes` pour ce couple (nœud, règle)."""
        expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=cooldown_minutes)
        self._store[(node_id, rule_name)] = expires_at

    def get_remaining(self, node_id: str, rule_name: str) -> timedelta | None:
        """Retourne le temps restant du cooldown, ou None si inactif."""
        expires_at = self._store.get((node_id, rule_name))
        if expires_at is None:
            return None
        remaining = expires_at - datetime.now(tz=timezone.utc)
        return remaining if remaining.total_seconds() > 0 else None

    def reset(self, node_id: str, rule_name: str) -> None:
        """Supprime manuellement le cooldown (utile pour les tests)."""
        self._store.pop((node_id, rule_name), None)

    def reset_all(self) -> None:
        """Réinitialise tous les cooldowns."""
        self._store.clear()

    # ── Sérialisation ─────────────────────────────────────────────────────────

    def snapshot(self) -> list[dict[str, Any]]:
        """
        Retourne une liste de tous les cooldowns actifs avec leur état.
        Utile pour l'endpoint /alerts/status.
        """
        now = datetime.now(tz=timezone.utc)
        result = []
        for (node_id, rule_name), expires_at in list(self._store.items()):
            remaining_s = (expires_at - now).total_seconds()
            if remaining_s <= 0:
                continue
            result.append(
                {
                    "node_id":            node_id,
                    "rule":               rule_name,
                    "expires_at":         expires_at.isoformat(),
                    "remaining_seconds":  int(remaining_s),
                    "remaining_human":    _fmt_duration(remaining_s),
                }
            )
        return result

    def __len__(self) -> int:
        return sum(
            1 for exp in self._store.values()
            if exp > datetime.now(tz=timezone.utc)
        )


def _fmt_duration(seconds: float) -> str:
    """Formate une durée en secondes en 'Xh Ym Zs' lisible."""
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}min")
    parts.append(f"{s}s")
    return " ".join(parts)
