"""
CloudVigil — NetworkProber

Sonde périodiquement des URLs externes (HTTP/HTTPS) pour mesurer :
  - La disponibilité (code HTTP 2xx)
  - La latence (temps de réponse en ms)
  - L'expiration du certificat SSL (pour les URLs HTTPS)

Alertes déclenchées :
  - Cible injoignable → sévérité "critical"
  - Certificat SSL expirant dans < ssl_warning_days jours → sévérité "critical"

Architecture :
  - Tâche asyncio de fond démarrée par le lifespan FastAPI
  - Résultats en mémoire (deque de 20 points par cible) pour réponse rapide de l'API
  - Persistance dans InfluxDB (measurement: network_probes)
  - Cooldown par URL pour éviter le spam d'alertes
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import aiohttp

from server import database
from server.alerts.config import AlertConfig, NetworkTarget
from server.alerts.cooldown import CooldownTracker
from server.alerts.notifier import WebhookNotifier

log = logging.getLogger(__name__)

# Sentinelle : "SSL non applicable ou non récupéré"
_SSL_NA = -1


# ── Résultat d'une sonde ──────────────────────────────────────────────────────

class ProbeResult:
    """Encapsule le résultat d'un probe sur une URL donnée."""

    def __init__(
        self,
        target:             NetworkTarget,
        reachable:          bool,
        status_code:        int | None        = None,
        latency_ms:         float | None      = None,
        ssl_days_remaining: int | None        = None,  # None = non HTTPS / non récupéré
        error:              str | None        = None,
        checked_at:         datetime | None   = None,
    ) -> None:
        self.target             = target
        self.reachable          = reachable
        self.status_code        = status_code
        self.latency_ms         = round(latency_ms, 1) if latency_ms is not None else None
        self.ssl_days_remaining = ssl_days_remaining
        self.error              = error
        self.checked_at         = checked_at or datetime.now(tz=timezone.utc)

    # ── Propriétés calculées ──────────────────────────────────────────────────

    @property
    def status(self) -> str:
        return "up" if self.reachable else "down"

    @property
    def ssl_status(self) -> str:
        """Catégorie SSL : ok / warning / critical / expired / na."""
        d = self.ssl_days_remaining
        if d is None:
            return "na"
        if d < 0:
            return "expired"
        if d < 7:
            return "critical"
        if d < 30:
            return "warning"
        return "ok"

    # ── Sérialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "name":               self.target.name,
            "url":                self.target.url,
            "status":             self.status,
            "reachable":          self.reachable,
            "status_code":        self.status_code,
            "latency_ms":         self.latency_ms,
            "ssl_days_remaining": self.ssl_days_remaining,
            "ssl_status":         self.ssl_status,
            "error":              self.error,
            "last_checked":       self.checked_at.isoformat(),
        }

    def to_history_point(self) -> dict[str, Any]:
        """Point compact pour la sparkline de latence."""
        return {
            "t":          self.checked_at.isoformat(),
            "latency_ms": self.latency_ms,
            "up":         self.reachable,
        }


# ── Prober principal ──────────────────────────────────────────────────────────

