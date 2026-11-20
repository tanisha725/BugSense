"""OpenTelemetry: receiving OTLP (protobuf and JSON), and what is calculated from it."""

import gzip
import time

from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from sqlalchemy import select

from app.models import Log, MetricPoint, Project, Span
from app.services import telemetry

TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"
NAMESPACE = {"key": "service.namespace", "value": {"stringValue": "Test shop"}}


def nanos(seconds_ago=0):
    return time.time_ns() - int(seconds_ago * 1e9)


def resource(service):
    return {"attributes": [{"key": "service.name", "value": {"stringValue": service}}, NAMESPACE]}


def span(trace_id, span_id, name, kind, duration_ms, parent=None, error=None, seconds_ago=1):
    start = nanos(seconds_ago)
    item = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": kind,
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(start + int(duration_ms * 1e6)),
        "attributes": [{"key": "http.route", "value": {"stringValue": "/checkout"}}],
        "status": {"code": 2, "message": error} if error else {},
    }
    if parent:
        item["parentSpanId"] = parent
    return item


def send_traces(client, service, spans):
    body = {"resourceSpans": [{"resource": resource(service), "scopeSpans": [{"spans": spans}]}]}
    return client.post("/v1/traces", json=body)


def checkout_trace(client, trace_id, failing=False, api_ms=20):
    """One checkout across three services: web -> api -> db, in OTLP/JSON."""
    error = "connection refused" if failing else None
    send_traces(client, "shop-web", [span(trace_id, "a" * 16, "GET /checkout", 3, api_ms + 5, error=error)])
    send_traces(client, "shop-api", [
        span(trace_id, "b" * 16, "GET /checkout", 2, api_ms, parent="a" * 16, error=error),
        span(trace_id, "c" * 16, "shop-db SELECT", 3, api_ms - 2, parent="b" * 16, error=error),
    ])
    if not failing:
        send_traces(client, "shop-db", [span(trace_id, "d" * 16, "SELECT order", 2, api_ms - 4, parent="c" * 16)])


def test_otlp_json_traces_are_stored_as_one_tree(client, session_factory):
    checkout_trace(client, TRACE)

    with session_factory() as db:
        spans = db.scalars(select(Span).where(Span.trace_id == TRACE)).all()
    assert {item.service for item in spans} == {"shop-web", "shop-api", "shop-db"}

    trace = client.get(f"/telemetry/traces/{TRACE}").json()
    depths = {(item["service"], item["name"]): item["depth"] for item in trace["spans"]}
    assert depths[("shop-web", "GET /checkout")] == 0
    assert depths[("shop-db", "SELECT order")] == 3


