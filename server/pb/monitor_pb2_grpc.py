# -*- coding: utf-8 -*-
# Stubs gRPC pré-générés. Exécuter `make proto` pour régénérer.
#
# RPC disponibles :
#   StreamMetrics      — client-streaming MetricReport → StreamResponse
#   StreamDockerStatus — client-streaming DockerReport → StreamResponse

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
        self.StreamDockerStatus = channel.stream_unary(
            "/monitor.MonitoringService/StreamDockerStatus",
            request_serializer=_pb.DockerReport.SerializeToString,
            response_deserializer=_pb.StreamResponse.FromString,
        )


# ── Interface servicer ────────────────────────────────────────────────────────

class MonitoringServiceServicer:
    """Interface à implémenter côté serveur. Toutes les méthodes sont async."""

    async def StreamMetrics(self, request_iterator, context: grpc.aio.ServicerContext):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    async def StreamDockerStatus(self, request_iterator, context: grpc.aio.ServicerContext):
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
        "StreamDockerStatus": grpc.stream_unary_rpc_method_handler(
            servicer.StreamDockerStatus,
            request_deserializer=_pb.DockerReport.FromString,
            response_serializer=_pb.StreamResponse.SerializeToString,
        ),
    }
    # grpcio ≥ 1.50 : method_service_handler → method_handlers_generic_handler
    generic_handler = grpc.method_handlers_generic_handler(
        "monitor.MonitoringService", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))
