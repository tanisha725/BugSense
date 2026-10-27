"""Log ingestion: receiving logs, storing them and listing them."""

import json
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Incident, Log, Project
from app.schemas import LogCreate, LogOut, LogsCreated, LogText
from app.services.log_parser import (
    find_error_type,
    find_request_id,
    normalize_severity,
    parse_log,
    split_into_entries,
)
from app.services.datasets import to_csv
from app.services.incident_detector import detect_incidents
from app.services.projects import find_or_create_project

router = APIRouter(prefix="/logs", tags=["logs"])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_ENTRIES = 5000
TEXT_EXTENSIONS = {".log", ".txt"}
JSON_EXTENSIONS = {".json", ".jsonl"}


def get_project(db, project_id):
    """Returns the requested project, or the default one if none was given."""
    if project_id is not None:
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    # Login comes in a later phase. Until then logs without a project go into a demo project.
    return find_or_create_project(db, "Demo Project")


def structured_log(data, raw, project):
    """Builds a Log row from an already validated structured log."""
    fields = data.model_dump(exclude={"project_id"})
    fields["severity"] = normalize_severity(fields["severity"])
    # Fill in what the sender left out, if the message contains it
    fields["error_type"] = fields["error_type"] or find_error_type(data.message)
    fields["request_id"] = fields["request_id"] or find_request_id(data.message)
    return Log(project_id=project.id, raw=raw, **fields)


def text_logs(text, project):
    """Splits raw text into entries and parses each one into a Log row."""
    return [
        Log(project_id=project.id, raw=entry, **parse_log(entry))
        for entry in split_into_entries(text)
    ]


def logs_from_json_text(text, project):
    """Reads a JSON file: either one list of objects or one object per line.

    Returns the Log rows and the number of entries that had to be skipped.
    """
    try:
        loaded = json.loads(text)
        items = loaded if isinstance(loaded, list) else [loaded]
    except json.JSONDecodeError:
        items = []
        for line in text.splitlines():
            if line.strip():
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    items.append(None)

    logs, skipped = [], 0
    for item in items:
        try:
            data = LogCreate.model_validate(item)
        except ValidationError:
            skipped += 1
            continue
        logs.append(structured_log(data, json.dumps(item), project))
    return logs, skipped


def save_logs(db, logs, project):
    """Stores new logs, then looks for incidents in the project again."""
    if not logs:
        raise HTTPException(status_code=400, detail="No log entries found")
    if len(logs) > MAX_ENTRIES:
        raise HTTPException(
            status_code=413, detail=f"Too many log entries (limit is {MAX_ENTRIES})"
        )
    db.add_all(logs)
    db.commit()
    detect_incidents(db, project.id)


@router.post("", response_model=LogOut, status_code=201)
def create_log(data: LogCreate, db: Session = Depends(get_db)):
    """Stores one structured JSON log."""
    project = get_project(db, data.project_id)
    raw = data.model_dump_json(exclude={"project_id"}, exclude_none=True)
    log = structured_log(data, raw, project)
    save_logs(db, [log], project)
    db.refresh(log)
    return log


@router.post("/text", response_model=LogsCreated, status_code=201)
def create_logs_from_text(data: LogText, db: Session = Depends(get_db)):
    """Stores pasted raw log text. Each entry is parsed into fields."""
    project = get_project(db, data.project_id)
    logs = text_logs(data.text, project)
    save_logs(db, logs, project)
    return LogsCreated(created=len(logs))


@router.post("/upload", response_model=LogsCreated, status_code=201)
def upload_log_file(
    file: UploadFile,
    project_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    """Stores the logs from an uploaded .log, .txt, .json or .jsonl file."""
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in TEXT_EXTENSIONS | JSON_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail="Only .log, .txt, .json and .jsonl files are allowed"
        )

    # Read one byte more than the limit so we can tell if the file is too big
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (limit is 2 MB)")

    # The file is only ever read as text. It is never executed.
    text = content.decode("utf-8", errors="replace").replace("\x00", "")
    project = get_project(db, project_id)

    if extension in JSON_EXTENSIONS:
        logs, skipped = logs_from_json_text(text, project)
    else:
        logs = text_logs(text, project)
        skipped = 0

    save_logs(db, logs, project)
    return LogsCreated(created=len(logs), skipped=skipped)


def in_project(query, project_id):
    """Adds "only this project" to a query when a project is chosen."""
    return query.where(Log.project_id == project_id) if project_id else query