def test_otlp_protobuf_and_gzip_are_accepted(client, session_factory):
    message = ExportTraceServiceRequest()
    resource_spans = message.resource_spans.add()
    attribute = resource_spans.resource.attributes.add()
    attribute.key, attribute.value.string_value = "service.name", "proto-svc"
    item = resource_spans.scope_spans.add().spans.add()
    item.trace_id, item.span_id = bytes.fromhex(TRACE), bytes.fromhex("e" * 16)
    item.name, item.kind = "work", 2
    item.start_time_unix_nano, item.end_time_unix_nano = nanos(1), nanos(1) + 5_000_000

    response = client.post(
        "/v1/traces",
        content=gzip.compress(message.SerializeToString()),
        headers={"Content-Type": "application/x-protobuf", "Content-Encoding": "gzip"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-protobuf"
    with session_factory() as db:
        stored = db.scalars(select(Span).where(Span.service == "proto-svc")).one()
        assert stored.kind == "SERVER" and round(stored.duration_ms) == 5
        # No service.namespace: the data goes into the default project
        assert db.get(Project, stored.project_id).name == "OpenTelemetry"


def test_bad_otlp_messages_are_refused(client):
    assert client.post("/v1/traces", content=b"x", headers={"Content-Type": "text/plain"}).status_code == 400
    assert client.post("/v1/traces", content=b"\xff\x00", headers={"Content-Type": "application/x-protobuf"}).status_code == 400
    assert client.post("/v1/metrics", content=b"{bad json", headers={"Content-Type": "application/json"}).status_code == 400


def test_red_numbers_and_percentiles(client):
    for index in range(10):
        checkout_trace(client, f"{index:032x}", failing=index < 3, api_ms=10 * (index + 1))

    overview = client.get("/telemetry/services", params={"window_minutes": 5}).json()
    api = next(item for item in overview["services"] if item["service"] == "shop-api")
    assert api["requests"] == 10
    assert api["errors"] == 3 and api["error_rate"] == 0.3
    assert api["latency_ms"]["p50"] == 50.0  # nearest rank: the 5th of 10 durations
    assert api["latency_ms"]["max"] == 100.0

    only_db = client.get("/telemetry/services", params={"service": "shop-db"}).json()["services"]
    assert [item["service"] for item in only_db] == ["shop-db"]


def test_trace_search_filters(client):
    checkout_trace(client, "1" * 32, failing=True)
    checkout_trace(client, "2" * 32, api_ms=900)

    assert [item["trace_id"] for item in client.get("/telemetry/traces", params={"status": "ERROR"}).json()] == ["1" * 32]
    assert [item["trace_id"] for item in client.get("/telemetry/traces", params={"status": "OK"}).json()] == ["2" * 32]
    slow = client.get("/telemetry/traces", params={"min_duration_ms": 500}).json()
    assert [item["trace_id"] for item in slow] == ["2" * 32]
    assert len(client.get("/telemetry/traces", params={"limit": 1}).json()) == 1
    # The failed trace has no shop-db span
    assert client.get("/telemetry/traces", params={"service": "shop-db"}).json()[0]["trace_id"] == "2" * 32
    assert client.get("/telemetry/traces", params={"status": "maybe"}).status_code == 422


def test_metrics_gauge_sum_and_histogram(client, session_factory):
    point_time = str(nanos(2))
    body = {"resourceMetrics": [{"resource": resource("shop-api"), "scopeMetrics": [{"metrics": [
        {"name": "process.memory.usage", "unit": "By",
         "gauge": {"dataPoints": [{"timeUnixNano": point_time, "asInt": "52000000"}]}},
        {"name": "process.cpu.time", "unit": "s",
         "sum": {"aggregationTemporality": 1, "isMonotonic": True,
                 "dataPoints": [{"timeUnixNano": point_time, "asDouble": 3.0}]}},
        {"name": "http.server.request.duration", "unit": "s",
         "histogram": {"aggregationTemporality": 1, "dataPoints": [{
             "timeUnixNano": point_time, "count": "10", "sum": 4.0,
             "explicitBounds": [0.1, 0.5, 1.0], "bucketCounts": ["2", "6", "1", "1"]}]}},
    ]}]}]}
    assert client.post("/v1/metrics", json=body).status_code == 200

    with session_factory() as db:
        assert db.scalar(select(MetricPoint).where(MetricPoint.name == "process.cpu.time")).temporality == "DELTA"

    overview = client.get("/telemetry/services", params={"window_minutes": 1}).json()["services"][0]
    assert overview["memory_mb"] == 52.0
    assert overview["cpu_percent"] == 5.0  # 3 CPU seconds in 60 seconds

    def series(aggregation):
        points = client.get("/telemetry/series", params={
            "metric": "http.server.request.duration", "service": "shop-api",
            "window_minutes": 1, "step_seconds": 60, "aggregation": aggregation,
        }).json()["points"]
        return [point["value"] for point in points if point["value"] is not None][0]

    assert series("count") == 10
    assert series("avg") == 0.4
    assert series("p50") == 0.5  # the 5th of 10 measurements is in the (0.1, 0.5] bucket
    assert series("p95") == 1.0
    names = {item["name"] for item in client.get("/telemetry/metrics").json()}
    assert {"process.cpu.time", "http.server.request.duration", "requests", "latency"} <= names


def test_cumulative_counters_become_increases(client):
    def counter(seconds_ago, value):
        return {"name": "jobs.done", "sum": {"aggregationTemporality": 2, "isMonotonic": True,
                "dataPoints": [{"timeUnixNano": str(nanos(seconds_ago)), "asInt": str(value)}]}}

    for seconds_ago, value in ((30, 100), (20, 110), (10, 125)):
        body = {"resourceMetrics": [{"resource": resource("worker"), "scopeMetrics": [{"metrics": [counter(seconds_ago, value)]}]}]}
        client.post("/v1/metrics", json=body)

    points = client.get("/telemetry/series", params={
        "metric": "jobs.done", "window_minutes": 1, "step_seconds": 60, "aggregation": "sum"}).json()["points"]
    assert [point["value"] for point in points if point["value"] is not None] == [25]


def test_otlp_logs_become_bugsense_logs(client, session_factory):
    body = {"resourceLogs": [{"resource": resource("shop-api"), "scopeLogs": [{"logRecords": [{
        "timeUnixNano": str(nanos(1)), "severityNumber": 17, "body": {"stringValue": "db refused"},
        "traceId": TRACE,
        "attributes": [{"key": "exception.type", "value": {"stringValue": "OperationalError"}},
                       {"key": "request_id", "value": {"stringValue": "req-1"}}],
    }]}]}]}
    assert client.post("/v1/logs", json=body).status_code == 200

    with session_factory() as db:
        log = db.scalars(select(Log)).one()
        assert (log.severity, log.service, log.error_type, log.request_id, log.trace_id) == (
            "ERROR", "shop-api", "OperationalError", "req-1", TRACE
        )
        assert log.project.name == "Test shop"


def test_high_error_rate_becomes_an_alert_log(client, session_factory):
    for index in range(6):
        checkout_trace(client, f"{index + 100:032x}", failing=True)

    with session_factory() as db:
        project_id = db.scalar(select(Span.project_id))
        telemetry.reset_alerts()
        new = telemetry.check_alerts(db, project_id, force=True)
        kinds = {(log.service, log.error_type) for log in new}
        # A second check does not repeat an alert that is still on
        again = telemetry.check_alerts(db, project_id, force=True)
    assert ("shop-api", "HighErrorRate") in kinds
    assert again == []


def test_parameter_limits_are_enforced(client):
    assert client.get("/telemetry/services", params={"window_minutes": 0}).status_code == 422
    assert client.get("/telemetry/series", params={"metric": "x", "step_seconds": 1}).status_code == 422
    assert client.get("/telemetry/series", params={"metric": "x", "aggregation": "median"}).status_code == 422
    assert client.get("/telemetry/traces/not-a-trace").status_code == 422
    assert client.get(f"/telemetry/traces/{'0' * 32}").status_code == 404
