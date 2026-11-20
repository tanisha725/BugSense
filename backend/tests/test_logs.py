from app.services.log_parser import split_into_entries


def test_split_keeps_stack_trace_with_its_log():
    text = "ERROR boom\n  File app.py, line 3\n\nINFO fine\n"

    assert split_into_entries(text) == ["ERROR boom\n  File app.py, line 3", "INFO fine"]


def test_create_structured_log(client):
    response = client.post(
        "/logs", json={"msg": "db connection refused", "level": "error", "service": "api"}
    )

    assert response.status_code == 201
    log = response.json()
    assert log["message"] == "db connection refused"
    assert log["severity"] == "ERROR"
    assert log["service"] == "api"


def test_structured_log_needs_a_message(client):
    assert client.post("/logs", json={"service": "api"}).status_code == 422


def test_paste_text_creates_one_log_per_line(client):
    response = client.post("/logs/text", json={"text": "first line\nsecond line\n"})

    assert response.json() == {"created": 2, "skipped": 0}
    # Newest first
    assert [log["raw"] for log in client.get("/logs").json()] == ["second line", "first line"]


def test_upload_text_file(client):
    files = {"file": ("app.log", b"ERROR one\nINFO two\n", "text/plain")}

    assert client.post("/logs/upload", files=files).json()["created"] == 2


def test_upload_json_lines_file_skips_bad_lines(client):
    content = b'{"message": "ok", "level": "info"}\nnot json\n{"no_message": 1}\n'
    files = {"file": ("app.jsonl", content, "application/json")}

    assert client.post("/logs/upload", files=files).json() == {"created": 1, "skipped": 2}


def test_upload_rejects_other_file_types(client):
    files = {"file": ("script.py", b"print('hi')", "text/plain")}

    assert client.post("/logs/upload", files=files).status_code == 400


def test_filters(client):
    client.post("/logs", json={"message": "payment failed", "severity": "ERROR", "service": "checkout"})
    client.post("/logs", json={"message": "user logged in", "severity": "INFO", "service": "auth"})

    assert len(client.get("/logs", params={"severity": "error"}).json()) == 1
    assert len(client.get("/logs", params={"service": "auth"}).json()) == 1
    assert len(client.get("/logs", params={"search": "PAYMENT"}).json()) == 1
    assert len(client.get("/logs", params={"search": "100%"}).json()) == 0


def test_uploaded_text_is_parsed(client):
    line = b"2026-10-08 10:15:03 ERROR [checkout-api] TimeoutError: too slow request_id=req-1\n"
    client.post("/logs/upload", files={"file": ("app.log", line, "text/plain")})

    log = client.get("/logs", params={"severity": "ERROR", "service": "checkout"}).json()[0]
    assert log["error_type"] == "TimeoutError"
    assert log["request_id"] == "req-1"
    assert log["message"] == "TimeoutError: too slow request_id=req-1"


def test_structured_log_gets_missing_fields_filled(client):
    log = client.post("/logs", json={"msg": "KeyError: 'id' request_id=abc", "level": "warn"}).json()

    assert (log["severity"], log["error_type"], log["request_id"]) == ("WARNING", "KeyError", "abc")


def test_delete_one_log(client):
    log_id = client.post("/logs", json={"message": "remove me"}).json()["id"]
    client.post("/logs", json={"message": "keep me"})

    assert client.delete(f"/logs/{log_id}").json() == {"deleted": 1}
    assert [log["message"] for log in client.get("/logs").json()] == ["keep me"]
    assert client.delete(f"/logs/{log_id}").status_code == 404


def test_delete_all_logs(client):
    client.post("/logs/text", json={"text": "one\ntwo\nthree"})

    assert client.delete("/logs").json() == {"deleted": 3}
    assert client.get("/logs").json() == []


def test_stats(client):
    client.post("/logs", json={"message": "a", "severity": "ERROR"})
    client.post("/logs/text", json={"text": "plain line"})

    stats = client.get("/logs/stats").json()
    assert stats["total"] == 2
    assert stats["errors"] == 1
    assert stats["by_severity"] == {"ERROR": 1, "UNKNOWN": 1}


