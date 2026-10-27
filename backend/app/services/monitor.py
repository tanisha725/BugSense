"""Service monitor: starts the demo services and watches them.

This replaces Docker monitoring. Docker runs programs in containers and reports
their status, restarts and health. Here the programs run as normal processes on
the computer, and BugSense itself plays the supervisor:

  - starts and stops each service              (like docker start / stop)
  - restarts a service that crashes            (like a Docker restart policy)
  - notices a crash loop: 3 crashes in 60 s    (like Docker's "restarting" state)
  - calls /health every few seconds            (like a Docker healthcheck)
  - stores everything a service prints as logs (like docker logs)
  - records events such as "exited with code 1" (like docker events)

The events are stored as logs too. So when a service crashes, incident
detection puts the crash and the errors it caused into the same incident.
"""

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path

from app.database import SessionLocal
from app.models import Log
from app.services.incident_detector import detect_incidents
from app.services.log_parser import parse_log, split_into_entries
from app.services.projects import find_or_create_project

DEMO_FOLDER = Path(__file__).resolve().parents[3] / "demo-services"
PROJECT_NAME = "Demo shop (live services)"

SERVICES = {
    "shop-db": {
        "script": "shop_db.py",
        "port": 9102,
        "description": "Pretend database. shop-api needs it for every order.",
    },
    "shop-api": {
        "script": "shop_api.py",
        "port": 9101,
        "description": "Checkout API. Healthy only when it can reach shop-db.",
    },
    "shop-web": {
        "script": "shop_web.py",
        "port": None,
        "description": "Web front end. Acts like customers: one checkout per second.",
    },
}

RESTART_DELAY = 2  # seconds before the first automatic restart (it grows each time)
CRASH_LOOP_COUNT = 3  # this many crashes ...
CRASH_LOOP_WINDOW = 60  # ... within this many seconds is a crash loop
GIVE_UP_AFTER = 6  # after this many crashes in the window, stop restarting
HEALTH_EVERY = 3  # seconds between health checks
TICK = 0.5  # how often the watcher looks at the services

# Tests replace this with a session for their own test database
session_factory = SessionLocal

_lock = threading.Lock()
_services = {}
_events = deque(maxlen=100)
_active = threading.Event()  # set while monitoring is switched on
_new_logs = threading.Event()  # set when new logs arrived, so detection runs again
_watcher = None
_project_id = None


def _state(name):
    """The monitor's notes about one service."""
    return _services.setdefault(
        name,
        {
            "process": None,
            "status": "stopped",  # stopped, running, crashed or crash-loop
            "wanted": False,  # should it be running? (False after the user stops it)
            "fault": "",
            "crashes": [],  # times of recent crashes
            "restart_count": 0,
            "started_at": None,
            "exit_code": None,
            "healthy": None,  # True, False, or None when unknown
            "restart_at": None,
            "last_health_check": 0,
        },
    )


# ---------- Storing logs and events ----------


def project_id():
    global _project_id
    if _project_id is None:
        with session_factory() as db:
            _project_id = find_or_create_project(
                db, PROJECT_NAME, "Three demo services started and watched by BugSense."
            ).id
            db.commit()
    return _project_id


def store_entry(service, entry):
    """Saves one log entry printed by a service."""
    fields = parse_log(entry)
    fields["service"] = fields["service"] or service
    with session_factory() as db:
        db.add(Log(project_id=project_id(), raw=entry, **fields))
        db.commit()
    _new_logs.set()


def record_event(service, severity, message, error_type=None):
    """Remembers a monitor event and stores it as a log of that service."""
    now = datetime.now()
    _events.append(
        {"time": now.isoformat(), "service": service, "severity": severity, "message": message}
    )
    raw = f"{now:%Y-%m-%d %H:%M:%S} {severity} [{service}] Process monitor: {message}"
    with session_factory() as db:
        db.add(
            Log(
                project_id=project_id(),
                raw=raw,
                timestamp=now,
                severity=severity,
                service=service,
                error_type=error_type,
                message=f"Process monitor: {message}",
            )
        )
        db.commit()
    _new_logs.set()


