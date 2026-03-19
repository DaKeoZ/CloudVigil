"""
CloudVigil — Hub WebSocket pour le Log Viewer.

Topologie :
    Agent Go  ──WS──▶  /ws/agent/{node_id}      (connexion persistante, 1 par agent)
    Frontend  ──WS──▶  /ws/logs/{node_id}/{cid}  (1 par onglet de logs ouvert)

Protocole Agent → Hub :
    {"type":"log",   "session_id":"…", "container_id":"…", "stream":"stdout", "line":"…"}
    {"type":"eof",   "session_id":"…", "container_id":"…"}
    {"type":"error", "session_id":"…", "container_id":"…", "line":"…"}

Protocole Hub → Agent :
    {"action":"start_logs", "session_id":"…", "container_id":"…", "tail":"50"}
    {"action":"stop_logs",  "session_id":"…"}
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)

# ── État global ───────────────────────────────────────────────────────────────
# Ces dicts vivent dans le même event loop asyncio → pas de verrous threading.
# Un asyncio.Lock suffit pour la cohérence des lectures/écritures groupées.

_agents:   dict[str, WebSocket] = {}   # node_id  → WebSocket (agent)
_sessions: dict[str, WebSocket] = {}   # session_id → WebSocket (frontend)

_lock = asyncio.Lock()


# ── Gestion des agents ────────────────────────────────────────────────────────

async def register_agent(node_id: str, ws: WebSocket) -> None:
    async with _lock:
        _agents[node_id] = ws
    log.info("[ws_hub] Agent '%s' enregistré (%d agent(s) connecté(s))", node_id, len(_agents))


async def unregister_agent(node_id: str) -> None:
    async with _lock:
        _agents.pop(node_id, None)
    log.info("[ws_hub] Agent '%s' déconnecté (%d agent(s) restant(s))", node_id, len(_agents))


# ── Gestion des sessions frontend ─────────────────────────────────────────────

def new_session_id() -> str:
    """Génère un identifiant de session court (8 hex chars)."""
    return uuid.uuid4().hex[:8]


async def register_frontend(session_id: str, ws: WebSocket) -> None:
    async with _lock:
        _sessions[session_id] = ws


async def unregister_frontend(session_id: str) -> None:
    async with _lock:
        _sessions.pop(session_id, None)


# ── Routage des messages ──────────────────────────────────────────────────────

async def route_agent_message(msg: dict[str, Any]) -> None:
    """
    Route un message provenant d'un agent vers la session frontend correspondante.
    Ignore silencieusement si la session a déjà été fermée.
    """
    session_id = msg.get("session_id")
    if not session_id:
        return

    ws = _sessions.get(session_id)
    if ws is None:
        return  # Frontend déjà fermé

    try:
        await ws.send_json(msg)
    except Exception as exc:
        log.debug("[ws_hub] Envoi frontend session=%s échoué : %s", session_id, exc)


async def send_to_agent(node_id: str, command: dict[str, Any]) -> bool:
    """
    Envoie une commande à l'agent identifié par node_id.
    Retourne False si l'agent n'est pas connecté ou si l'envoi échoue.
    """
    ws = _agents.get(node_id)
    if ws is None:
        return False
    try:
        await ws.send_json(command)
        return True
    except Exception as exc:
        log.warning("[ws_hub] Envoi agent '%s' échoué : %s", node_id, exc)
        return False


# ── Lecture des messages d'un agent (boucle principale) ──────────────────────

async def pump_agent(node_id: str, ws: WebSocket) -> None:
    """
    Lit les messages de l'agent en boucle et les route vers les sessions frontend.
    Retourne quand la connexion se ferme (normalement ou sur erreur).
    """
    async for msg in ws.iter_json():
        await route_agent_message(msg)


# ── Statistiques ──────────────────────────────────────────────────────────────

def stats() -> dict[str, Any]:
    return {
        "connected_agents":   list(_agents.keys()),
        "active_log_sessions": len(_sessions),
    }


# ── Ouverture d'une session de logs (helper haut-niveau) ──────────────────────

async def open_log_session(
    node_id:      str,
    container_id: str,
    frontend_ws:  WebSocket,
    tail:         str = "50",
) -> str | None:
    """
    Crée une session de logs, l'enregistre et envoie la commande start_logs à l'agent.
    Retourne le session_id, ou None si l'agent n'est pas connecté.
    """
    session_id = new_session_id()
    await register_frontend(session_id, frontend_ws)

    success = await send_to_agent(node_id, {
        "action":       "start_logs",
        "container_id": container_id,
        "session_id":   session_id,
        "tail":         tail,
    })

    if not success:
        await unregister_frontend(session_id)
        return None

    return session_id


async def close_log_session(node_id: str, session_id: str) -> None:
    """
    Arrête la session de logs côté agent et nettoie l'état du hub.
    """
    await unregister_frontend(session_id)
    await send_to_agent(node_id, {
        "action":     "stop_logs",
        "session_id": session_id,
    })
