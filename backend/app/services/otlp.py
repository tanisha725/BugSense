"""OpenTelemetry receiver: turns OTLP messages into rows in the database.

OpenTelemetry (OTel) is the industry standard for telemetry. A program that
uses the OTel SDK sends three kinds of data with the OTLP protocol:

  traces   one request, step by step (spans), across services
  metrics  numbers measured over time (request durations, CPU, memory)
  logs     log records, linked to the trace they happened in

BugSense receives them exactly like an OpenTelemetry Collector or a cloud
monitoring service would (Huawei Cloud AOM/APM accept the same protocol).
OTLP over HTTP comes in two encodings, and both are accepted:

  application/x-protobuf  binary, what the OTel SDKs send by default
  application/json        the same message written as JSON (IDs in hex)

Which project the data belongs to comes from the resource attribute
"service.namespace" (the application the services are part of).
"""

import base64
import gzip
import json
import threading
import time
from datetime import datetime, timezone

from google.protobuf import json_format
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
    ExportLogsServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.proto.metrics.v1 import metrics_pb2

from app.models import Log, MetricPoint, Span
from app.services.incident_detector import detect_incidents
from app.services.log_parser import find_error_type, find_request_id
from app.services.projects import find_or_create_project

DEFAULT_PROJECT = "OpenTelemetry"
DETECT_EVERY = 3  # seconds: incident detection runs at most this often per project

SIGNALS = {
    "traces": (ExportTraceServiceRequest, ExportTraceServiceResponse),
    "metrics": (ExportMetricsServiceRequest, ExportMetricsServiceResponse),
    "logs": (ExportLogsServiceRequest, ExportLogsServiceResponse),
}

# OTLP/JSON writes these IDs as hex, protobuf's JSON reader expects base64
ID_FIELDS = {"traceId", "spanId", "parentSpanId"}


class OtlpError(ValueError):
    """The message could not be read. The route answers 400."""


# ---------- Reading the message ----------


