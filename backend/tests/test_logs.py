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