def read_output(lines, store):
    """Turns the lines a program prints into log entries.

    A line usually is one entry, but the lines of a stack trace belong to the
    error line above them. A line is kept back until the next one shows
    whether it continues the same entry.
    """
    pending = None
    for line in lines:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        if pending is not None and len(split_into_entries(f"{pending}\n{line}")) == 1:
            pending = f"{pending}\n{line}"
        else:
            if pending is not None:
                store(pending)
            pending = line
    if pending is not None:
        store(pending)


# ---------- Starting and stopping one service ----------


def port_in_use(port):
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _start(name):
    """Starts the program of one service. The caller holds the lock."""
    state = _state(name)
    config = SERVICES[name]
    if config["port"] and port_in_use(config["port"]):
        state["status"] = "crashed"
        record_event(name, "ERROR", f"Cannot start: port {config['port']} is already used by another program", "PortInUse")
        return
    environment = {**os.environ, "SHOP_FAULT": state["fault"], "PYTHONUNBUFFERED": "1"}
    process = subprocess.Popen(
        [sys.executable, config["script"]],
        cwd=DEMO_FOLDER,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # error messages and tracebacks are logs too
        text=True,
    )
    state.update(process=process, status="running", started_at=time.time(), exit_code=None, healthy=None, restart_at=None)
    # One small thread per service reads what it prints
    threading.Thread(
        target=read_output, args=(process.stdout, lambda entry: store_entry(name, entry)), daemon=True
    ).start()
    fault = f" with fault '{state['fault']}'" if state["fault"] else ""
    record_event(name, "INFO", f"Started (pid {process.pid}){fault}")


def _stop(name, reason):
    """Stops the program of one service. The caller holds the lock."""
    state = _state(name)
    process = state["process"]
    state.update(status="stopped", wanted=False, healthy=None, restart_at=None)
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        record_event(name, "INFO", reason)


# ---------- The watcher: noticing crashes and checking health ----------


def handle_crash(name, now):
    """Decides what to do after a service exits on its own. The caller holds the lock."""
    state = _state(name)
    code = state["process"].returncode
    state.update(exit_code=code, healthy=None)
    record_event(name, "ERROR", f"Exited unexpectedly with code {code}", "ProcessExit")

    state["crashes"] = [moment for moment in state["crashes"] if now - moment < CRASH_LOOP_WINDOW]
    state["crashes"].append(now)
    crashes = len(state["crashes"])

    if crashes >= GIVE_UP_AFTER:
        state["status"] = "crash-loop"
        record_event(name, "CRITICAL", f"Gave up restarting after {crashes} crashes in {CRASH_LOOP_WINDOW} s", "CrashLoop")
        return
    if crashes == CRASH_LOOP_COUNT:
        record_event(name, "CRITICAL", f"Crash loop: {crashes} crashes in the last {CRASH_LOOP_WINDOW} s", "CrashLoop")
    state["status"] = "crash-loop" if crashes >= CRASH_LOOP_COUNT else "crashed"
    # Wait a little longer after every crash ("back-off"), like Docker does
    state["restart_at"] = now + RESTART_DELAY * crashes


def check_health(name):
    """Calls the service's /health page. Returns (healthy, reason)."""
    url = f"http://127.0.0.1:{SERVICES[name]['port']}/health"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=1):
            return True, "ok"
    except urllib.error.HTTPError as problem:
        return False, f"/health returned {problem.code}"
    except OSError as problem:
        return False, f"/health did not answer ({getattr(problem, 'reason', problem)})"


def watch():
    """Runs in a background thread while monitoring is on."""
    last_detection = 0
    while _active.is_set():
        now = time.time()
        to_check = []
        with _lock:
            for name in SERVICES:
                state = _state(name)
                process = state["process"]
                if state["status"] in ("running",) and process and process.poll() is not None:
                    handle_crash(name, now)
                elif state["wanted"] and state["restart_at"] and now >= state["restart_at"]:
                    state["restart_count"] += 1
                    record_event(name, "WARNING", f"Restarting automatically (restart #{state['restart_count']})")
                    _start(name)
                elif (
                    state["status"] == "running"
                    and SERVICES[name]["port"]
                    and now - state["last_health_check"] >= HEALTH_EVERY
                    and now - state["started_at"] > 1  # give it a moment to start
                ):
                    state["last_health_check"] = now
                    to_check.append(name)

        # Health checks call the network, so they run without holding the lock
        for name in to_check:
            healthy, reason = check_health(name)
            with _lock:
                state = _state(name)
                if state["status"] != "running" or healthy == state["healthy"]:
                    continue
                if healthy:
                    record_event(name, "INFO", "Health check passed")
                else:
                    record_event(name, "WARNING", f"Health check failed: {reason}", "HealthCheckFailed")
                state["healthy"] = healthy

        # Look for incidents again when new logs arrived (at most every 3 seconds)
        if _new_logs.is_set() and now - last_detection >= 3:
            _new_logs.clear()
            last_detection = now
            with session_factory() as db:
                detect_incidents(db, project_id())

        time.sleep(TICK)


def _ensure_watcher():
    global _watcher
    _active.set()
    if _watcher is None or not _watcher.is_alive():
        _watcher = threading.Thread(target=watch, daemon=True)
        _watcher.start()


# ---------- What the API calls ----------


def start(name):
    with _lock:
        _ensure_watcher()
        state = _state(name)
        state.update(wanted=True, crashes=[])
        if state["status"] != "running":
            _start(name)


def stop(name):
    with _lock:
        _stop(name, "Stopped by user")


def restart(name, fault=None):
    with _lock:
        _ensure_watcher()
        state = _state(name)
        if fault is not None:
            state["fault"] = fault
        _stop(name, "Stopped for restart")
        # A restart by hand is a fresh start, so the crash history is forgotten
        state.update(wanted=True, crashes=[], restart_count=0)
        _start(name)


def start_all():
    for name in SERVICES:
        start(name)
        time.sleep(0.4)  # let each one open its port before the next needs it


def stop_all():
    with _lock:
        for name in reversed(list(SERVICES)):
            if _state(name)["process"] is not None:
                _stop(name, "Stopped by user")
    _active.clear()


# The four demo failures, plus a way back
SCENARIOS = {
    "database-down": "The database stops. The API cannot connect, returns 503, and the web page fails.",
    "crash-loop": "The API crashes right after starting, again and again.",
    "slow": "The API becomes slow, so the web page times out (an error spike).",
    "bad-config": "The API is given a broken database address and refuses to start.",
    "recover": "Remove every fault and start all services normally.",
}


def run_scenario(key):
    if key == "recover":
        for name in SERVICES:
            if _state(name)["fault"] or _state(name)["status"] != "running":
                restart(name, fault="")
        return
    start_all()
    if key == "database-down":
        with _lock:
            _stop("shop-db", "Stopped (demo scenario: database goes down)")
    elif key == "crash-loop":
        restart("shop-api", fault="crash")
    elif key == "slow":
        restart("shop-api", fault="slow")
    elif key == "bad-config":
        restart("shop-api", fault="bad-config")


def status():
    """Everything the Services page shows."""
    now = time.time()
    with _lock:
        services = []
        for name, config in SERVICES.items():
            state = _state(name)
            process = state["process"]
            running = state["status"] == "running"
            services.append(
                {
                    "name": name,
                    "description": config["description"],
                    "port": config["port"],
                    "status": state["status"],
                    "healthy": state["healthy"] if config["port"] else None,
                    "pid": process.pid if process and running else None,
                    "uptime_seconds": round(now - state["started_at"]) if running else None,
                    "restart_count": state["restart_count"],
                    "exit_code": state["exit_code"],
                    "fault": state["fault"],
                }
            )
        events = list(_events)[-40:][::-1]
    return {
        "monitoring": _active.is_set(),
        "project_id": _project_id,
        "services": services,
        "events": events,
        "scenarios": [{"key": key, "description": text} for key, text in SCENARIOS.items()],
    }
