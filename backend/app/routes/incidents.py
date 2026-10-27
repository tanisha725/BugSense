"""Incidents: groups of related failures found by the incident detector."""

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Incident, Log, Project
from app.schemas import LogOut
from app.services.incident_detector import (
    ERROR_LEVELS,
    detect_incidents,
    error_label,
    rate_severity,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])

SEVERITY_RANK = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "INFO": 1}


def incident_facts(db, incident_ids):
    """Facts calculated from each incident's logs: when it started and ended,
    how many logs, errors and warnings, and how many services."""
    when = func.coalesce(Log.timestamp, Log.created_at)
    rows = db.execute(
        select(
            Log.incident_id,
            func.min(when),
            func.max(when),
            func.count(),
            func.count().filter(Log.severity.in_(ERROR_LEVELS)),
            func.count().filter(Log.severity == "WARNING"),
            func.count(distinct(Log.service)),
        )
        .where(Log.incident_id.in_(incident_ids))
        .group_by(Log.incident_id)
    ).all()
    return {
        row[0]: {
            "first_seen": row[1],
            "last_seen": row[2],
            "log_count": row[3],
            "error_count": row[4],
            "warning_count": row[5],
            "service_count": row[6],
        }
        for row in rows
    }


def incident_to_dict(incident, facts):
    return {
        "id": incident.id,
        "project_id": incident.project_id,
        "title": incident.title,
        "severity": incident.severity,
        "status": incident.status,
        "affected_service": incident.affected_service,
        "error_count": incident.error_count,
        "first_seen": None,
        "last_seen": None,
        "log_count": 0,
        "warning_count": 0,
        "service_count": 0,
        **facts,
    }


def find_incidents(db, project_id, status):
    query = select(Incident)
    if project_id:
        query = query.where(Incident.project_id == project_id)
    if status in ("OPEN", "RESOLVED"):
        query = query.where(Incident.status == status)
    incidents = db.scalars(query).all()
    facts = incident_facts(db, [incident.id for incident in incidents])
    result = [incident_to_dict(incident, facts.get(incident.id, {})) for incident in incidents]
    # Most serious first, then the most recent
    result.sort(key=lambda item: str(item["last_seen"] or ""), reverse=True)
    result.sort(key=lambda item: SEVERITY_RANK.get(item["severity"], 0), reverse=True)
    return result


@router.get("")
def list_incidents(project_id: int | None = None, status: str = "OPEN", db: Session = Depends(get_db)):
    """Incidents, most serious first. status: OPEN, RESOLVED or ALL."""
    return find_incidents(db, project_id, status.upper())


@router.get("/summary")
def incident_summary(project_id: int | None = None, db: Session = Depends(get_db)):
    """Counts of open incidents, for the dashboard."""
    query = select(Incident.severity, func.count()).where(Incident.status == "OPEN")
    if project_id:
        query = query.where(Incident.project_id == project_id)
    by_severity = dict(db.execute(query.group_by(Incident.severity)).all())
    return {
        "open": sum(by_severity.values()),
        "critical": by_severity.get("CRITICAL", 0),
        "by_severity": by_severity,
    }


@router.post("/detect")
def run_detection(project_id: int | None = None, db: Session = Depends(get_db)):
    """Runs incident detection again (for one project, or for all of them)."""
    if project_id:
        project_ids = [project_id]
    else:
        project_ids = db.scalars(select(Project.id)).all()
    created = sum(detect_incidents(db, pid) for pid in project_ids)
    return {"projects": len(project_ids), "open_incidents": created}


def get_incident(db, incident_id):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.get("/{incident_id}")
def incident_detail(incident_id: int, db: Session = Depends(get_db)):
    """One incident with its evidence: why it has this severity, which services
    and which errors are involved, and the logs themselves in time order."""
    incident = get_incident(db, incident_id)
    logs = db.scalars(
        select(Log)
        .where(Log.incident_id == incident_id)
        .order_by(func.coalesce(Log.timestamp, Log.created_at), Log.id)
    ).all()
    facts = incident_facts(db, [incident_id]).get(incident_id, {})
    _, reasons = rate_severity(logs) if logs else (None, [])

    services = Counter(log.service or "unknown" for log in logs)
    service_errors = Counter(log.service or "unknown" for log in logs if log.severity in ERROR_LEVELS)
    signatures = Counter(error_label(log) for log in logs if log.severity in ERROR_LEVELS) or Counter(
        error_label(log) for log in logs
    )

    return {
        **incident_to_dict(incident, facts),
        "project_name": incident.project.name,
        "severity_reasons": reasons,
        "services": [
            {"service": name, "count": count, "errors": service_errors[name]}
            for name, count in services.most_common(8)
        ],
        "signatures": [{"label": label, "count": count} for label, count in signatures.most_common(6)],
        # The first logs are the most useful for finding the cause, so they come first
        "logs": [LogOut.model_validate(log).model_dump() for log in logs[:300]],
    }


class StatusChange(BaseModel):
    status: str


@router.patch("/{incident_id}")
def change_status(incident_id: int, change: StatusChange, db: Session = Depends(get_db)):
    """Marks an incident RESOLVED (it is kept as history) or OPEN again."""
    status = change.status.upper()
    if status not in ("OPEN", "RESOLVED"):
        raise HTTPException(status_code=400, detail="Status must be OPEN or RESOLVED")
    incident = get_incident(db, incident_id)
    incident.status = status
    db.commit()
    return {"id": incident.id, "status": incident.status}
