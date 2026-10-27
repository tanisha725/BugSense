from datetime import datetime, timedelta

from app.models import Log
from app.services.incident_detector import message_template, rate_severity, split_into_bursts

START = datetime(2026, 10, 8, 10, 0, 0)


def make_log(minute, severity, service="api", error_type=None, message="boom"):
    return Log(
        project_id=1,
        raw=message,
        timestamp=START + timedelta(minutes=minute),
        severity=severity,
        service=service,
        error_type=error_type,
        message=message,
        created_at=START,
    )


def test_message_template_hides_numbers_and_ids():
    assert message_template("Child 6725 in slot 10") == "Child <*> in slot <*>"
    assert message_template("from 173.234.31.186 port 52683") == "from <*> port <*>"


def test_a_long_quiet_gap_starts_a_new_burst():
    logs = [make_log(0, "ERROR"), make_log(4, "ERROR"), make_log(30, "ERROR")]

    assert [len(burst) for burst in split_into_bursts(logs)] == [2, 1]


def test_severity_rules():
    assert rate_severity([make_log(0, "CRITICAL")])[0] == "CRITICAL"
    three_services = [make_log(0, "ERROR", service) for service in ("db", "api", "web")]
    assert rate_severity(three_services)[0] == "CRITICAL"
    assert rate_severity([make_log(0, "ERROR")] * 20)[0] == "HIGH"
    assert rate_severity([make_log(0, "ERROR", "db"), make_log(0, "ERROR", "api")])[0] == "HIGH"
    assert rate_severity([make_log(0, "ERROR")] * 3)[0] == "MEDIUM"
    severity, reasons = rate_severity([make_log(0, "WARNING")] * 12)
    assert severity == "LOW" and reasons == ["12 warnings close together, no errors"]


def test_cascading_failure_becomes_one_incident(client):
    """The demo scenario: database stops -> backend errors -> 503s -> page fails."""
    with open("../samples/checkout-outage.log", "rb") as file:
        client.post("/logs/upload", files={"file": ("outage.log", file.read(), "text/plain")})

    incidents = client.get("/incidents").json()
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident["severity"] == "CRITICAL"
    assert incident["title"].startswith("FATAL: the database system is shutting down in postgres")
    assert incident["service_count"] == 3
    assert incident["error_count"] == 6

    detail = client.get(f"/incidents/{incident['id']}").json()
    assert detail["severity_reasons"] == ["1 CRITICAL log(s)"]
    # The evidence is in time order, so the first failure is first
    assert detail["logs"][0]["service"] == "checkout-api"
    assert {item["service"] for item in detail["services"]} == {"checkout-api", "postgres", "web-frontend"}


def test_single_error_is_not_an_incident(client):
    client.post("/logs/text", json={"text": "2026-10-08 10:00:00 ERROR [api] KeyError: 'id'"})

    assert client.get("/incidents").json() == []


def test_resolving_keeps_the_incident_as_history(client):
    text = "\n".join(f"2026-10-08 10:00:0{n} ERROR [api] TimeoutError: slow" for n in range(3))
    client.post("/logs/text", json={"text": text})
    incident_id = client.get("/incidents").json()[0]["id"]

    assert client.patch(f"/incidents/{incident_id}", json={"status": "resolved"}).json()["status"] == "RESOLVED"
    client.post("/incidents/detect")

    assert client.get("/incidents").json() == []
    assert [item["id"] for item in client.get("/incidents", params={"status": "RESOLVED"}).json()] == [incident_id]
    assert client.patch(f"/incidents/{incident_id}", json={"status": "maybe"}).status_code == 400


def test_dataset_import_detects_incidents(client):
    project_id = client.post("/datasets/hadoop/import").json()["project_id"]

    incidents = client.get("/incidents", params={"project_id": project_id}).json()
    assert len(incidents) == 1
    assert incidents[0]["severity"] == "CRITICAL"
    assert incidents[0]["error_count"] == 152

    summary = client.get("/incidents/summary", params={"project_id": project_id}).json()
    assert summary == {"open": 1, "critical": 1, "by_severity": {"CRITICAL": 1}}


def test_deleting_all_logs_removes_their_incidents(client):
    project_id = client.post("/datasets/hadoop/import").json()["project_id"]
    client.delete("/logs", params={"project_id": project_id})

    assert client.get("/incidents", params={"project_id": project_id}).json() == []
