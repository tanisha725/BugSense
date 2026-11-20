"""Investigation tools: every parameter of every tool really filters, and bad
parameters are refused with a clear message."""

import time
from datetime import datetime, timedelta

import pytest

from app.services import tools

TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"

LOGS = f"""2026-11-17 10:00:00 INFO [shop-api] GET /checkout 200 in 12 ms request_id=req-0
2026-11-17 10:00:01 ERROR [shop-api] OperationalError: connection to shop-db failed request_id=req-1 trace_id={TRACE}
2026-11-17 10:00:01 ERROR [shop-web] Checkout page failed: upstream returned 503 request_id=req-1
2026-11-17 10:00:02 ERROR [shop-api] OperationalError: connection to shop-db failed request_id=req-2
2026-11-17 10:00:02 WARNING [shop-web] slow page request_id=req-2
2026-11-17 10:00:03 CRITICAL [shop-web] TimeoutError: shop-api did not answer request_id=req-3
"""


def run(client, name, **parameters):
    response = client.post(f"/tools/{name}", json=parameters)
    assert response.status_code == 200, response.text
    return response.json()["result"]


@pytest.fixture
def project(client):
    client.post("/logs/text", json={"text": LOGS})
    return client.get("/projects").json()[0]["id"]


def incident_id(client):
    return client.get("/incidents").json()[0]["id"]


def test_every_tool_is_listed_with_a_schema(client):
    listed = client.get("/tools").json()
    assert [tool["name"] for tool in listed] == list(tools.TOOLS)
    for tool in listed:
        schema = tool["parameters"]
        assert schema["type"] == "object" and tool["description"]
        assert schema.get("additionalProperties") is False
        # Every parameter has a description, so the AI knows what it does
        assert all("description" in field for field in schema["properties"].values()), tool["name"]


def test_bad_parameters_are_refused(client, project):
    def status(name, **parameters):
        return client.post(f"/tools/{name}", json=parameters).status_code

    assert status("no_such_tool") == 404
    assert status("search_logs", colour="red") == 422  # unknown parameter
    assert status("search_logs", limit=0) == 422  # below the minimum
    assert status("search_logs", limit=101) == 422  # above the maximum
    assert status("search_logs", min_severity="LOUD") == 422  # not an allowed value
    assert status("search_logs", trace_id="xyz") == 422  # wrong format
    assert status("search_logs", since="2026-11-17T11:00:00", until="2026-11-17T10:00:00") == 422
    assert status("get_incident") == 422  # missing required parameter
    assert status("get_incident", incident_id=999) == 404
    assert status("get_error_timeline") == 422  # needs incident_id or project_id
    assert status("get_service_status", service="rm-rf") == 422
    assert status("get_metric_series", metric="x", aggregation="median") == 422
    detail = client.post("/tools/search_logs", json={"limit": 0}).json()["detail"]
    assert "limit" in detail and "greater than or equal to 1" in detail


def test_search_logs_parameters(client, project):
    def ids(**parameters):
        return [log["id"] for log in run(client, "search_logs", **parameters)["logs"]]

    every = ids(limit=100)
    assert len(every) == 6
    assert len(ids(project_id=project)) == 6
    assert len(ids(project_id=project + 1)) == 0
    assert len(ids(incident_id=incident_id(client))) == 5  # the INFO log is not part of it
    assert len(ids(query="SHOP-DB")) == 2  # not case-sensitive
    assert len(ids(min_severity="ERROR")) == 4
    assert len(ids(min_severity="CRITICAL")) == 1
    assert len(ids(service="web")) == 3
    assert len(ids(error_type="operationalerror")) == 2
    assert len(ids(request_id="req-1")) == 2
    assert len(ids(trace_id=TRACE.upper())) == 1
    assert len(ids(since="2026-11-17T10:00:02")) == 3
    assert len(ids(until="2026-11-17T10:00:01")) == 3
    assert ids(order="newest", limit=1) == [every[-1]]
    assert ids(order="oldest", limit=2) == every[:2]
    result = run(client, "search_logs", min_severity="ERROR", limit=1)
    assert result["total_matching"] == 4 and result["returned"] == 1


def test_list_and_get_incident_parameters(client, project):
    assert run(client, "list_incidents")["count"] == 1
    assert run(client, "list_incidents", project_id=project + 1)["count"] == 0
    assert run(client, "list_incidents", status="RESOLVED")["count"] == 0
    assert run(client, "list_incidents", min_severity="CRITICAL")["count"] == 1
    assert run(client, "list_incidents", service="shop-db")["count"] == 0
    assert run(client, "list_incidents", service="shop-api", limit=1)["count"] == 1

    incident = incident_id(client)
    full = run(client, "get_incident", incident_id=incident)
    assert full["severity"] == "CRITICAL" and len(full["logs"]) == 5
    assert len(run(client, "get_incident", incident_id=incident, log_limit=2)["logs"]) == 2
    errors = run(client, "get_incident", incident_id=incident, errors_only=True)
    assert {log["severity"] for log in errors["logs"]} == {"ERROR", "CRITICAL"}
    assert errors["logs_matching"] == 4