@router.get("/stats")
def log_stats(project_id: int | None = None, db: Session = Depends(get_db)):
    """Counts logs by severity and finds the most common error types and services."""
    rows = db.execute(
        in_project(select(Log.severity, func.count()), project_id).group_by(Log.severity)
    ).all()
    by_severity = {severity or "UNKNOWN": count for severity, count in rows}

    top_errors = db.execute(
        in_project(select(Log.error_type, func.count()), project_id)
        .where(Log.error_type.is_not(None))
        .group_by(Log.error_type)
        .order_by(func.count().desc(), Log.error_type)
        .limit(5)
    ).all()

    error_count = func.count().filter(Log.severity.in_(["ERROR", "CRITICAL"]))
    top_services = db.execute(
        in_project(select(Log.service, func.count(), error_count), project_id)
        .where(Log.service.is_not(None))
        .group_by(Log.service)
        .order_by(func.count().desc(), Log.service)
        .limit(5)
    ).all()

    service_count = db.scalar(
        in_project(select(func.count(func.distinct(Log.service))), project_id)
    )

    return {
        "total": sum(by_severity.values()),
        "errors": by_severity.get("ERROR", 0) + by_severity.get("CRITICAL", 0),
        "warnings": by_severity.get("WARNING", 0),
        "services": service_count,
        "by_severity": by_severity,
        "top_errors": [{"error_type": name, "count": count} for name, count in top_errors],
        "top_services": [
            {"service": name, "count": count, "errors": errors}
            for name, count, errors in top_services
        ],
    }


def as_local_time(moment):
    """Times without a time zone are treated as local time, so all times can be compared."""
    return moment.astimezone() if moment.tzinfo is None else moment


@router.get("/timeline")
def log_timeline(
    project_id: int | None = None,
    slots: int = 30,
    minutes: int | None = None,
    db: Session = Depends(get_db),
):
    """Counts logs in equal time slots, for the activity chart.

    Without `minutes` the slots cover the whole time range of the logs.
    With `minutes` they cover only the last few minutes (used for live replay).
    """
    slots = max(1, min(slots, 120))
    when = func.coalesce(Log.timestamp, Log.created_at)
    rows = db.execute(in_project(select(when, Log.severity), project_id)).all()
    times = [(as_local_time(moment), severity) for moment, severity in rows]

    if minutes:
        end = datetime.now().astimezone()
        start = end - timedelta(minutes=minutes)
        times = [(moment, severity) for moment, severity in times if start <= moment <= end]
    elif times:
        start = min(moment for moment, _ in times)
        end = max(moment for moment, _ in times)
    if not times:
        return []

    slot_size = max((end - start) / slots, timedelta(seconds=1))
    result = [
        {"start": start + slot_size * index, "total": 0, "errors": 0, "warnings": 0}
        for index in range(slots)
    ]
    for moment, severity in times:
        slot = result[min(int((moment - start) / slot_size), slots - 1)]
        slot["total"] += 1
        if severity in ("ERROR", "CRITICAL"):
            slot["errors"] += 1
        elif severity == "WARNING":
            slot["warnings"] += 1
    return result


def filtered_logs(project_id, search, severity, service):
    """The query behind the Logs page filters, shared by the list and the CSV export."""
    query = in_project(select(Log), project_id)
    if search:
        query = query.where(Log.raw.icontains(search, autoescape=True))
    if severity:
        query = query.where(Log.severity == severity.upper())
    if service:
        query = query.where(Log.service.icontains(service, autoescape=True))
    return query


@router.get("", response_model=list[LogOut])
def list_logs(
    search: str | None = None,
    severity: str | None = None,
    service: str | None = None,
    project_id: int | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Returns the newest logs first, with optional filters."""
    query = filtered_logs(project_id, search, severity, service)
    query = query.order_by(Log.id.desc()).limit(max(1, min(limit, 500)))
    return db.scalars(query).all()


@router.get("/export")
def export_logs(
    search: str | None = None,
    severity: str | None = None,
    service: str | None = None,
    project_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Downloads the stored logs (with the same filters as the Logs page) as a CSV file.

    This also works for a live stream: it exports everything received so far.
    """
    query = filtered_logs(project_id, search, severity, service).order_by(Log.id).limit(50_000)
    rows = [
        {
            "line": log.id,
            "timestamp": log.timestamp,
            "severity": log.severity,
            "service": log.service,
            "error_type": log.error_type,
            "request_id": log.request_id,
            "message": log.message or log.raw,
        }
        for log in db.scalars(query)
    ]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Response(
        to_csv(rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="bugsense-logs-{stamp}.csv"'},
    )


@router.delete("/{log_id}")
def delete_log(log_id: int, db: Session = Depends(get_db)):
    """Deletes one log."""
    log = db.get(Log, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Log not found")
    project_id = log.project_id
    db.delete(log)
    db.commit()
    detect_incidents(db, project_id)
    return {"deleted": 1}


@router.delete("")
def delete_all_logs(project_id: int | None = None, db: Session = Depends(get_db)):
    """Deletes every log (of one project, if given). Useful before a new demo."""
    query = delete(Log)
    incidents = delete(Incident)
    if project_id:
        query = query.where(Log.project_id == project_id)
        incidents = incidents.where(Incident.project_id == project_id)
    result = db.execute(query)
    # Incidents without logs mean nothing, so they go too
    db.execute(incidents)
    db.commit()
    return {"deleted": result.rowcount}