def test_stats_top_errors(client):
    client.post("/logs/text", json={"text": "ERROR TimeoutError: a\nERROR TimeoutError: b\nERROR KeyError: c"})

    assert client.get("/logs/stats").json()["top_errors"] == [
        {"error_type": "TimeoutError", "count": 2},
        {"error_type": "KeyError", "count": 1},
    ]


FILTER_LOGS = """2026-11-17 10:00:00 INFO [api] started request_id=req-0
2026-11-17 10:00:01 ERROR [api] TimeoutError: db slow request_id=req-1 trace_id=4bf92f3577b34da6a3ce929d0e0e4736
2026-11-17 10:00:02 WARNING [web] retrying request_id=req-1
2026-11-17 10:00:03 CRITICAL [web] ConnectionError: api down request_id=req-2
2026-11-17 10:00:04 DEBUG [web] cache miss
"""


def test_every_log_filter_and_paging_parameter(client):
    client.post("/logs/text", json={"text": FILTER_LOGS})

    def messages(**params):
        return [log["message"][:12] for log in client.get("/logs", params=params).json()]

    def count(**params):
        return client.get("/logs/count", params=params).json()["total"]

    assert count() == 5
    assert count(severity="error") == 1  # lower case is accepted
    assert count(min_severity="WARNING") == 3
    assert count(service="we") == 3
    assert count(error_type="timeouterror") == 1
    assert count(request_id="req-1") == 2
    assert count(trace_id="4BF92F3577B34DA6A3CE929D0E0E4736") == 1
    assert count(since="2026-11-17T10:00:03") == 2
    assert count(until="2026-11-17T10:00:01") == 2
    assert count(search="retry") == 1
    incident = client.get("/incidents").json()[0]["id"]
    assert count(incident_id=incident) == 3  # the WARNING, ERROR and CRITICAL logs

    assert messages(limit=2) == ["cache miss", "ConnectionEr"]  # newest first
    assert messages(limit=2, offset=2) == ["retrying req", "TimeoutError"]
    assert messages(order="oldest", limit=1) == ["started requ"]

    export = client.get("/logs/export", params={"request_id": "req-1"}).text
    assert export.count("\n") == 3 and "trace_id" in export.splitlines()[0]


def test_log_parameters_are_validated(client):
    for params in (
        {"severity": "LOUD"},
        {"min_severity": "x"},
        {"limit": 0},
        {"limit": 501},
        {"offset": -1},
        {"trace_id": "nope"},
        {"order": "random"},
        {"since": "2026-11-17T11:00:00", "until": "2026-11-17T10:00:00"},
        {"project_id": 0},
    ):
        assert client.get("/logs", params=params).status_code == 422, params
    assert client.get("/logs/timeline", params={"slots": 0}).status_code == 422
    assert client.get("/logs/timeline", params={"minutes": 0}).status_code == 422


def test_incident_list_parameters(client):
    client.post("/logs/text", json={"text": FILTER_LOGS})

    def ids(**params):
        return client.get("/incidents", params=params).json()

    assert len(ids()) == 1
    assert len(ids(status="resolved")) == 0
    assert len(ids(status="all")) == 1
    assert len(ids(min_severity="CRITICAL")) == 1
    assert len(ids(service="web")) == 1
    assert len(ids(service="nothing")) == 0
    assert len(ids(offset=1)) == 0
    assert client.get("/incidents", params={"status": "maybe"}).status_code == 422
    assert client.get("/incidents", params={"min_severity": "HUGE"}).status_code == 422
    assert client.get("/incidents", params={"limit": 0}).status_code == 422

    incident = ids()[0]["id"]
    detail = client.get(f"/incidents/{incident}", params={"log_limit": 1, "errors_only": True}).json()
    assert len(detail["logs"]) == 1 and detail["logs_matching"] == 2
    assert client.post("/incidents/detect", params={"project_id": 999}).status_code == 404
