"""
CloudVigil — Serveur gRPC de réception des métriques agents.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from concurrent import futures

import grpc

# Ajout du chemin racine pour résoudre les imports absolus hors venv
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from server.pb import monitor_pb2, monitor_pb2_grpc  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

LISTEN_ADDR = os.getenv("CLOUDVIGIL_LISTEN", "[::]:50051")
MAX_WORKERS = int(os.getenv("CLOUDVIGIL_WORKERS", "10"))


class MonitoringServicer(monitor_pb2_grpc.MonitoringServiceServicer):
    """Implémentation serveur du service MonitoringService."""

    def StreamMetrics(self, request: monitor_pb2.StreamRequest, context: grpc.ServicerContext):
        node = request.node_id
        interval = request.interval_seconds or 5
        log.info("Flux ouvert — node_id=%s interval=%ds", node, interval)

        try:
            while context.is_active():
                # Boucle passive : l'agent est côté client et envoie les données.
                # En mode server-streaming, le serveur renverrait ici les rapports
                # s'il était producteur. Dans notre architecture l'agent EST producteur
                # (client-streaming ou bidirectionnel à terme). Ce stub retourne une
                # réponse vide pour valider la connexion.
                pass
        finally:
            log.info("Flux fermé — node_id=%s", node)

        return


def serve() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=MAX_WORKERS))
    monitor_pb2_grpc.add_MonitoringServiceServicer_to_server(MonitoringServicer(), server)
    server.add_insecure_port(LISTEN_ADDR)
    server.start()
    log.info("Serveur CloudVigil démarré sur %s", LISTEN_ADDR)

    def _graceful_shutdown(sig, frame):  # noqa: ANN001
        log.info("Signal %s reçu — arrêt gracieux…", sig)
        server.stop(grace=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
