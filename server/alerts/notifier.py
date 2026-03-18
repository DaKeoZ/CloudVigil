"""
Envoi de notifications via Webhook (Slack et/ou Discord).

Formats respectés :
  Slack   — Incoming Webhooks avec `attachments` colorés
  Discord — Webhook Embeds avec couleur et timestamp
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from server.alerts.config import AlertConfig, AlertRule

log = logging.getLogger(__name__)

# ── Couleurs par sévérité ─────────────────────────────────────────────────────

_SLACK_COLOR: dict[str, str] = {
    "info":     "#3b82f6",   # blue
    "warning":  "#f59e0b",   # amber
    "critical": "#ef4444",   # red
}

_DISCORD_COLOR: dict[str, int] = {
    "info":     0x3B82F6,
    "warning":  0xF59E0B,
    "critical": 0xEF4444,
}

_EMOJI: dict[str, str] = {
    "info":     "ℹ️",
    "warning":  "⚠️",
    "critical": "🚨",
}


class WebhookNotifier:
    """
    Envoie des alertes structurées vers les webhooks configurés.
    Utilise aiohttp (déjà disponible via influxdb-client[async]).
    """

    def __init__(self, config: AlertConfig) -> None:
        self._config = config

    async def send(
        self,
        node_id:     str,
        rule:        AlertRule,
        avg_value:   float,
        breach_count: int,
    ) -> None:
        """
        Envoie la notification vers tous les webhooks actifs.
        Les erreurs sont loguées sans interrompre le flux.
        """
        if not self._config.has_active_webhook:
            log.info(
                "[notifier] Alerte '%s' sur %s — aucun webhook actif, log uniquement.",
                rule.name, node_id,
            )
            return

        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        tasks: list[object] = []

        if self._config.slack.is_active:
            tasks.append(
                self._send_slack(node_id, rule, avg_value, breach_count, ts)
            )
        if self._config.discord.is_active:
            tasks.append(
                self._send_discord(node_id, rule, avg_value, breach_count, ts)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, Exception):
                log.error("[notifier] Échec de la notification : %s", res)

    # ── Slack ─────────────────────────────────────────────────────────────────

    async def _send_slack(
        self,
        node_id:      str,
        rule:         AlertRule,
        avg_value:    float,
        breach_count: int,
        ts:           str,
    ) -> None:
        emoji = _EMOJI.get(rule.severity, "⚠️")
        color = _SLACK_COLOR.get(rule.severity, "#f59e0b")

        payload: dict[str, Any] = {
            "text": f"{emoji} *Alerte CloudVigil — {rule.name}*",
            "attachments": [
                {
                    "color": color,
                    "fields": [
                        {"title": "Nœud",            "value": f"`{node_id}`",                          "short": True},
                        {"title": "Métrique",         "value": rule.metric,                              "short": True},
                        {"title": "Valeur moyenne",   "value": f"*{avg_value:.1f}%*",                   "short": True},
                        {"title": "Seuil",            "value": f"{rule.operator} {rule.threshold}%",    "short": True},
                        {"title": "Fenêtre d'alerte", "value": f"{rule.duration_minutes} min",          "short": True},
                        {"title": "Points analysés",  "value": str(breach_count),                       "short": True},
                        {"title": "Cooldown",         "value": f"{rule.cooldown_minutes} min",           "short": True},
                        {"title": "Sévérité",         "value": rule.severity.upper(),                   "short": True},
                    ],
                    "footer": f"CloudVigil Monitor • {ts}",
                    "footer_icon": "https://raw.githubusercontent.com/cloudvigil/cloudvigil/main/docs/logo.png",
                }
            ],
        }

        await self._post(self._config.slack.url, payload, "Slack")

    # ── Discord ───────────────────────────────────────────────────────────────

    async def _send_discord(
        self,
        node_id:      str,
        rule:         AlertRule,
        avg_value:    float,
        breach_count: int,
        ts:           str,
    ) -> None:
        emoji = _EMOJI.get(rule.severity, "⚠️")
        color = _DISCORD_COLOR.get(rule.severity, 0xF59E0B)

        payload: dict[str, Any] = {
            "embeds": [
                {
                    "title":       f"{emoji}  Alerte CloudVigil — {rule.name}",
                    "description": (
                        f"Le nœud **`{node_id}`** a dépassé le seuil configuré "
                        f"pendant **{rule.duration_minutes} minute(s)**."
                    ),
                    "color": color,
                    "fields": [
                        {"name": "Nœud",            "value": f"`{node_id}`",                        "inline": True},
                        {"name": "Métrique",         "value": f"`{rule.metric}`",                   "inline": True},
                        {"name": "Sévérité",         "value": rule.severity.upper(),                "inline": True},
                        {"name": "Valeur moyenne",   "value": f"**{avg_value:.1f}%**",              "inline": True},
                        {"name": "Seuil",            "value": f"`{rule.operator} {rule.threshold}%`", "inline": True},
                        {"name": "Points analysés",  "value": str(breach_count),                   "inline": True},
                        {"name": "Cooldown actif",   "value": f"{rule.cooldown_minutes} min",      "inline": True},
                    ],
                    "footer":    {"text": f"CloudVigil Monitor • {ts}"},
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                }
            ]
        }

        await self._post(self._config.discord.url, payload, "Discord")

    # ── Envoi HTTP ────────────────────────────────────────────────────────────

    async def _post(self, url: str, payload: dict, target: str) -> None:
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        raise RuntimeError(
                            f"[{target}] HTTP {resp.status}: {body[:200]}"
                        )
                    log.info("[notifier] %s — notification envoyée (HTTP %s)", target, resp.status)
        except aiohttp.ClientError as exc:
            raise RuntimeError(f"[{target}] Erreur réseau : {exc}") from exc

    # ── Test de connexion ─────────────────────────────────────────────────────

    async def send_test(self) -> dict[str, str]:
        """
        Envoie une notification de test sur tous les webhooks actifs.
        Retourne { "slack": "ok"|"error: ...", "discord": "ok"|"error: ..." }.
        """
        results: dict[str, str] = {}

        test_rule = AlertRule(
            name="Test CloudVigil",
            metric="cpu_usage",
            operator=">",
            threshold=90.0,
            severity="info",
        )
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        for target, is_active, send_fn in [
            ("slack",   self._config.slack.is_active,   self._send_slack),
            ("discord", self._config.discord.is_active, self._send_discord),
        ]:
            if not is_active:
                results[target] = "désactivé"
                continue
            try:
                await send_fn("test-node", test_rule, 91.5, 3, ts)  # type: ignore[arg-type]
                results[target] = "ok"
            except Exception as exc:
                results[target] = f"erreur: {exc}"

        return results