class NetworkProber:
    """
    Service de fond qui sonde des URLs HTTP/HTTPS périodiquement.

    Cycle de vie :
      await prober.start()  ← appelé dans le lifespan FastAPI
      await prober.stop()   ← appelé à l'arrêt du serveur
    """

    # Historique conservé en mémoire par cible (pour la sparkline)
    _HISTORY_LEN = 20

    def __init__(self, config: AlertConfig) -> None:
        self._config    = config
        self._notifier  = WebhookNotifier(config)
        self._cooldown  = CooldownTracker()
        self._task:     asyncio.Task | None = None

        # État en mémoire : url → dernier résultat + historique
        self._latest:  dict[str, ProbeResult]          = {}
        self._history: dict[str, deque[dict[str, Any]]] = {}

        # Statistiques
        self._total_probes:  int = 0
        self._total_alerts:  int = 0
        self._started_at:    datetime | None = None

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        net = self._config.network
        if not net.is_active:
            log.info("[network] Aucune cible configurée — sonde réseau désactivée.")
            return

        for t in net.targets:
            self._history[t.url] = deque(maxlen=self._HISTORY_LEN)

        self._task = asyncio.create_task(
            self._run_loop(), name="cloudvigil-network-prober"
        )
        self._started_at = datetime.now(tz=timezone.utc)
        log.info(
            "[network] Sonde démarrée — %d cible(s), intervalle=%ds, ssl_warning=%dj",
            len(net.targets),
            net.interval_seconds,
            net.ssl_warning_days,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info(
            "[network] Sonde arrêtée — %d probe(s), %d alerte(s).",
            self._total_probes,
            self._total_alerts,
        )

    # ── Boucle principale ─────────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        """Premier probe immédiat, puis toutes les interval_seconds secondes."""
        await self._probe_all()
        interval = self._config.network.interval_seconds
        while True:
            try:
                await asyncio.sleep(interval)
                await self._probe_all()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("[network] Erreur dans la boucle : %s", exc, exc_info=True)

    async def _probe_all(self) -> None:
        tasks = [self._probe_target(t) for t in self._config.network.targets]
        await asyncio.gather(*tasks, return_exceptions=True)

    # ── Probe d'une cible ─────────────────────────────────────────────────────

    async def _probe_target(self, target: NetworkTarget) -> None:
        """Sonde une URL : HTTP + SSL. Persiste le résultat et évalue les alertes."""
        net     = self._config.network
        timeout = aiohttp.ClientTimeout(total=net.timeout_seconds)
        is_https = target.url.lower().startswith("https://")

        latency_ms:   float | None = None
        status_code:  int   | None = None
        reachable:    bool         = False
        error_msg:    str   | None = None
        ssl_days:     int   | None = None

        t0 = time.perf_counter()
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    target.url,
                    allow_redirects=True,
                    ssl=True,
                ) as resp:
                    latency_ms  = (time.perf_counter() - t0) * 1000
                    status_code = resp.status
                    reachable   = 200 <= resp.status < 400

                    # Lire un peu pour finaliser la connexion et accéder au transport
                    await resp.read()

                    # Récupération du certificat SSL via le transport aiohttp
                    if is_https:
                        ssl_days = _extract_ssl_days(resp)

        except aiohttp.ClientConnectorSSLError as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            error_msg  = f"SSL error: {exc}"
            log.warning("[network] SSL error %s : %s", target.name, exc)

        except asyncio.TimeoutError:
            latency_ms = net.timeout_seconds * 1000
            error_msg  = f"Timeout après {net.timeout_seconds}s"

        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            error_msg  = str(exc)[:200]

        # Fallback SSL via connexion asyncio dédiée (si aiohttp n'a pas fourni l'info)
        if is_https and ssl_days is None and reachable:
            parsed = urlparse(target.url)
            ssl_days = await _check_ssl_days_async(
                parsed.hostname or "",
                parsed.port or 443,
                timeout_s=5.0,
            )

        result = ProbeResult(
            target=target,
            reachable=reachable,
            status_code=status_code,
            latency_ms=latency_ms,
            ssl_days_remaining=ssl_days,
            error=error_msg,
        )

        # Stocker en mémoire
        self._latest[target.url] = result
        self._history[target.url].append(result.to_history_point())
        self._total_probes += 1

        # Persistance InfluxDB (non bloquant)
        asyncio.create_task(database.write_probe_result(result))

        # Évaluation des alertes
        await self._evaluate_alerts(target, result)

        log.debug(
            "[network] %s → %s  %sms  SSL=%s",
            target.name,
            "UP" if reachable else "DOWN",
            f"{latency_ms:.0f}" if latency_ms else "?",
            f"{ssl_days}j" if ssl_days is not None else "n/a",
        )

    # ── Alertes ───────────────────────────────────────────────────────────────

    async def _evaluate_alerts(self, target: NetworkTarget, result: ProbeResult) -> None:
        net = self._config.network

        # ── Alerte injoignable ────────────────────────────────────────────────
        if not result.reachable:
            if not self._cooldown.is_active("net", f"down:{target.url}"):
                log.warning(
                    "[network] 🔴 '%s' injoignable — %s",
                    target.name,
                    result.error or f"HTTP {result.status_code}",
                )
                await self._notifier.send_network_alert(
                    target_name=target.name,
                    url=target.url,
                    reason="down",
                    detail=(
                        f"La cible est injoignable.\n"
                        f"Erreur : {result.error or f'HTTP {result.status_code}'}"
                    ),
                    severity="critical",
                )
                self._cooldown.set("net", f"down:{target.url}", net.cooldown_minutes)
                self._total_alerts += 1

        # ── Alerte SSL expirant ───────────────────────────────────────────────
        ssl_d = result.ssl_days_remaining
        if ssl_d is not None and ssl_d < net.ssl_warning_days:
            key = f"ssl:{target.url}"
            if not self._cooldown.is_active("net", key):
                label = (
                    "expiré !" if ssl_d < 0
                    else f"expire dans {ssl_d} jour(s) !"
                )
                log.warning(
                    "[network] 🔐 Certificat SSL '%s' %s",
                    target.name, label,
                )
                await self._notifier.send_network_alert(
                    target_name=target.name,
                    url=target.url,
                    reason="ssl_expiry",
                    detail=(
                        f"Le certificat SSL de **{target.url}** {label}\n"
                        f"Seuil d'alerte : {net.ssl_warning_days} jour(s)."
                    ),
                    severity="critical",
                )
                self._cooldown.set("net", key, net.cooldown_minutes)
                self._total_alerts += 1

    # ── API mémoire ───────────────────────────────────────────────────────────

    def get_latest(self) -> list[dict[str, Any]]:
        """Retourne le dernier résultat + historique pour chaque cible."""
        output: list[dict[str, Any]] = []
        for target in self._config.network.targets:
            result = self._latest.get(target.url)
            if result:
                d = result.to_dict()
                d["history"] = list(self._history.get(target.url, []))
            else:
                # Cible pas encore sondée
                d = {
                    "name":               target.name,
                    "url":                target.url,
                    "status":             "pending",
                    "reachable":          None,
                    "status_code":        None,
                    "latency_ms":         None,
                    "ssl_days_remaining": None,
                    "ssl_status":         "na",
                    "error":              None,
                    "last_checked":       None,
                    "history":            [],
                }
            output.append(d)
        return output

    def stats(self) -> dict[str, Any]:
        return {
            "total_probes":   self._total_probes,
            "total_alerts":   self._total_alerts,
            "targets_count":  len(self._config.network.targets),
            "interval_s":     self._config.network.interval_seconds,
            "started_at":     self._started_at.isoformat() if self._started_at else None,
            "running":        self._task is not None and not self._task.done(),
        }