def test_error_timeline_parameters(client, project):
    timeline = run(client, "get_error_timeline", incident_id=incident_id(client), bucket_seconds=1)
    assert [item["service"] for item in timeline["first_errors"]] == ["shop-api", "shop-web"]
    assert len(timeline["buckets"]) == 3  # errors at :01, :02 and :03
    assert len(run(client, "get_error_timeline", project_id=project, bucket_seconds=60)["buckets"]) == 1
    only_web = run(client, "get_error_timeline", project_id=project, service="shop-web")
    assert [item["service"] for item in only_web["first_errors"]] == ["shop-web"]


def test_service_status_parameters(client):
    every = run(client, "get_service_status")
    assert {item["name"] for item in every["services"]} == {"shop-db", "shop-api", "shop-web"}
    one = run(client, "get_service_status", service="shop-db", event_limit=0)
    assert [item["name"] for item in one["services"]] == ["shop-db"]
    assert one["events"] == []
    # The demo fault is the answer, so it is never shown to the investigator
    assert all("fault" not in item for item in every["services"])


def test_service_status_since_keeps_only_newer_events(client, monkeypatch):
    from app.services import monitor

    monkeypatch.setattr(monitor, "_events", monitor.deque([
        {"time": "2026-11-17T10:00:00", "service": "shop-api", "severity": "ERROR", "message": "old crash"},
        {"time": "2026-11-17T11:00:00", "service": "shop-api", "severity": "INFO", "message": "Started"},
    ]))
    events = run(client, "get_service_status", since="2026-11-17T10:30:00")["events"]
    assert [event["message"] for event in events] == ["Started"]


def send_span(client, service, trace_id, span_id, minutes_ago, duration_ms, parent=None, error=False):
    start = time.time_ns() - int(minutes_ago * 60e9)
    item = {"traceId": trace_id, "spanId": span_id, "name": "GET /x", "kind": 2,
            "startTimeUnixNano": str(start), "endTimeUnixNano": str(start + int(duration_ms * 1e6)),
            "status": {"code": 2, "message": "boom"} if error else {}}
    if parent:
        item["parentSpanId"] = parent
    body = {"resourceSpans": [{"resource": {"attributes": [
        {"key": "service.name", "value": {"stringValue": service}}]}, "scopeSpans": [{"spans": [item]}]}]}
    assert client.post("/v1/traces", json=body).status_code == 200


def test_telemetry_tool_parameters(client):
    send_span(client, "api", "1" * 32, "a" * 16, minutes_ago=0.1, duration_ms=50)
    send_span(client, "db", "1" * 32, "b" * 16, minutes_ago=0.1, duration_ms=40, parent="a" * 16)
    send_span(client, "api", "2" * 32, "c" * 16, minutes_ago=0.1, duration_ms=1500, error=True)
    send_span(client, "api", "3" * 32, "d" * 16, minutes_ago=30, duration_ms=10)  # half an hour ago

    metrics = run(client, "get_service_metrics")
    assert {item["service"] for item in metrics["services"]} == {"api", "db"}
    api = run(client, "get_service_metrics", service="api", window_minutes=5)["services"][0]
    assert api["requests"] == 2 and api["errors"] == 1
    past = (datetime.now() - timedelta(minutes=28)).isoformat()
    old = run(client, "get_service_metrics", service="api", window_minutes=5, until=past)["services"][0]
    assert old["requests"] == 1 and old["latency_ms"]["max"] == 10.0
    project = client.get("/projects").json()[0]["id"]
    assert run(client, "get_service_metrics", project_id=project + 1)["services"] == []

    assert run(client, "search_traces")["count"] == 2
    assert run(client, "search_traces", window_minutes=60)["count"] == 3
    assert run(client, "search_traces", until=past, window_minutes=5)["count"] == 1
    assert [t["trace_id"] for t in run(client, "search_traces", status="ERROR")["traces"]] == ["2" * 32]
    assert [t["trace_id"] for t in run(client, "search_traces", status="OK")["traces"]] == ["1" * 32]
    assert [t["trace_id"] for t in run(client, "search_traces", service="db")["traces"]] == ["1" * 32]
    assert [t["trace_id"] for t in run(client, "search_traces", min_duration_ms=1000)["traces"]] == ["2" * 32]
    assert run(client, "search_traces", limit=1, window_minutes=60)["count"] == 1
    assert run(client, "search_traces", project_id=project + 1)["count"] == 0

    series = run(client, "get_metric_series", metric="requests", service="api", window_minutes=60,
                 step_seconds=600, aggregation="count")
    assert sum(point["value"] for point in series["points"]) == 3
    latest = run(client, "get_metric_series", metric="latency", service="api", window_minutes=5,
                 step_seconds=300, aggregation="max")
    assert latest["points"][-1]["value"] == 1500.0
    rate = run(client, "get_metric_series", metric="error_rate", window_minutes=5, step_seconds=300)
    assert rate["points"][-1]["value"] == pytest.approx(1 / 3, abs=0.01)
    assert run(client, "get_metric_series", metric="requests", project_id=project + 1)["points"] == []

    tree = run(client, "get_trace", trace_id="1" * 32)
    assert [(span["service"], span["depth"]) for span in tree["spans"]] == [("api", 0), ("db", 1)]
    assert "logs" in tree and "logs" not in run(client, "get_trace", trace_id="1" * 32, include_logs=False)
    assert client.post("/tools/get_trace", json={"trace_id": "9" * 32}).status_code == 404
