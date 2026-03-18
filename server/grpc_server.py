"""Implémentation async du service gRPC MonitoringService."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import grpc
import grpc.aio

from server import database, store
from server.pb import monitor_pb2, monitor_pb2_grpc

log = logging.getLogger(__name__)


class MonitoringServicer(monitor_pb2_grpc.MonitoringServiceServicer):
    """
    Servicer async qui gère deux flux client-streaming :
    - StreamMetrics      : métriques système → InfluxDB
    - StreamDockerStatus : état des conteneurs → store mémoire + InfluxDB
    """

    # ── StreamMetrics ─────────────────────────────────────────────────────────

    async def StreamMetrics(self, request_iterator, context: grpc.aio.ServicerContext):
        """Reçoit les MetricReport de l'agent et les persiste dans InfluxDB."""
        peer = context.peer()
        count = 0
        log.info("[grpc/metrics] connexion — peer=%s", peer)

        try:
            async for report in request_iterator:
                await database.write_metric(
                    node_id=report.node_id,
                    cpu_usage=report.cpu_usage,
                    ram_usage=report.ram_usage,
                    disk_usage=report.disk_usage,
                    timestamp=_proto_ts_to_dt(report.timestamp),
                )
                count += 1

        except Exception as exc:
            log.error("[grpc/metrics] erreur (peer=%s) : %s", peer, exc)
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

        log.info("[grpc/metrics] flux terminé — peer=%s rapports=%d", peer, count)
        return monitor_pb2.StreamResponse(status="ok")

    # ── StreamDockerStatus ────────────────────────────────────────────────────

    async def StreamDockerStatus(self, request_iterator, context: grpc.aio.ServicerContext):
        """
        Reçoit les DockerReport de l'agent :
        - Met à jour le store en mémoire (pour l'API /nodes/{id}/containers)
        - Écrit un Point InfluxDB par conteneur en cours d'exécution
        """
        peer = context.peer()
        count = 0
        log.info("[grpc/docker] connexion — peer=%s", peer)

        try:
            async for report in request_iterator:
                ts = _proto_ts_to_dt(report.timestamp)

                # Sérialiser les conteneurs pour le store
                containers_data = [
                    {
                        "id":           c.id,
                        "name":         c.name,
                        "image":        c.image,
                        "state":        c.state,
                        "cpu_percent":  round(c.cpu_percent, 2),
                        "mem_usage_mb": round(c.mem_usage_mb, 2),
                        "mem_limit_mb": round(c.mem_limit_mb, 2),
                    }
                    for c in report.containers
                ]
                await store.update_containers(report.node_id, containers_data, ts)

                # Persister les métriques de chaque conteneur running dans InfluxDB
                for c in report.containers:
                    if c.state == "running":
                        await database.write_container_metric(
                            node_id=report.node_id,
                            container_id=c.id,
                            container_name=c.name,
                            image=c.image,
                            cpu_percent=c.cpu_percent,
                            mem_usage_mb=c.mem_usage_mb,
                            mem_limit_mb=c.mem_limit_mb,
                            timestamp=ts,
                        )
                count += 1

        except Exception as exc:
            log.error("[grpc/docker] erreur (peer=%s) : %s", peer, exc)
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

        log.info("[grpc/docker] flux terminé — peer=%s rapports=%d", peer, count)
        return monitor_pb2.StreamResponse(status="ok")


def _proto_ts_to_dt(ts) -> datetime:
    """Convertit un google.protobuf.Timestamp en datetime UTC timezone-aware."""
    return datetime.fromtimestamp(
        ts.seconds + ts.nanos / 1e9,
        tz=timezone.utc,
    )
