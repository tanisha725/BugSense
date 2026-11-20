"""Incident queries shared by the API routes and the investigation tools."""

from collections import Counter

from sqlalchemy import distinct, func, select

from app.models import Incident, Log
from app.schemas import LogOut
from app.services.incident_detector import ERROR_LEVELS, error_label, rate_severity

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
            func.min(Log.id),
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
            "first_log_id": row[7],
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
        "first_log_id": None,
        **facts,
    }


def find_incidents(db, project_id=None, status="OPEN", min_severity=None, service=None, limit=None, offset=0):
    """Incidents, most serious first, then the most recent.

    status        OPEN, RESOLVED or ALL
    min_severity  only incidents at least this serious (LOW, MEDIUM, HIGH, CRITICAL)
    service       only incidents with logs from this service (part of the name is enough)
    """
    query = select(Incident)
    if project_id:
        query = query.where(Incident.project_id == project_id)
    if status in ("OPEN", "RESOLVED"):
        query = query.where(Incident.status == status)
    if min_severity:
        allowed = [name for name, rank in SEVERITY_RANK.items() if rank >= SEVERITY_RANK[min_severity]]
        query = query.where(Incident.severity.in_(allowed))
    if service:
        with_service = select(Log.incident_id).where(
            Log.incident_id.is_not(None), Log.service.icontains(service, autoescape=True)
        )
        query = query.where(Incident.id.in_(with_service))
    incidents = db.scalars(query).all()
    facts = incident_facts(db, [incident.id for incident in incidents])
    result = [incident_to_dict(incident, facts.get(incident.id, {})) for incident in incidents]
    result.sort(key=lambda item: str(item["last_seen"] or ""), reverse=True)
    result.sort(key=lambda item: SEVERITY_RANK.get(item["severity"], 0), reverse=True)
    end = None if limit is None else offset + limit
    return result[offset:end]


def incident_logs(db, incident_id):
    return db.scalars(
        select(Log)
        .where(Log.incident_id == incident_id)
        .order_by(func.coalesce(Log.timestamp, Log.created_at), Log.id)
    ).all()


def incident_evidence(db, incident, log_limit=300, errors_only=False):
    """One incident with its evidence: why it has this severity, which services
    and which errors are involved, and the logs themselves in time order."""
    logs = incident_logs(db, incident.id)
    facts = incident_facts(db, [incident.id]).get(incident.id, {})
    _, reasons = rate_severity(logs) if logs else (None, [])

    services = Counter(log.service or "unknown" for log in logs)
    service_errors = Counter(log.service or "unknown" for log in logs if log.severity in ERROR_LEVELS)
    signatures = Counter(error_label(log) for log in logs if log.severity in ERROR_LEVELS) or Counter(
        error_label(log) for log in logs
    )
    shown = [log for log in logs if log.severity in ERROR_LEVELS] if errors_only else logs

    return {
        **incident_to_dict(incident, facts),
        "project_name": incident.project.name,
        "severity_reasons": reasons,
        "services": [
            {"service": name, "count": count, "errors": service_errors[name]}
            for name, count in services.most_common(8)
        ],
        "signatures": [{"label": label, "count": count} for label, count in signatures.most_common(6)],
        "logs_matching": len(shown),
        # The first logs are the most useful for finding the cause, so they come first
        "logs": [LogOut.model_validate(log).model_dump() for log in shown[:log_limit]],
    }
