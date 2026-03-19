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

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, AsyncGenerator

import grpc
import grpc.aio
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm

from fastapi import WebSocket, WebSocketDisconnect

from server import database, store, ws_hub
from server.alerts import AlertEngine, load_alert_config
from server.auth import CurrentUser, Token, create_access_token, get_current_user, verify_credentials
from server.config import Settings, get_settings
from server.grpc_server import MonitoringServicer
from server.pb import monitor_pb2_grpc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger(__name__)


# ── Helpers TLS ───────────────────────────────────────────────────────────────

def _build_grpc_credentials(settings: Settings) -> grpc.ServerCredentials | None:
    """
    Construit les credentials mTLS pour le serveur gRPC.
    Retourne None si les chemins de certificats ne sont pas configurés
    (mode développement non sécurisé).
    """
    if not settings.tls_ca_cert:
        return None

    try:
        ca_cert     = Path(settings.tls_ca_cert).read_bytes()
        server_cert = Path(settings.tls_server_cert).read_bytes()
        server_key  = Path(settings.tls_server_key).read_bytes()
    except OSError as exc:
        log.error("[tls] Impossible de lire les certificats TLS : %s — mTLS désactivé.", exc)
        return None

    return grpc.ssl_server_credentials(
        private_key_certificate_chain_pairs=[(server_key, server_cert)],
        root_certificates=ca_cert,
        require_client_auth=True,   # mTLS strict : le client DOIT présenter son certificat
    )


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

    tls_creds = _build_grpc_credentials(settings)
    if tls_creds:
        grpc_server.add_secure_port(settings.grpc_listen, tls_creds)
        log.info("Serveur gRPC démarré sur %s (mTLS activé)", settings.grpc_listen)
    else:
        grpc_server.add_insecure_port(settings.grpc_listen)
        log.warning("Serveur gRPC démarré sur %s (⚠️  non chiffré)", settings.grpc_listen)

    await grpc_server.start()

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

# ── Authentification (publique) ───────────────────────────────────────────────

