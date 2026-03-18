"""
Moteur d'alertes CloudVigil — Background Task asyncio.

Cycle d'évaluation (toutes les CHECK_INTERVAL_SECONDS) :
  1. Interroger InfluxDB pour récupérer l'historique de tous les nœuds actifs
     sur la fenêtre temporelle la plus large des règles configurées.
  2. Pour chaque nœud × règle :
       a. Extraire les points dans la fenêtre de la règle.
       b. Vérifier que TOUS les points franchissent le seuil.
       c. Si oui et que le cooldown est inactif → notifier + démarrer le cooldown.
  3. Attendre CHECK_INTERVAL_SECONDS avant le prochain cycle.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from server import database
from server.alerts.config import AlertConfig, AlertRule
from server.alerts.cooldown import CooldownTracker
from server.alerts.notifier import WebhookNotifier

log = logging.getLogger(__name__)

# Intervalle entre deux évaluations complètes (en secondes)
CHECK_INTERVAL_SECONDS: int = 30


class AlertEngine:
    """
    Moteur d'alertes tournant comme tâche asyncio de fond.

    Cycle de vie :
      await engine.start()   ← appelé dans le lifespan FastAPI
      await engine.stop()    ← appelé à l'arrêt du serveur
    """

    def __init__(self, config: AlertConfig) -> None:
        self._config   = config
        self._notifier = WebhookNotifier(config)
        self._cooldown = CooldownTracker()
        self._task:    asyncio.Task | None = None
        self._total_alerts_sent: int = 0
        self._total_evaluations:  int = 0
        self._last_run_at: datetime | None = None

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self._config.rules:
            log.info("[alerts] Aucune règle définie — moteur désactivé.")
            return

        if not self._config.has_active_webhook:
            log.warning(
                "[alerts] %d règle(s) chargée(s) mais aucun webhook actif — "
                "les alertes seront uniquement loguées.",
                len(self._config.rules),
            )

        self._task = asyncio.create_task(self._run_loop(), name="cloudvigil-alert-engine")
        log.info(
            "[alerts] Moteur démarré — %d règle(s), cycle toutes les %ds",
            len(self._config.rules),
            CHECK_INTERVAL_SECONDS,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info(
            "[alerts] Moteur arrêté — %d évaluation(s), %d alerte(s) envoyée(s).",
            self._total_evaluations,
            self._total_alerts_sent,
        )

    # ── Boucle principale ─────────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        """Boucle infinie : évalue toutes les règles toutes les CHECK_INTERVAL_SECONDS."""
        # Premier cycle immédiat
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        while True:
            try:
                await self._evaluate_all_nodes()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("[alerts] Erreur inattendue dans le moteur : %s", exc, exc_info=True)
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    # ── Évaluation ────────────────────────────────────────────────────────────

    async def _evaluate_all_nodes(self) -> None:
        """
        Récupère l'historique de tous les nœuds et évalue chaque règle.
        Une seule requête InfluxDB par cycle, fenêtrée sur le max des durées.
        """
        if not self._config.rules:
            return

        max_window = max(r.duration_minutes for r in self._config.rules)
        nodes_data: dict[str, list[dict]] = await database.query_metrics_all_nodes(
            minutes=max_window
        )

        self._total_evaluations += 1
        self._last_run_at = datetime.now(tz=timezone.utc)

        if not nodes_data:
            log.debug("[alerts] Aucune métrique disponible dans InfluxDB.")
            return

        for node_id, history in nodes_data.items():
            for rule in self._config.rules:
                await self._evaluate_rule(node_id, rule, history)

    async def _evaluate_rule(
        self,
        node_id:      str,
        rule:         AlertRule,
        full_history: list[dict[str, Any]],
    ) -> None:
        """
        Évalue une règle sur la fenêtre temporelle qui lui correspond.

        Condition de déclenchement :
          TOUS les points dans la fenêtre [now - duration_minutes, now]
          doivent franchir le seuil défini.
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=rule.duration_minutes)

        # Filtrer les points dans la fenêtre de la règle
        window: list[dict] = []
        for point in full_history:
            try:
                ts = datetime.fromisoformat(point["timestamp"])
                if ts >= cutoff:
                    window.append(point)
            except (KeyError, ValueError):
                continue

        if len(window) < 2:
            # Pas assez de points pour une évaluation fiable
            log.debug(
                "[alerts] (%s, %s) — %d point(s) dans la fenêtre, skip.",
                node_id, rule.name, len(window),
            )
            return

        # Extraire les valeurs de la métrique ciblée
        values: list[float] = [
            float(p[rule.metric])
            for p in window
            if p.get(rule.metric) is not None
        ]

        if not values:
            return

        # Vérifier si TOUS les points franchissent le seuil
        all_breached = all(rule.evaluate(v) for v in values)

        if not all_breached:
            return  # Pas de dépassement continu → pas d'alerte

        # ── Cooldown ──────────────────────────────────────────────────────────
        if self._cooldown.is_active(node_id, rule.name):
            remaining = self._cooldown.get_remaining(node_id, rule.name)
            log.debug(
                "[alerts] Cooldown actif pour (%s, %s) — reste %s, alerte supprimée.",
                node_id, rule.name, remaining,
            )
            return

        # ── Déclenchement de l'alerte ─────────────────────────────────────────
        avg_value = sum(values) / len(values)

        log.warning(
            "[alerts] %s ALERTE '%s' — nœud=%s %s=%.1f%% (moy.) "
            "sur %d points / %dmin — cooldown %dmin",
            _severity_prefix(rule.severity),
            rule.name,
            node_id,
            rule.metric,
            avg_value,
            len(values),
            rule.duration_minutes,
            rule.cooldown_minutes,
        )

        # Envoi de la notification (non bloquant pour le cycle)
        await self._notifier.send(
            node_id=node_id,
            rule=rule,
            avg_value=avg_value,
            breach_count=len(values),
        )

        # Démarrer le cooldown immédiatement après l'envoi
        self._cooldown.set(node_id, rule.name, rule.cooldown_minutes)
        self._total_alerts_sent += 1

    # ── Statistiques ──────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Retourne l'état du moteur pour l'endpoint GET /alerts/status."""
        return {
            "running":          self._task is not None and not self._task.done(),
            "rules_count":      len(self._config.rules),
            "check_interval_s": CHECK_INTERVAL_SECONDS,
            "total_evaluations": self._total_evaluations,
            "total_alerts_sent": self._total_alerts_sent,
            "last_run_at":      self._last_run_at.isoformat() if self._last_run_at else None,
            "webhooks": {
                "slack":   "actif" if self._config.slack.is_active   else "inactif",
                "discord": "actif" if self._config.discord.is_active else "inactif",
            },
            "active_cooldowns": self._cooldown.snapshot(),
            "rules": [r.to_dict() for r in self._config.rules],
        }

    @property
    def cooldown(self) -> CooldownTracker:
        """Accès au tracker de cooldown (pour les tests et l'endpoint de reset)."""
        return self._cooldown

    @property
    def notifier(self) -> WebhookNotifier:
        """Accès au notifier (pour l'endpoint /alerts/test)."""
        return self._notifier


def _severity_prefix(severity: str) -> str:
    return {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(severity, "⚠️")
