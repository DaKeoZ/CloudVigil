"""Gestion de la connexion InfluxDB et healthcheck."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from influxdb_client import Point
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

from server.config import get_settings

if TYPE_CHECKING:
    from influxdb_client.client.write_api_async import WriteApiAsync

log = logging.getLogger(__name__)

# Singleton client — initialisé dans le lifespan FastAPI.
_client: InfluxDBClientAsync | None = None
_write_api: WriteApiAsync | None = None


async def init_db() -> None:
    """Ouvre la connexion InfluxDB et initialise le write API async."""
    global _client, _write_api
    settings = get_settings()

    _client = InfluxDBClientAsync(
        url=settings.influxdb_url,
        token=settings.influxdb_token,
        org=settings.influxdb_org,
    )
    _write_api = _client.write_api()
    log.info("InfluxDB connecté → %s (org=%s)", settings.influxdb_url, settings.influxdb_org)


async def close_db() -> None:
    """Ferme proprement le client InfluxDB."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
        log.info("InfluxDB déconnecté.")


async def query_metrics_all_nodes(minutes: int = 10) -> dict[str, list[dict]]:
    """
    Interroge InfluxDB pour obtenir l'historique des métriques système de tous les nœuds
    sur les `minutes` dernières minutes.
    Retourne un dict { node_id: [{ timestamp, cpu_usage, ram_usage, disk_usage }, ...] }.
    """
    if _client is None:
        return {}

    settings = get_settings()
    flux = f"""
from(bucket: "{settings.influxdb_bucket}")
  |> range(start: -{minutes}m)
  |> filter(fn: (r) => r._measurement == "system_metrics")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
"""
    try:
        query_api = _client.query_api()
        tables = await query_api.query(flux, org=settings.influxdb_org)
        nodes: dict[str, list] = {}
        for table in tables:
            for record in table.records:
                nid = record.values.get("node_id", "unknown")
                nodes.setdefault(nid, []).append(
                    {
                        "timestamp": record.get_time().isoformat(),
                        "cpu_usage": round(float(record.values.get("cpu_usage") or 0), 2),
                        "ram_usage": round(float(record.values.get("ram_usage") or 0), 2),
                        "disk_usage": round(float(record.values.get("disk_usage") or 0), 2),
                    }
                )
        return nodes
    except Exception as exc:
        log.warning("Requête InfluxDB échouée : %s", exc)
        return {}


async def health_check() -> bool:
    """Retourne True si InfluxDB répond correctement au ping."""
    if _client is None:
        return False
    try:
        return await _client.ping()
    except Exception as exc:
        log.warning("InfluxDB healthcheck échoué : %s", exc)
        return False


async def write_container_metric(
    node_id: str,
    container_id: str,
    container_name: str,
    image: str,
    cpu_percent: float,
    mem_usage_mb: float,
    mem_limit_mb: float,
    timestamp: datetime,
) -> None:
    """Écrit un Point de métriques Docker dans le bucket InfluxDB configuré."""
    if _write_api is None:
        raise RuntimeError("La base de données n'est pas initialisée.")

    settings = get_settings()

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    point = (
        Point("docker_containers")
        .tag("node_id", node_id)
        .tag("container_id", container_id)
        .tag("container_name", container_name)
        .tag("image", image)
        .field("cpu_percent", float(cpu_percent))
        .field("mem_usage_mb", float(mem_usage_mb))
        .field("mem_limit_mb", float(mem_limit_mb))
        .time(timestamp)
    )

    await _write_api.write(bucket=settings.influxdb_bucket, record=point)
    log.debug(
        "Point Docker écrit — node=%s container=%s cpu=%.1f%%",
        node_id, container_name, cpu_percent,
    )


async def write_metric(
    node_id: str,
    cpu_usage: float,
    ram_usage: float,
    disk_usage: float,
    timestamp: datetime,
) -> None:
    """Écrit un Point de métriques système dans le bucket InfluxDB configuré."""
    if _write_api is None:
        raise RuntimeError("La base de données n'est pas initialisée.")

    settings = get_settings()

    # Le timestamp doit être timezone-aware (UTC) pour InfluxDB v2.
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    point = (
        Point("system_metrics")
        .tag("node_id", node_id)
        .field("cpu_usage", float(cpu_usage))
        .field("ram_usage", float(ram_usage))
        .field("disk_usage", float(disk_usage))
        .time(timestamp)
    )

    await _write_api.write(bucket=settings.influxdb_bucket, record=point)
    log.debug(
        "Point écrit — node=%s cpu=%.1f%% ram=%.1f%% disk=%.1f%%",
        node_id, cpu_usage, ram_usage, disk_usage,
    )