@app.post(
    "/auth/token",
    response_model=Token,
    summary="Obtenir un token JWT (OAuth2 Password Flow)",
    tags=["auth"],
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    """
    Authentification par identifiant / mot de passe.

    Retourne un Bearer JWT à inclure dans le header `Authorization: Bearer <token>`
    pour accéder aux endpoints protégés.

    Configurer les identifiants via les variables d'environnement :
    `CLOUDVIGIL_API_USERNAME` et `CLOUDVIGIL_API_PASSWORD`.
    """
    if not verify_credentials(form_data.username, form_data.password):
        log.warning("[auth] Tentative de connexion échouée pour '%s'", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiant ou mot de passe incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_in = create_access_token(form_data.username)
    log.info("[auth] Token JWT délivré pour '%s' (expire dans %ds)", form_data.username, expires_in)
    return Token(access_token=token, expires_in=expires_in)


# ── Healthcheck (public) ──────────────────────────────────────────────────────

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
async def get_node_containers(node_id: str, _: CurrentUser) -> dict[str, Any]:
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
async def get_dashboard(_: CurrentUser) -> dict[str, Any]:
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
async def list_nodes(_: CurrentUser) -> dict[str, Any]:
    """Retourne la liste de tous les nœuds ayant envoyé au moins un rapport Docker."""
    nodes = store.list_nodes()
    return {"nodes": nodes, "count": len(nodes)}


# ── Alertes ───────────────────────────────────────────────────────────────────

@app.get("/alerts/status", summary="État du moteur d'alertes")
async def alerts_status(_: CurrentUser) -> dict[str, Any]:
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
async def alerts_test(_: CurrentUser) -> dict[str, Any]:
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
async def reset_cooldown(node_id: str, rule_name: str, _: CurrentUser) -> dict[str, str]:
    """
    Supprime le cooldown actif pour le couple (node_id, rule_name).
    Permet de forcer le renvoi immédiat d'une alerte sans attendre l'expiration.
    """
    engine: AlertEngine = getattr(app.state, "alert_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Moteur d'alertes non initialisé.")
    engine.cooldown.reset(node_id, rule_name)
    return {"status": "ok", "message": f"Cooldown réinitialisé pour ({node_id}, {rule_name})."}


# ── Auto-réparation ───────────────────────────────────────────────────────────

@app.get("/repairs", summary="Historique des réparations automatiques")
async def get_repairs(
    _: CurrentUser,
    minutes: int = Query(default=1440, ge=1, le=43200, description="Fenêtre temporelle en minutes (défaut 24 h)"),
) -> dict[str, Any]:
    """
    Retourne l'historique des tentatives de réparation automatique (restarts) journalisées
    dans InfluxDB. Triées de la plus récente à la plus ancienne.

    - `minutes=1440` → 24 dernières heures (défaut)
    - `minutes=60`   → 1 heure
    """
    events = await database.query_repair_events(minutes=minutes)
    return {
        "events":  events,
        "total":   len(events),
        "window_minutes": minutes,
    }


# ── WebSocket — Log Viewer ─────────────────────────────────────────────────────

@app.websocket("/ws/agent/{node_id}")
async def agent_ws_endpoint(ws: WebSocket, node_id: str) -> None:
    """
    Canal de contrôle permanent : l'agent Go s'y connecte au démarrage.

    - Reçoit les commandes start_logs / stop_logs depuis les sessions frontend.
    - Envoie les lignes de logs vers le hub qui les route aux sessions frontend.

    Pas d'authentification JWT sur cet endpoint : la légitimité de l'agent
    est garantie par le mTLS gRPC ; l'isolation réseau Docker empêche les
    connexions externes non autorisées.
    """
    await ws.accept()
    await ws_hub.register_agent(node_id, ws)
    try:
        await ws_hub.pump_agent(node_id, ws)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("[ws/agent/%s] Connexion perdue : %s", node_id, exc)
    finally:
        await ws_hub.unregister_agent(node_id)


@app.websocket("/ws/logs/{node_id}/{container_id}")
async def logs_ws_endpoint(
    ws:           WebSocket,
    node_id:      str,
    container_id: str,
    tail:         str = "50",
    token:        str = "",         # Bearer JWT passé en query param (WS ne supporte pas les headers custom)
) -> None:
    """
    Le frontend se connecte ici pour recevoir les logs d'un conteneur en direct.

    Flux :
      1. Validation du token JWT (query param `?token=<jwt>`)
      2. Commande start_logs envoyée à l'agent via le hub
      3. Les logs arrivent de l'agent et sont routés vers cette connexion
      4. À la déconnexion frontend, commande stop_logs envoyée à l'agent
    """
    await ws.accept()

    # ── Validation JWT ────────────────────────────────────────────────────────
    if token:
        try:
            await get_current_user(token)
        except Exception:
            await ws.send_json({"type": "error", "line": "Token JWT invalide ou expiré."})
            await ws.close(code=4001)
            return
    else:
        await ws.send_json({"type": "error", "line": "Authentification requise (paramètre ?token=…)."})
        await ws.close(code=4001)
        return

    # ── Ouverture de la session de logs ───────────────────────────────────────
    session_id = await ws_hub.open_log_session(node_id, container_id, ws, tail=tail)

    if session_id is None:
        await ws.send_json({
            "type": "error",
            "line": f"Agent '{node_id}' non connecté au hub WebSocket. "
                    "Vérifiez que CLOUDVIGIL_WS_SERVER est correctement configuré sur l'agent.",
        })
        await ws.close(code=4002)
        return

    log.info("[ws/logs] Session %s ouverte — nœud=%s conteneur=%s", session_id, node_id, container_id)

    try:
        # Garder la connexion ouverte ; le frontend peut envoyer des messages de contrôle
        async for msg in ws.iter_json():
            if msg.get("action") == "clear":
                pass  # Réservé pour futures extensions (ex. clear terminal)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.debug("[ws/logs/%s] Déconnexion : %s", session_id, exc)
    finally:
        await ws_hub.close_log_session(node_id, session_id)
        log.info("[ws/logs] Session %s fermée", session_id)


@app.get("/ws/status", summary="État du hub WebSocket (agents connectés + sessions actives)")
async def ws_status(_: CurrentUser) -> dict:
    """Retourne l'état du hub WebSocket : agents connectés et sessions de logs actives."""
    return ws_hub.stats()


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
