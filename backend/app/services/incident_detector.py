"""Incident detection: grouping related failures into incidents, with plain rules.

The idea in one sentence: problems that happen close together in time are
probably one incident.

  1. Take the project's problem logs (WARNING, ERROR, CRITICAL), oldest first.
  2. Cut them into "bursts": a gap of more than 10 minutes starts a new burst.
  3. A burst becomes an incident only if it is serious enough (see `is_incident`).
  4. Give the incident a severity, a title and an affected service.

Example: a database stops, the backend cannot connect, the API returns 503 and
the web page fails. These errors arrive within seconds of each other, so they
become ONE incident instead of many separate errors.

Detection can run again at any time. Open incidents are rebuilt from scratch,
while resolved incidents are kept as they are.
"""

import re
from collections import Counter
from datetime import timedelta

from sqlalchemy import delete, func, select, update

from app.models import Incident, Log

PROBLEM_LEVELS = ("WARNING", "ERROR", "CRITICAL")
ERROR_LEVELS = ("ERROR", "CRITICAL")

# Problems further apart than this are treated as separate incidents.
# 10 minutes was chosen by testing on the six real datasets: 5 minutes split one
# recurring Apache problem into 59 incidents, 10 minutes gives 18.
BURST_GAP = timedelta(minutes=10)

# A burst needs at least this much to become an incident (one error alone is noise)
MIN_ERRORS = 3
MIN_WARNINGS = 10


# ---------- Message templates: "the same error with different numbers" ----------

TEMPLATE_PATTERNS = [
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),  # UUIDs
    re.compile(r"\b0x[0-9a-fA-F]+\b"),  # hex numbers
    re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"),  # IP addresses
    re.compile(r"\d+"),  # any other number
]


def message_template(message):
    """'Child 6725 in slot 10' -> 'Child <*> in slot <*>'. Same idea as Loghub's EventTemplate."""
    text = message or ""
    for pattern in TEMPLATE_PATTERNS:
        text = pattern.sub("<*>", text)
    return re.sub(r"(<\*>[\s,.:_-]*)+<\*>", "<*>", text).strip()


def error_label(log):
    """A short name for what went wrong in one log."""
    return log.error_type or message_template(log.message)[:90] or "Unknown problem"


# ---------- Step 2: cutting problems into bursts ----------


def when(log):
    """The time of a log. Logs without their own timestamp use the time they arrived."""
    moment = log.timestamp or log.created_at
    return moment.astimezone() if moment.tzinfo is None else moment


def split_into_bursts(logs):
    """Groups logs (sorted by time) into bursts separated by gaps longer than BURST_GAP."""
    bursts = []
    for log in logs:
        if bursts and when(log) - when(bursts[-1][-1]) <= BURST_GAP:
            bursts[-1].append(log)
        else:
            bursts.append([log])
    return bursts


# ---------- Steps 3 and 4: deciding, rating and naming ----------


def count_levels(burst):
    levels = Counter(log.severity for log in burst)
    return levels["CRITICAL"], levels["ERROR"], levels["WARNING"]


def is_incident(burst):
    criticals, errors, warnings = count_levels(burst)
    return criticals >= 1 or criticals + errors >= MIN_ERRORS or warnings >= MIN_WARNINGS


def rate_severity(burst):
    """Returns the incident severity and the reasons for it, in plain words.

    CRITICAL  any CRITICAL log, or errors in 3 or more services
    HIGH      20 or more errors, or errors in 2 services
    MEDIUM    3 or more errors
    LOW       only warnings (10 or more)
    INFO is part of the scale, but BugSense only opens incidents from LOW upwards.
    """
    criticals, errors, warnings = count_levels(burst)
    error_count = criticals + errors
    failing_services = {log.service for log in burst if log.severity in ERROR_LEVELS and log.service}

    if criticals:
        return "CRITICAL", [f"{criticals} CRITICAL log(s)"]
    if len(failing_services) >= 3:
        return "CRITICAL", [f"errors in {len(failing_services)} services at the same time"]
    if error_count >= 20:
        return "HIGH", [f"{error_count} errors in a short time"]
    if len(failing_services) == 2:
        return "HIGH", ["errors in 2 services at the same time"]
    if error_count >= MIN_ERRORS:
        return "MEDIUM", [f"{error_count} errors close together"]
    return "LOW", [f"{warnings} warnings close together, no errors"]


def describe(burst):
    """Title and affected service of an incident."""
    errors = [log for log in burst if log.severity in ERROR_LEVELS]
    # The first failure is often the best hint about where things started
    first = errors[0] if errors else burst[0]
    services = Counter(log.service for log in burst if log.service)
    affected = services.most_common(1)[0][0] if services else None

    title = error_label(first)
    if first.service:
        title += f" in {first.service}"
    if not errors:
        title = f"Repeated warnings: {title}"
    if len(services) > 1:
        title += f" (+{len(services) - 1} more service{'s' if len(services) > 2 else ''})"
    return title[:255], affected


# ---------- Running detection for a project ----------


def detect_incidents(db, project_id):
    """Rebuilds the open incidents of one project. Returns how many were created."""
    # Forget the old open incidents (resolved ones stay untouched)
    open_ids = select(Incident.id).where(
        Incident.project_id == project_id, Incident.status == "OPEN"
    )
    db.execute(update(Log).where(Log.incident_id.in_(open_ids)).values(incident_id=None))
    db.execute(delete(Incident).where(Incident.project_id == project_id, Incident.status == "OPEN"))
    # The two lines above changed the database directly, so reload objects from it
    db.expire_all()

    # Problem logs that do not already belong to a resolved incident, oldest first
    problems = db.scalars(
        select(Log)
        .where(
            Log.project_id == project_id,
            Log.severity.in_(PROBLEM_LEVELS),
            Log.incident_id.is_(None),
        )
        .order_by(func.coalesce(Log.timestamp, Log.created_at), Log.id)
    ).all()

    created = 0
    for burst in split_into_bursts(problems):
        if not is_incident(burst):
            continue
        severity, _ = rate_severity(burst)
        title, affected = describe(burst)
        criticals, errors, _ = count_levels(burst)
        incident = Incident(
            project_id=project_id,
            title=title,
            severity=severity,
            affected_service=affected,
            error_count=criticals + errors,
        )
        db.add(incident)
        db.flush()  # gives the incident its id
        for log in burst:
            log.incident_id = incident.id
        created += 1

    db.commit()
    return created