def _hex_ids_to_base64(value):
    if isinstance(value, dict):
        return {
            key: base64.b64encode(bytes.fromhex(item)).decode()
            if key in ID_FIELDS and isinstance(item, str) and item
            else _hex_ids_to_base64(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_hex_ids_to_base64(item) for item in value]
    return value


def decode(signal, body, content_type, content_encoding=None):
    """Reads an OTLP request body into its protobuf message."""
    request_class, _ = SIGNALS[signal]
    if (content_encoding or "").lower() == "gzip":
        try:
            body = gzip.decompress(body)
        except OSError as problem:
            raise OtlpError("Body is not valid gzip") from problem
    message = request_class()
    media_type = (content_type or "").split(";")[0].strip().lower()
    try:
        if media_type == "application/json":
            data = _hex_ids_to_base64(json.loads(body or b"{}"))
            json_format.ParseDict(data, message, ignore_unknown_fields=True)
        elif media_type in ("application/x-protobuf", "application/protobuf"):
            message.ParseFromString(body)
        else:
            raise OtlpError("Content-Type must be application/x-protobuf or application/json")
    except (DecodeError, json_format.ParseError, ValueError) as problem:
        if isinstance(problem, OtlpError):
            raise
        raise OtlpError(f"Could not read the OTLP {signal} message: {problem}") from problem
    return message


def encode_response(signal, content_type):
    """An empty "everything accepted" reply, in the encoding of the request."""
    _, response_class = SIGNALS[signal]
    if (content_type or "").startswith("application/json"):
        return b"{}", "application/json"
    return response_class().SerializeToString(), "application/x-protobuf"


# ---------- Small helpers ----------


def any_value(value):
    """An OTel AnyValue (string, number, list, ...) as a plain Python value."""
    which = value.WhichOneof("value")
    if which is None:
        return None
    if which == "array_value":
        return [any_value(item) for item in value.array_value.values]
    if which == "kvlist_value":
        return attributes(value.kvlist_value.values)
    if which == "bytes_value":
        return value.bytes_value.hex()
    return getattr(value, which)


def attributes(key_values):
    return {item.key: any_value(item.value) for item in key_values}


def from_nanos(nanos):
    return datetime.fromtimestamp(nanos / 1e9, tz=timezone.utc)


def enum_name(prefix, name):
    """'SPAN_KIND_SERVER' -> 'SERVER'"""
    return name.removeprefix(prefix)


_project_ids = {}
_project_lock = threading.Lock()


def project_for(db, resource):
    """The project of a resource, from its service.namespace attribute."""
    name = str(resource.get("service.namespace") or DEFAULT_PROJECT)[:100]
    with _project_lock:
        if name not in _project_ids:
            project = find_or_create_project(
                db, name, "Telemetry received over OpenTelemetry (OTLP)."
            )
            db.commit()
            _project_ids[name] = project.id
        return _project_ids[name]


def service_of(resource):
    return str(resource.get("service.name") or "unknown_service")[:100]


# ---------- Storing each signal ----------


def store_traces(db, message):
    """Saves every span. Returns {project_id: number of spans}."""
    counts = {}
    for resource_spans in message.resource_spans:
        resource = attributes(resource_spans.resource.attributes)
        project_id = project_for(db, resource)
        service = service_of(resource)
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                start, end = span.start_time_unix_nano, span.end_time_unix_nano
                db.add(
                    Span(
                        project_id=project_id,
                        trace_id=span.trace_id.hex(),
                        span_id=span.span_id.hex(),
                        parent_span_id=span.parent_span_id.hex() or None,
                        service=service,
                        name=span.name[:255] or "(unnamed)",
                        kind=enum_name("SPAN_KIND_", span.SpanKind.Name(span.kind)),
                        start_time=from_nanos(start),
                        end_time=from_nanos(end),
                        duration_ms=max(0, end - start) / 1e6,
                        status=enum_name("STATUS_CODE_", span.status.StatusCode.Name(span.status.code)),
                        status_message=span.status.message or None,
                        attributes=attributes(span.attributes),
                    )
                )
                counts[project_id] = counts.get(project_id, 0) + 1
    db.commit()
    return counts


def _point_value(point):
    return float(getattr(point, point.WhichOneof("value") or "as_double", 0))


def store_metrics(db, message):
    """Saves gauges, sums and histograms. Returns {project_id: number of points}."""
    counts = {}
    for resource_metrics in message.resource_metrics:
        resource = attributes(resource_metrics.resource.attributes)
        project_id = project_for(db, resource)
        service = service_of(resource)
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                kind = metric.WhichOneof("data")
                if kind not in ("gauge", "sum", "histogram"):
                    continue  # exponential histograms and summaries are not used by BugSense
                data = getattr(metric, kind)
                temporality = None
                if kind != "gauge":
                    temporality = enum_name(
                        "AGGREGATION_TEMPORALITY_",
                        metrics_pb2.AggregationTemporality.Name(data.aggregation_temporality),
                    )
                for point in data.data_points:
                    row = MetricPoint(
                        project_id=project_id,
                        service=service,
                        name=metric.name[:255],
                        kind=kind,
                        unit=metric.unit[:50] or None,
                        temporality=temporality,
                        time=from_nanos(point.time_unix_nano),
                        attributes=attributes(point.attributes),
                    )
                    if kind == "histogram":
                        row.value = point.sum
                        row.count = point.count
                        row.bounds = list(point.explicit_bounds)
                        row.bucket_counts = [int(count) for count in point.bucket_counts]
                    else:
                        row.value = _point_value(point)
                    db.add(row)
                    counts[project_id] = counts.get(project_id, 0) + 1
    db.commit()
    return counts


def severity_of(record):
    """OTel severity (text or number 1-24) as a BugSense severity."""
    text = (record.severity_text or "").upper()
    if text in ("DEBUG", "INFO", "ERROR", "CRITICAL"):
        return text
    if text in ("WARN", "WARNING"):
        return "WARNING"
    if text in ("FATAL", "PANIC"):
        return "CRITICAL"
    number = record.severity_number
    if number == 0:
        return None
    for limit, level in ((8, "DEBUG"), (12, "INFO"), (16, "WARNING"), (20, "ERROR")):
        if number <= limit:
            return level
    return "CRITICAL"


def store_logs(db, message):
    """Saves log records as BugSense logs. Returns {project_id: number of logs}."""
    counts = {}
    for resource_logs in message.resource_logs:
        resource = attributes(resource_logs.resource.attributes)
        project_id = project_for(db, resource)
        service = service_of(resource)
        for scope_logs in resource_logs.scope_logs:
            for record in scope_logs.log_records:
                extra = attributes(record.attributes)
                body = any_value(record.body)
                body = body if isinstance(body, str) else json.dumps(body)
                moment = from_nanos(record.time_unix_nano or record.observed_time_unix_nano or time.time_ns())
                severity = severity_of(record)
                db.add(
                    Log(
                        project_id=project_id,
                        raw=f"{moment.isoformat()} {severity or '-'} [{service}] {body}",
                        timestamp=moment,
                        severity=severity,
                        service=service,
                        error_type=str(extra.get("exception.type") or find_error_type(body) or "")[:100] or None,
                        message=body,
                        request_id=str(extra.get("request_id") or find_request_id(body) or "")[:100] or None,
                        trace_id=record.trace_id.hex() or None,
                        stack_trace=extra.get("exception.stacktrace"),
                    )
                )
                counts[project_id] = counts.get(project_id, 0) + 1
    db.commit()
    return counts


STORE = {"traces": store_traces, "metrics": store_metrics, "logs": store_logs}

_last_detection = {}


def detect_soon(db, project_id):
    """Runs incident detection for a project, at most every DETECT_EVERY seconds."""
    now = time.time()
    if now - _last_detection.get(project_id, 0) >= DETECT_EVERY:
        _last_detection[project_id] = now
        detect_incidents(db, project_id)
