"""
CloudVigil — Point d'entrée du serveur.

Lance en parallèle :
  • Un serveur gRPC async (grpc.aio) sur le port configuré (défaut: 50051)
  • Une API HTTP FastAPI sur le port configuré (défaut: 8000)

Démarrage :
    uvicorn server.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import grpc.aio
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from server import database, store
from server.config import get_settings
from server.grpc_server import MonitoringServicer
from server.pb import monitor_pb2_grpc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gère le cycle de vie complet : InfluxDB + serveur gRPC."""
    settings = get_settings()

    # 1. Initialiser InfluxDB
    await database.init_db()

    # 2. Démarrer le serveur gRPC dans la même boucle asyncio
    grpc_server = grpc.aio.server()
    monitor_pb2_grpc.add_MonitoringServiceServicer_to_server(
        MonitoringServicer(), grpc_server
    )
    grpc_server.add_insecure_port(settings.grpc_listen)
    await grpc_server.start()
    log.info("Serveur gRPC démarré sur %s", settings.grpc_listen)

    # Stocker la référence pour les routes de healthcheck
    app.state.grpc_server = grpc_server

    try:
        yield
    finally:
        # Arrêt gracieux : on laisse 5 s aux flux en cours de se terminer.
        log.info("Arrêt du serveur gRPC (grace=5s)…")
        await grpc_server.stop(grace=5)
        await database.close_db()


# ── Application FastAPI ───────────────────────────────────────────────────────

app = FastAPI(
    title="CloudVigil Server",
    description="Récepteur de métriques agents via gRPC + persistence InfluxDB.",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", summary="Healthcheck global")
async def health() -> JSONResponse:
    """
    Vérifie l'état de santé de l'ensemble du serveur :
    - API FastAPI (toujours OK si cette réponse est reçue)
    - Connexion InfluxDB
    - Serveur gRPC (running / stopped)
    """
    influxdb_ok = await database.health_check()

    grpc_server = getattr(app.state, "grpc_server", None)
    grpc_state = "running" if grpc_server is not None else "not_started"

    overall = "ok" if influxdb_ok else "degraded"

    return JSONResponse(
        status_code=200 if influxdb_ok else 503,
        content={
            "status": overall,
            "components": {
                "api": "ok",
                "grpc": grpc_state,
                "influxdb": "ok" if influxdb_ok else "unreachable",
            },
        },
    )


@app.get(
    "/nodes/{node_id}/containers",
    summary="État des conteneurs Docker d'un nœud",
    response_description="Snapshot Docker le plus récent reçu pour ce nœud.",
)
async def get_node_containers(node_id: str) -> dict[str, Any]:
    """
    Retourne le dernier snapshot Docker reçu pour le nœud `node_id`.

    - **node_id** : identifiant du nœud (valeur de `CLOUDVIGIL_NODE_ID` côté agent)

    Retourne HTTP 404 si aucun rapport Docker n'a encore été reçu pour ce nœud
    (Docker non installé sur l'agent, ou agent non encore connecté).
    """
    data = store.get_containers(node_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Nœud '{node_id}' inconnu ou Docker non disponible sur cet agent.",
        )
    return data


@app.get("/nodes", summary="Liste des nœuds avec données Docker")
async def list_nodes() -> dict[str, Any]:
    """Retourne la liste de tous les nœuds ayant envoyé au moins un rapport Docker."""
    nodes = store.list_nodes()
    return {"nodes": nodes, "count": len(nodes)}


@app.get("/", include_in_schema=False)
async def root():
    return {"service": "CloudVigil Server", "docs": "/docs"}


# ── Lancement standalone ──────────────────────────────────────────────────────

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "server.main:app",
        host=settings.http_host,
        port=settings.http_port,
        log_level="info",
    )
