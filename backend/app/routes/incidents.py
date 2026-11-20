"""Incidents: groups of related failures found by the incident detector."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Incident, Project
from app.services import diagnosis
from app.services.incident_detector import detect_incidents
from app.services.incidents import find_incidents, incident_evidence

router = APIRouter(prefix="/incidents", tags=["incidents"])

ProjectId = Annotated[int | None, Query(ge=1)]
Status = Literal["OPEN", "RESOLVED", "ALL"]
Level = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def upper(value):
    return value.upper() if isinstance(value, str) else value


@router.get("")
def list_incidents(
    project_id: ProjectId = None,
    status: Annotated[str, Query(description="OPEN, RESOLVED or ALL")] = "OPEN",
    min_severity: Annotated[str | None, Query(description="LOW, MEDIUM, HIGH or CRITICAL")] = None,
    service: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
):
    """Incidents, most serious first. Upper or lower case is accepted."""
    status, min_severity = upper(status), upper(min_severity)
    if status not in Status.__args__:
        raise HTTPException(status_code=422, detail="status must be OPEN, RESOLVED or ALL")
    if min_severity is not None and min_severity not in Level.__args__:
        raise HTTPException(status_code=422, detail="min_severity must be LOW, MEDIUM, HIGH or CRITICAL")
    return find_incidents(db, project_id, status, min_severity, service, limit, offset)


@router.get("/summary")
def incident_summary(project_id: ProjectId = None, db: Session = Depends(get_db)):
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
def run_detection(project_id: ProjectId = None, db: Session = Depends(get_db)):
    """Runs incident detection again (for one project, or for all of them)."""
    if project_id:
        if db.get(Project, project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
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
def incident_detail(
    incident_id: int,
    log_limit: Annotated[int, Query(ge=0, le=1000)] = 300,
    errors_only: bool = False,
    db: Session = Depends(get_db),
):
    """One incident with its evidence. log_limit caps the logs returned;
    errors_only keeps only ERROR and CRITICAL logs."""
    return incident_evidence(db, get_incident(db, incident_id), log_limit, errors_only)


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


# ---------- Diagnosis (Phase 7) ----------


@router.post("/{incident_id}/diagnose")
def diagnose(
    incident_id: int,
    engine: Literal["auto", "llm", "rules"] = "auto",
    max_steps: Annotated[int, Query(ge=1, le=12)] = 4,
    db: Session = Depends(get_db),
):
    """Finds the probable cause of an incident.

    engine  auto  - the AI model if a key is set, otherwise the rules
            llm   - the AI model (fails if no key is set)
            rules - the rule-based investigator, no AI
    max_steps caps how many rounds of tool calls the AI may make after the
    case file (default 4, to stay inside free-tier token limits).
    """
    incident = get_incident(db, incident_id)
    try:
        return diagnosis.diagnose(db, incident, engine, max_steps)
    except diagnosis.DiagnosisError as problem:
        raise HTTPException(status_code=problem.status, detail=str(problem)) from problem


@router.get("/{incident_id}/diagnoses")
def diagnosis_history(
    incident_id: int,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    db: Session = Depends(get_db),
):
    """Earlier diagnoses of this incident, newest first."""
    return diagnosis.history(db, get_incident(db, incident_id), limit)
