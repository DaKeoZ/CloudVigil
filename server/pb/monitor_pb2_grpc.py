# -*- coding: utf-8 -*-
# Stubs gRPC pré-générés. Exécuter `make proto` pour régénérer.
# RPC : StreamMetrics — client-streaming (agent → serveur)

from __future__ import annotations

import grpc
import grpc.aio

from server.pb import monitor_pb2 as _pb


# ── Stub client ───────────────────────────────────────────────────────────────

class MonitoringServiceStub:
    """Stub client du service MonitoringService."""

    def __init__(self, channel: grpc.Channel) -> None:
        self.StreamMetrics = channel.stream_unary(
            "/monitor.MonitoringService/StreamMetrics",
            request_serializer=_pb.MetricReport.SerializeToString,
            response_deserializer=_pb.StreamResponse.FromString,
        )


# ── Interface servicer ────────────────────────────────────────────────────────

class MonitoringServiceServicer:
    """Interface à implémenter côté serveur."""

    async def StreamMetrics(self, request_iterator, context: grpc.aio.ServicerContext):
        """
        Flux client-streaming : itère sur les MetricReport envoyés par l'agent
        et retourne un StreamResponse à la clôture.
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")


# ── Enregistrement serveur ────────────────────────────────────────────────────

def add_MonitoringServiceServicer_to_server(servicer: MonitoringServiceServicer, server) -> None:
    rpc_method_handlers = {
        "StreamMetrics": grpc.stream_unary_rpc_method_handler(
            servicer.StreamMetrics,
            request_deserializer=_pb.MetricReport.FromString,
            response_serializer=_pb.StreamResponse.SerializeToString,
        ),
    }
    generic_handler = grpc.method_service_handler(
        "monitor.MonitoringService", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers(
        "monitor.MonitoringService", rpc_method_handlers
    )


# ── Classe expérimentale (tests & CLI) ────────────────────────────────────────

class MonitoringService:
    """Helpers statiques pour les appels directs (tests / debug)."""

    @staticmethod
    def StreamMetrics(
        request_iterator,
        target: str,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure: bool = False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.stream_unary(
            request_iterator,
            target,
            "/monitor.MonitoringService/StreamMetrics",
            _pb.MetricReport.SerializeToString,
            _pb.StreamResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )
