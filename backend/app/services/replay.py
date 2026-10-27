"""Live replay: sends a dataset into BugSense a few lines per second.

This makes a recorded dataset behave like a live system. Each line is stored
with the current time, so the dashboard fills up in real time.

It runs in a background thread, so the API keeps answering while it works.
Only one replay runs at a time.
"""

import threading
import time
from datetime import datetime

from sqlalchemy import delete

from app.database import SessionLocal
from app.models import Incident, Log
from app.services.datasets import DATASETS, parse_entry, read_entries
from app.services.incident_detector import detect_incidents
from app.services.projects import find_or_create_project

# Tests replace this with a session for their own test database
session_factory = SessionLocal

_stop_signal = threading.Event()
_thread = None
_state = {"running": False, "dataset": None, "project_id": None, "sent": 0, "total": 0, "speed": 0}


def status():
    return dict(_state)


def start(key, speed):
    """Starts replaying a dataset at `speed` lines per second."""
    stop()
    dataset = DATASETS[key]

    with session_factory() as db:
        project = find_or_create_project(
            db, f"{dataset['name']} (live)", f"Live replay of the {dataset['name']} dataset."
        )
        # Every replay starts with an empty project
        db.execute(delete(Log).where(Log.project_id == project.id))
        db.execute(delete(Incident).where(Incident.project_id == project.id))
        db.commit()
        project_id = project.id

    entries = read_entries(key)
    _state.update(
        running=True, dataset=key, project_id=project_id, sent=0, total=len(entries), speed=speed
    )
    _stop_signal.clear()

    global _thread
    # daemon=True: the thread never stops the server from shutting down
    _thread = threading.Thread(
        target=run, args=(entries, dataset, project_id, speed), daemon=True
    )
    _thread.start()
    return status()


def stop():
    """Asks the running replay to stop and waits briefly for it."""
    _stop_signal.set()
    if _thread is not None:
        _thread.join(timeout=3)
    _state["running"] = False
    return status()


def run(entries, dataset, project_id, speed, pause_seconds=1.0):
    """The work done by the background thread: one batch of lines every second."""
    for start_index in range(0, len(entries), speed):
        if _stop_signal.is_set():
            break
        batch = entries[start_index : start_index + speed]
        now = datetime.now().astimezone()
        with session_factory() as db:
            for entry in batch:
                fields = parse_entry(entry, dataset)
                fields["timestamp"] = now  # "happening now"; the original time stays in raw
                db.add(Log(project_id=project_id, raw=entry, **fields))
            db.commit()
            # Incidents appear and grow while the stream runs
            detect_incidents(db, project_id)
        _state["sent"] += len(batch)
        # wait() returns early if stop() is called during the pause
        _stop_signal.wait(pause_seconds)
    _state["running"] = False