# ── Helpers SSL ───────────────────────────────────────────────────────────────

def _extract_ssl_days(resp: aiohttp.ClientResponse) -> int | None:
    """
    Tente d'extraire les jours restants du certificat SSL depuis le transport aiohttp.
    Retourne None si l'information n'est pas disponible.
    """
    try:
        conn = resp.connection
        if conn is None:
            return None
        transport = getattr(conn, "transport", None)
        if transport is None:
            return None
        ssl_obj = transport.get_extra_info("ssl_object")
        if ssl_obj is None:
            return None
        cert = ssl_obj.getpeercert()
        not_after = cert.get("notAfter", "")
        if not not_after:
            return None
        expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(
            tzinfo=timezone.utc
        )
        return (expiry - datetime.now(tz=timezone.utc)).days
    except Exception:
        return None


async def _check_ssl_days_async(
    hostname: str,
    port:     int   = 443,
    timeout_s: float = 5.0,
) -> int | None:
    """
    Vérifie l'expiration SSL via une connexion asyncio directe.
    Fallback utilisé quand aiohttp ne fournit pas l'objet SSL.
    """
    if not hostname:
        return None
    try:
        ctx = ssl.create_default_context()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(hostname, port, ssl=ctx),
            timeout=timeout_s,
        )
        ssl_obj = writer.transport.get_extra_info("ssl_object")
        days = None
        if ssl_obj:
            cert = ssl_obj.getpeercert()
            not_after = cert.get("notAfter", "")
            if not_after:
                expiry = datetime.strptime(
                    not_after, "%b %d %H:%M:%S %Y %Z"
                ).replace(tzinfo=timezone.utc)
                days = (expiry - datetime.now(tz=timezone.utc)).days
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return days
    except asyncio.TimeoutError:
        return None
    except ssl.SSLCertVerificationError:
        return -999   # Cert invalide (auto-signé, expiré, bad hostname)
    except Exception as exc:
        log.debug("[network] _check_ssl_days_async(%s:%d) : %s", hostname, port, exc)
        return None
