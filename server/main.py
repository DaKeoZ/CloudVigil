"""
CloudVigil — Point d'entrée du serveur.

Lance en parallèle :
  • Un serveur gRPC async (grpc.aio) sur le port configuré (défaut: 50051)
  • Une API HTTP FastAPI sur le port configuré (défaut: 8000)
  • Le moteur d'alertes en arrière-plan (background task asyncio)

Démarrage :
    uvicorn server.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import grpc.aio
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server import database, store
from server.alerts import AlertEngine, load_alert_config
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
    """Gère le cycle de vie complet : InfluxDB + gRPC + moteur d'alertes."""
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

    # 3. Charger la configuration des alertes et démarrer le moteur
    alert_config = load_alert_config(Path(settings.alerts_config_path))
    alert_engine = AlertEngine(alert_config)
    await alert_engine.start()

    # Stocker les références pour les routes
    app.state.grpc_server  = grpc_server
    app.state.alert_engine = alert_engine

    try:
        yield
    finally:
        # Arrêt gracieux : alertes → gRPC → InfluxDB
        await alert_engine.stop()
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

# CORS : autorise le frontend Next.js (dev sur :3000, prod configurable via env).
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        f"http://{_settings.http_host}:{_settings.http_port}",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
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


@app.get("/dashboard", summary="Vue d'ensemble de tous les nœuds monitorés")
async def get_dashboard() -> dict[str, Any]:
    """
    Endpoint principal du frontend CloudVigil.
    Retourne pour chaque nœud connu :
    - Son statut (online / offline)
    - La dernière mesure système (CPU / RAM / disque)
    - L'historique des 10 dernières minutes pour les sparklines
    - Le résumé des conteneurs Docker (si disponible)
    """
    # Métriques système depuis InfluxDB
    metrics_by_node = await database.query_metrics_all_nodes(minutes=10)

    # Nœuds ayant envoyé des données Docker (store mémoire)
    docker_node_ids = set(store.list_nodes())

    # Union des sources de données
    all_node_ids = set(metrics_by_node.keys()) | docker_node_ids

    result = []
    for node_id in sorted(all_node_ids):
        history = metrics_by_node.get(node_id, [])
        latest = history[-1] if history else None
        containers_data = store.get_containers(node_id)

        result.append(
            {
                "node_id": node_id,
                "status": "online" if latest else "offline",
                "latest": latest,
                "history": history,
                "containers": containers_data.get("containers", []) if containers_data else [],
                "container_count": containers_data.get("count", 0) if containers_data else 0,
                "updated_at": containers_data.get("updated_at") if containers_data else None,
            }
        )

    return {"nodes": result, "total": len(result)}


@app.get("/nodes", summary="Liste des nœuds avec données Docker")
async def list_nodes() -> dict[str, Any]:
    """Retourne la liste de tous les nœuds ayant envoyé au moins un rapport Docker."""
    nodes = store.list_nodes()
    return {"nodes": nodes, "count": len(nodes)}


# ── Alertes ───────────────────────────────────────────────────────────────────

@app.get("/alerts/status", summary="État du moteur d'alertes")
async def alerts_status() -> dict[str, Any]:
    """
    Retourne l'état complet du moteur d'alertes :
    - Règles configurées et leur sévérité
    - Statistiques (nombre d'évaluations, d'alertes envoyées)
    - Cooldowns actifs par (nœud, règle)
    - État des webhooks (Slack / Discord)
    """
    engine: AlertEngine = getattr(app.state, "alert_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Moteur d'alertes non initialisé.")
    return engine.stats()


@app.post("/alerts/test", summary="Envoi d'une notification de test sur les webhooks")
async def alerts_test() -> dict[str, Any]:
    """
    Envoie un message de test sur tous les webhooks actifs (Slack et/ou Discord).
    Utile pour vérifier que les URLs de webhook sont correctement configurées.

    Retourne le résultat par cible : `"ok"` ou `"erreur: <détail>"`.
    """
    engine: AlertEngine = getattr(app.state, "alert_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Moteur d'alertes non initialisé.")
    results = await engine.notifier.send_test()
    return {"results": results}


@app.delete(
    "/alerts/cooldown/{node_id}/{rule_name}",
    summary="Réinitialise le cooldown d'une règle pour un nœud",
)
async def reset_cooldown(node_id: str, rule_name: str) -> dict[str, str]:
    """
    Supprime le cooldown actif pour le couple (node_id, rule_name).
    Permet de forcer le renvoi immédiat d'une alerte sans attendre l'expiration.
    """
    engine: AlertEngine = getattr(app.state, "alert_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Moteur d'alertes non initialisé.")
    engine.cooldown.reset(node_id, rule_name)
    return {"status": "ok", "message": f"Cooldown réinitialisé pour ({node_id}, {rule_name})."}


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
