import socket
import time

import pytest
from sqlalchemy import select

from app.models import Incident, Log
from app.services import monitor


def test_stack_trace_lines_stay_with_their_error():
    lines = [
        "2026-10-27 10:00:00 INFO [api] starting\n",
        "2026-10-27 10:00:01 CRITICAL [api] Unhandled exception, shutting down\n",
        "Traceback (most recent call last):\n",
        '  File "shop_api.py", line 97, in <module>\n',
        "RuntimeError: missing key 'currency'\n",
        "2026-10-27 10:00:02 INFO [api] next\n",
    ]
    entries = []
    monitor.read_output(lines, entries.append)

    assert len(entries) == 3
    assert entries[1].startswith("2026-10-27 10:00:01 CRITICAL")
    assert entries[1].endswith("RuntimeError: missing key 'currency'")


def test_health_check_reports_a_service_that_does_not_answer(monkeypatch):
    with socket.socket() as spare:  # find a port nothing listens on
        spare.bind(("127.0.0.1", 0))
        free_port = spare.getsockname()[1]
    monkeypatch.setitem(monitor.SERVICES, "ghost", {"script": "", "port": free_port, "description": ""})

    healthy, reason = monitor.check_health("ghost")
    assert healthy is False and "did not answer" in reason


@pytest.fixture
def crashing_service(tmp_path, monkeypatch, session_factory):
    """A real little program that prints one line and crashes straight away."""
    (tmp_path / "crasher.py").write_text(
        "import sys\nprint('2026-10-27 10:00:00 INFO [crasher] starting', flush=True)\nsys.exit(3)\n"
    )
    monkeypatch.setattr(monitor, "DEMO_FOLDER", tmp_path)
    monkeypatch.setattr(monitor, "SERVICES", {"crasher": {"script": "crasher.py", "port": None, "description": ""}})
    monkeypatch.setattr(monitor, "session_factory", session_factory)
    monkeypatch.setattr(monitor, "RESTART_DELAY", 0.05)
    monkeypatch.setattr(monitor, "TICK", 0.05)
    monkeypatch.setattr(monitor, "GIVE_UP_AFTER", 4)
    monkeypatch.setattr(monitor, "_project_id", None)
    monkeypatch.setattr(monitor, "_services", {})
    monitor._events.clear()
    yield
    monitor.stop_all()


def test_crash_loop_is_detected_and_becomes_an_incident(crashing_service, session_factory):
    monitor.start("crasher")

    deadline = time.time() + 20
    while time.time() < deadline and "Gave up" not in str(monitor.status()["events"]):
        time.sleep(0.1)

    service = monitor.status()["services"][0]
    assert service["status"] == "crash-loop"
    assert service["exit_code"] == 3
    assert service["restart_count"] == 3  # 4 crashes = the first run + 3 restarts

    time.sleep(3.5)  # incident detection runs every 3 seconds
    with session_factory() as db:
        error_types = set(db.scalars(select(Log.error_type)))
        incidents = db.scalars(select(Incident)).all()
    assert {"ProcessExit", "CrashLoop"} <= error_types
    assert [incident.severity for incident in incidents] == ["CRITICAL"]


def test_unknown_service_and_scenario_are_rejected(client):
    assert client.post("/monitor/services/rm-rf/start").status_code == 404
    assert client.post("/monitor/scenarios/delete-everything").status_code == 404
    assert client.post("/monitor/services/shop-api/explode").status_code == 400
