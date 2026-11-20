"""Telemetry calculated from uploaded logs: traces from request IDs, latency
from durations in the text, and log activity per minute."""

from sqlalchemy import select

from app.models import MetricPoint, Span
from app.services import log_telemetry

CHECKOUT_LOGS = """2026-11-17 10:00:00 INFO [shop-web] Checkout page loaded in 25 ms request_id=req-1
2026-11-17 10:00:00 INFO [shop-api] GET /checkout 200 in 19 ms request_id=req-1
2026-11-17 10:00:01 ERROR [shop-api] OperationalError: connection to shop-db failed request_id=req-2
2026-11-17 10:00:01 ERROR [shop-web] Checkout page failed: upstream returned 503 request_id=req-2
2026-11-17 10:00:02 ERROR [shop-api] OperationalError: connection to shop-db failed request_id=req-3
2026-11-17 10:00:02 ERROR [shop-web] Checkout page failed: upstream returned 503 request_id=req-3
2026-11-17 10:01:30 WARNING [shop-api] GET /checkout 200 in 2.4 s request_id=req-4
2026-11-17 10:01:31 INFO [cron] nightly job started
"""

# The logs are from 17 Nov 2026 10:00-10:02 local time; look at exactly that time
PAST_WINDOW = {"window_minutes": 5, "until": "2026-11-17T10:03:00"}


def upload(client, text=CHECKOUT_LOGS):
    assert client.post("/logs/text", json={"text": text}).status_code == 201
    return client.get("/projects").json()[0]["id"]


def test_durations_are_read_from_log_text():
    assert log_telemetry.duration_ms("GET /checkout 200 in 19 ms") == 19
    assert log_telemetry.duration_ms("request took 2.4 s") == 2400
    assert log_telemetry.duration_ms("duration=120ms") == 120
    assert log_telemetry.duration_ms("latency: 45 ms") == 45
    assert log_telemetry.duration_ms("Gateway request timed out after 3000 ms") == 3000
    assert log_telemetry.duration_ms('"GET /v2/servers HTTP/1.1" status: 200 len: 1916 time: 0.2717581') == 271.7581
    assert log_telemetry.duration_ms("Database connection refused") is None


def test_upload_creates_traces_from_request_ids(client, session_factory):
    upload(client)
    with session_factory() as db:
        spans = db.scalars(select(Span)).all()
        assert {span.source for span in spans} == {"logs"}
        # 4 requests: two services each for req-1..3, one for req-4
        assert len({span.trace_id for span in spans}) == 4 and len(spans) == 7
        first = {span.service: span for span in spans if span.attributes["request_id"] == "req-1"}
        assert first["shop-web"].duration_ms == 25 and first["shop-api"].duration_ms == 19
        # The service that logged the request first is the root; the other is its child
        assert first["shop-web"].parent_span_id is None
        assert first["shop-api"].parent_span_id == first["shop-web"].span_id
        failed = [span for span in spans if span.status == "ERROR"]
        assert len(failed) == 4 and "connection to shop-db" in failed[0].status_message


def test_telemetry_page_works_for_uploaded_logs(client):
    project = upload(client)

    overview = client.get("/telemetry/services", params={"project_id": project, **PAST_WINDOW}).json()
    by_name = {item["service"]: item for item in overview["services"]}
    api = by_name["shop-api"]
    assert api["source"] == "logs"
    assert api["requests"] == 4 and api["errors"] == 2 and api["error_rate"] == 0.5
    assert api["latency_ms"]["max"] == 2400.0
    # A service without request IDs still gets log activity
    assert by_name["cron"]["requests"] == 0 and by_name["cron"]["log_count"] == 1
    assert by_name["shop-web"]["log_error_rate"] == 0.6667

    traces = client.get("/telemetry/traces", params={"project_id": project, "status": "ERROR", **PAST_WINDOW}).json()
    assert len(traces) == 2
    tree = client.get(f"/telemetry/traces/{traces[0]['trace_id']}").json()
    assert {span["service"] for span in tree["spans"]} == {"shop-web", "shop-api"}

    series = client.get("/telemetry/series", params={
        "project_id": project, "metric": "log.records", "aggregation": "sum", "step_seconds": 60, **PAST_WINDOW,
    }).json()
    assert sum(point["value"] or 0 for point in series["points"]) == 8

    span = client.get("/telemetry/range", params={"project_id": project}).json()
    assert span["first"].startswith("2026-11-17") and span["minutes"] >= 2


def test_telemetry_follows_the_logs(client, session_factory):
    project = upload(client)
    log_id = client.get("/logs", params={"request_id": "req-4"}).json()[0]["id"]
    client.delete(f"/logs/{log_id}")
    with session_factory() as db:
        assert not db.scalars(select(Span).where(Span.attributes["request_id"].as_string() == "req-4")).all()

    client.delete("/logs", params={"project_id": project})
    with session_factory() as db:
        assert db.scalars(select(Span)).all() == [] and db.scalars(select(MetricPoint)).all() == []


def test_measured_services_are_not_counted_twice(client, session_factory):
    project = upload(client)
    # shop-api also sends real OpenTelemetry spans into the same project
    with session_factory() as db:
        db.add(Span(project_id=project, trace_id="f" * 32, span_id="f" * 16, service="shop-api", name="real",
                    kind="SERVER", start_time=db.scalar(select(Span.start_time)),
                    end_time=db.scalar(select(Span.end_time)), duration_ms=5, source="otel"))
        db.commit()
        result = log_telemetry.rebuild(db, project)
        calculated = {span.service for span in db.scalars(select(Span).where(Span.source == "logs"))}
    assert "shop-api" not in calculated and result["spans"] == 3


def test_rebuild_endpoint(client):
    project = upload(client)
    result = client.post("/telemetry/from-logs", params={"project_id": project}).json()
    # metric points: one per service, severity and minute (6 such groups)
    assert result == {"logs": 8, "spans": 7, "traces": 4, "metric_points": 6}
    assert client.post("/telemetry/from-logs", params={"project_id": 999}).status_code == 404
    assert client.post("/telemetry/from-logs").status_code == 422
