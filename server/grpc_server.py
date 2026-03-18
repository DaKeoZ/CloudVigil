"""Implémentation async du service gRPC MonitoringService."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import grpc
import grpc.aio

from server import database
from server.pb import monitor_pb2, monitor_pb2_grpc

log = logging.getLogger(__name__)


class MonitoringServicer(monitor_pb2_grpc.MonitoringServiceServicer):
    """Servicer async : reçoit le flux de métriques de chaque agent et persiste en InfluxDB."""

    async def StreamMetrics(
        self,
        request_iterator: grpc.aio.ServicerContext,
        context: grpc.aio.ServicerContext,
    ) -> monitor_pb2.StreamResponse:
        """
        Flux client-streaming : l'agent envoie des MetricReport en continu.
        Le serveur écrit chaque rapport dans InfluxDB et répond une fois le flux terminé.
        """
        peer = context.peer()
        count = 0
        log.info("[grpc] nouvelle connexion — peer=%s", peer)

        try:
            async for report in request_iterator:
                ts = _proto_timestamp_to_datetime(report.timestamp)

                await database.write_metric(
                    node_id=report.node_id,
                    cpu_usage=report.cpu_usage,
                    ram_usage=report.ram_usage,
                    disk_usage=report.disk_usage,
                    timestamp=ts,
                )
                count += 1

        except Exception as exc:
            log.error("[grpc] erreur pendant le flux (peer=%s) : %s", peer, exc)
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

        log.info("[grpc] flux terminé — peer=%s rapports_reçus=%d", peer, count)
        return monitor_pb2.StreamResponse(status="ok")


def _proto_timestamp_to_datetime(ts) -> datetime:
    """Convertit un google.protobuf.Timestamp en datetime UTC timezone-aware."""
    return datetime.fromtimestamp(
        ts.seconds + ts.nanos / 1e9,
        tz=timezone.utc,
    )
