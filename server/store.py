"""
Cache mémoire partagé entre le servicer gRPC et l'API FastAPI.

Toutes les opérations sont thread-safe via asyncio.Lock car le servicer gRPC
(grpc.aio) et FastAPI partagent la même boucle d'événements.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

# ── Structure de données ──────────────────────────────────────────────────────

# { node_id: { "node_id": str, "containers": [...], "updated_at": str } }
_containers: dict[str, dict[str, Any]] = {}

_lock = asyncio.Lock()


# ── Écriture (appelée par le servicer gRPC) ───────────────────────────────────

async def update_containers(
    node_id: str,
    containers: list[dict[str, Any]],
    updated_at: datetime,
) -> None:
    """Écrase le snapshot Docker du nœud avec les données les plus récentes."""
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    async with _lock:
        _containers[node_id] = {
            "node_id": node_id,
            "containers": containers,
            "updated_at": updated_at.isoformat(),
            "count": len(containers),
        }


# ── Lecture (appelée par l'API FastAPI) ───────────────────────────────────────

def get_containers(node_id: str) -> dict[str, Any] | None:
    """Retourne le dernier snapshot Docker connu pour ce nœud, ou None."""
    return _containers.get(node_id)


def list_nodes() -> list[str]:
    """Retourne la liste des node_id ayant au moins un rapport Docker."""
    return list(_containers.keys())
