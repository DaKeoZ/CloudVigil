# -*- coding: utf-8 -*-
# Stubs pré-générés. Exécuter `make proto` pour régénérer depuis proto/monitor.proto.
#
# Ce fichier construit le FileDescriptorProto programmatiquement (sans bytes raw)
# afin d'éviter toute dérive manuelle entre le proto source et les stubs.

from __future__ import annotations

from google.protobuf import descriptor_pb2 as _descriptor_pb2
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
from google.protobuf import timestamp_pb2 as _timestamp_pb2  # noqa: F401 — enregistre Timestamp dans le pool

_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC, 5, 27, 0, "", "monitor.proto"
)

_sym_db = _symbol_database.Default()

# TYPE_* et LABEL_* constants (wire format protobuf)
_STRING  = 9
_FLOAT   = 2
_UINT32  = 13
_MESSAGE = 11
_OPTIONAL = 1


def _make_file_descriptor_bytes() -> bytes:
    """Construit et sérialise le FileDescriptorProto correspondant à monitor.proto."""
    fdp = _descriptor_pb2.FileDescriptorProto(
        name="monitor.proto",
        package="monitor",
        syntax="proto3",
        dependency=["google/protobuf/timestamp.proto"],
    )
    fdp.options.CopyFrom(
        _descriptor_pb2.FileOptions(go_package="github.com/cloudvigil/agent/pb;pb")
    )

    def _f(msg, name, number, ftype, json_name="", type_name=""):
        field = msg.field.add()
        field.name = name
        field.number = number
        field.type = ftype
        field.label = _OPTIONAL
        field.json_name = json_name or name
        if type_name:
            field.type_name = type_name

    # ── MetricReport ──────────────────────────────────────────────────────────
    mr = fdp.message_type.add()
    mr.name = "MetricReport"
    _f(mr, "node_id",    1, _STRING,  json_name="nodeId")
    _f(mr, "cpu_usage",  2, _FLOAT,   json_name="cpuUsage")
    _f(mr, "ram_usage",  3, _FLOAT,   json_name="ramUsage")
    _f(mr, "disk_usage", 4, _FLOAT,   json_name="diskUsage")
    _f(mr, "timestamp",  5, _MESSAGE, json_name="timestamp",
       type_name=".google.protobuf.Timestamp")

    # ── StreamRequest ─────────────────────────────────────────────────────────
    sr = fdp.message_type.add()
    sr.name = "StreamRequest"
    _f(sr, "node_id",          1, _STRING, json_name="nodeId")
    _f(sr, "interval_seconds", 2, _UINT32, json_name="intervalSeconds")

    # ── StreamResponse ────────────────────────────────────────────────────────
    resp = fdp.message_type.add()
    resp.name = "StreamResponse"
    _f(resp, "status", 1, _STRING, json_name="status")

    # ── MonitoringService ─────────────────────────────────────────────────────
    svc = fdp.service.add()
    svc.name = "MonitoringService"
    method = svc.method.add()
    method.name = "StreamMetrics"
    method.input_type = ".monitor.MetricReport"
    method.output_type = ".monitor.StreamResponse"
    method.client_streaming = True
    method.server_streaming = False

    return fdp.SerializeToString()


DESCRIPTOR = _descriptor_pool.Default().Add(_make_file_descriptor_bytes())

_globals = globals()
_builder.BuildMessageAndEnumTypes(_globals, DESCRIPTOR)
_builder.BuildTopDescriptorsAndMessages(_globals, "monitor_pb2", _globals)

if not __import__("google.protobuf.descriptor", fromlist=["_USE_C_DESCRIPTORS"])._USE_C_DESCRIPTORS:
    DESCRIPTOR._options = None
    DESCRIPTOR._serialized_options = b"\n\x1cgithub.com/cloudvigil/agent/pb;pb"
