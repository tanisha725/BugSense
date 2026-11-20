"""Investigation tools: the questions BugSense can answer about a failure.

Each tool has a name, a description and typed parameters. The same tools are
used by three callers:

  - the AI agent (Phase 7) - it chooses tools and parameters itself
  - the rule-based investigator - it calls them in a fixed order
  - the Tools page - a person fills in the parameters by hand

Every parameter is a field of a Pydantic model. That one model gives:
  1. the JSON Schema the AI model is shown (types, limits, allowed values)
  2. the validation of every call: a wrong type, an out-of-range number or
     an unknown parameter is refused with a clear message, never ignored
  3. the actual filter in the database query - no parameter is decorative

Tools only read. None of them changes data or runs a command.
"""

import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import func, select

from app.models import Incident, Log
from app.services import monitor, root_cause, telemetry
from app.services.incident_detector import ERROR_LEVELS, error_label
from app.services.incidents import find_incidents, incident_evidence, incident_facts

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
TRACE_ID = r"^[0-9a-fA-F]{32}$"


class ToolError(Exception):
    """A tool could not run: unknown tool, bad parameters, or nothing found."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Params(BaseModel):
    # Unknown parameters are an error, so a typo is never silently ignored
    model_config = ConfigDict(extra="forbid")


def aware(moment):
    """Times without a time zone are read as the computer's local time."""
    return moment.astimezone() if moment and moment.tzinfo is None else moment


def when(log):
    moment = log.timestamp or log.created_at
    return moment.astimezone() if moment.tzinfo is None else moment


def last_line(text):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def short_log(log, message_chars=220):
    """A log in few characters, so tool results stay small for the AI."""
    return {
        "id": log.id,
        "time": when(log).isoformat(timespec="seconds"),
        "severity": log.severity,
        "service": log.service,
        "error_type": log.error_type,
        "request_id": log.request_id,
        "trace_id": log.trace_id,
        "message": (log.message or log.raw)[:message_chars],
        "has_stack_trace": bool(log.stack_trace),
        # The last line of a stack trace names the real exception
        "exception": last_line(log.stack_trace)[:200] if log.stack_trace else None,
    }


# ---------- 1. list_incidents ----------


class ListIncidents(Params):
    project_id: int | None = Field(None, ge=1, description="Only this project. Leave out for all projects.")
    status: Literal["OPEN", "RESOLVED", "ALL"] = Field("OPEN", description="Which incidents to list.")
    min_severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = Field(
        None, description="Only incidents at least this serious."
    )
    service: str | None = Field(None, max_length=100, description="Only incidents involving this service (part of the name).")
    limit: int = Field(10, ge=1, le=50, description="Maximum number of incidents.")


def list_incidents(db, p: ListIncidents):
    items = find_incidents(db, p.project_id, p.status, p.min_severity, p.service, p.limit)
    return {
        "count": len(items),
        "incidents": [
            {
                key: item[key]
                for key in ("id", "project_id", "title", "severity", "status", "affected_service",
                            "error_count", "service_count", "first_seen", "last_seen")
            }
            for item in items
        ],
    }


# ---------- 2. get_incident ----------


class GetIncident(Params):
    incident_id: int = Field(ge=1, description="The incident to read.")
    log_limit: int = Field(20, ge=0, le=100, description="How many of its logs to include, oldest first.")
    errors_only: bool = Field(False, description="Include only ERROR and CRITICAL logs.")


def get_incident(db, p: GetIncident):
    incident = db.get(Incident, p.incident_id)
    if incident is None:
        raise ToolError(f"Incident {p.incident_id} not found", 404)
    evidence = incident_evidence(db, incident, p.log_limit, p.errors_only)
    logs = db.scalars(select(Log).where(Log.id.in_([log["id"] for log in evidence["logs"]]))).all()
    by_id = {log.id: log for log in logs}
    evidence["logs"] = [short_log(by_id[log["id"]]) for log in evidence["logs"]]
    evidence.pop("first_log_id", None)
    return evidence


# ---------- 3. search_logs ----------


class SearchLogs(Params):
    project_id: int | None = Field(None, ge=1, description="Only this project.")
    incident_id: int | None = Field(None, ge=1, description="Only logs grouped into this incident.")
    query: str | None = Field(None, max_length=200, description="Text that must appear in the log (not case-sensitive).")
    min_severity: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = Field(
        None, description="Only logs at least this severe."
    )
    service: str | None = Field(None, max_length=100, description="Only this service (part of the name).")
    error_type: str | None = Field(None, max_length=100, description="Only this error type, e.g. TimeoutError.")
    request_id: str | None = Field(None, max_length=100, description="Only logs of this request, across all services.")
    trace_id: str | None = Field(None, pattern=TRACE_ID, description="Only logs of this OpenTelemetry trace.")
    since: datetime | None = Field(None, description="Only logs at or after this time (ISO 8601).")
    until: datetime | None = Field(None, description="Only logs at or before this time (ISO 8601).")
    order: Literal["oldest", "newest"] = Field("oldest", description="oldest finds where a problem began.")
    limit: int = Field(20, ge=1, le=100, description="Maximum number of logs.")

    @model_validator(mode="after")
    def since_before_until(self):
        if self.since and self.until and aware(self.since) > aware(self.until):
            raise ValueError("since must be before until")
        return self


def search_logs(db, p: SearchLogs):
    moment = func.coalesce(Log.timestamp, Log.created_at)
    query = select(Log)
    if p.project_id:
        query = query.where(Log.project_id == p.project_id)
    if p.incident_id:
        query = query.where(Log.incident_id == p.incident_id)
    if p.query:
        query = query.where(Log.raw.icontains(p.query, autoescape=True))
    if p.min_severity:
        query = query.where(Log.severity.in_(LEVELS[LEVELS.index(p.min_severity):]))
    if p.service:
        query = query.where(Log.service.icontains(p.service, autoescape=True))
    if p.error_type:
        query = query.where(func.lower(Log.error_type) == p.error_type.lower())
    if p.request_id:
        query = query.where(Log.request_id == p.request_id)
    if p.trace_id:
        query = query.where(Log.trace_id == p.trace_id.lower())
    if p.since:
        query = query.where(moment >= aware(p.since))
    if p.until:
        query = query.where(moment <= aware(p.until))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    ordering = (moment, Log.id) if p.order == "oldest" else (moment.desc(), Log.id.desc())
    logs = db.scalars(query.order_by(*ordering).limit(p.limit)).all()
    return {"total_matching": total, "returned": len(logs), "logs": [short_log(log) for log in logs]}


# ---------- 4. get_error_timeline ----------


class ErrorTimeline(Params):
    incident_id: int | None = Field(None, ge=1, description="The incident to look at.")
    project_id: int | None = Field(None, ge=1, description="Or a whole project (used when no incident_id is given).")
    bucket_seconds: int = Field(60, ge=1, le=3600, description="Size of each time bucket.")
    service: str | None = Field(None, max_length=100, description="Only this service (part of the name).")

    @model_validator(mode="after")
    def needs_a_target(self):
        if self.incident_id is None and self.project_id is None:
            raise ValueError("give incident_id or project_id")
        return self


def get_error_timeline(db, p: ErrorTimeline):
    """When each service started failing: the first failure often points at the cause."""
    query = select(Log).where(Log.severity.in_(ERROR_LEVELS))
    if p.incident_id:
        query = query.where(Log.incident_id == p.incident_id)
    else:
        query = query.where(Log.project_id == p.project_id)
    if p.service:
        query = query.where(Log.service.icontains(p.service, autoescape=True))
    logs = sorted(db.scalars(query).all(), key=lambda log: (when(log), log.id))
    if not logs:
        return {"errors": 0, "first_errors": [], "buckets": []}

    start = when(logs[0])
    first_by_service = {}
    buckets = defaultdict(Counter)
    for log in logs:
        service = log.service or "unknown"
        first_by_service.setdefault(service, log)
        index = int((when(log) - start).total_seconds() // p.bucket_seconds)
        buckets[index][service] += 1

    return {
        "errors": len(logs),
        # In the order the services started failing
        "first_errors": [
            {
                "service": service,
                "time": when(log).isoformat(timespec="seconds"),
                "seconds_after_first": round((when(log) - start).total_seconds(), 1),
                "error": error_label(log),
                "message": (log.message or log.raw)[:200],
            }
            for service, log in first_by_service.items()
        ],
        "buckets": [
            {
                "start": (start + timedelta(seconds=index * p.bucket_seconds)).isoformat(timespec="seconds"),
                "by_service": dict(counter),
            }
            for index, counter in sorted(buckets.items())
        ][:60],
    }


# ---------- 5. get_service_status ----------


class ServiceStatus(Params):
    service: Literal[tuple(monitor.SERVICES)] | None = Field(  # type: ignore[valid-type]
        None, description="One demo service. Leave out for all of them."
    )
    event_limit: int = Field(10, ge=0, le=40, description="How many recent monitor events to include.")
    since: datetime | None = Field(
        None, description="Only monitor events at or after this time (ISO 8601), e.g. the incident start."
    )


def get_service_status(db, p: ServiceStatus):
    """Process facts from the monitor: running or not, health, restarts, exit code."""
    status = monitor.status()
    services = [
        # The switched-on demo fault is left out on purpose: it is the answer, not evidence
        {key: value for key, value in service.items() if key not in ("fault", "description")}
        for service in status["services"]
        if p.service is None or service["name"] == p.service
    ]
    events = [
        event for event in status["events"]
        if (p.service is None or event["service"] == p.service)
        and (p.since is None or aware(datetime.fromisoformat(event["time"])) >= aware(p.since))
    ]
    return {"monitoring": status["monitoring"], "services": services, "events": events[: p.event_limit]}


# ---------- 6. get_service_metrics ----------


class ServiceMetrics(Params):
    project_id: int | None = Field(None, ge=1, description="Only this project.")
    service: str | None = Field(None, max_length=100, description="One service (exact name). Leave out for all.")
    window_minutes: int = Field(5, ge=1, le=43200, description="How many minutes to summarise.")
    until: datetime | None = Field(None, description="End of the window (ISO 8601). Default: now.")


def get_service_metrics(db, p: ServiceMetrics):
    """Telemetry summary: requests, error rate, latency p50/p95/p99, CPU, memory."""
    return telemetry.service_overview(db, p.project_id, p.window_minutes, p.service, aware(p.until))


# ---------- 7. get_metric_series ----------


class MetricSeries(Params):
    metric: str = Field(
        max_length=255,
        description="A received metric (e.g. http.server.request.duration, process.cpu.time) "
        "or one derived from spans: requests, errors, error_rate, latency.",
    )
    project_id: int | None = Field(None, ge=1, description="Only this project.")
    service: str | None = Field(None, max_length=100, description="One service (exact name).")
    window_minutes: int = Field(15, ge=1, le=43200, description="How many minutes back.")
    step_seconds: int = Field(60, ge=5, le=3600, description="Size of each point in seconds.")
    aggregation: Literal[telemetry.AGGREGATIONS] = Field(  # type: ignore[valid-type]
        "avg", description="How the values in one step are combined."
    )
    until: datetime | None = Field(None, description="End of the window (ISO 8601). Default: now.")


def get_metric_series(db, p: MetricSeries):
    series = telemetry.metric_series(
        db, p.project_id, p.service, p.metric, p.window_minutes, p.step_seconds, p.aggregation, aware(p.until)
    )
    series["points"] = [point for point in series["points"] if point["value"] is not None]
    return series


# ---------- 8. search_traces ----------


class SearchTraces(Params):
    project_id: int | None = Field(None, ge=1, description="Only this project.")
    service: str | None = Field(None, max_length=100, description="Only traces that pass through this service.")
    status: Literal["ANY", "ERROR", "OK"] = Field("ANY", description="ERROR finds failed requests.")
    min_duration_ms: float | None = Field(None, ge=0, description="Only requests at least this slow.")
    window_minutes: int = Field(15, ge=1, le=43200, description="How many minutes back.")
    until: datetime | None = Field(None, description="End of the window (ISO 8601). Default: now.")
    limit: int = Field(10, ge=1, le=50, description="Maximum number of traces.")


def search_traces(db, p: SearchTraces):
    traces = telemetry.search_traces(
        db, p.project_id, p.service, p.status, p.min_duration_ms, p.window_minutes, p.limit, aware(p.until)
    )
    return {"count": len(traces), "traces": traces}


# ---------- 9. get_trace ----------


class GetTrace(Params):
    trace_id: str = Field(pattern=TRACE_ID, description="The 32-character trace ID.")
    include_logs: bool = Field(True, description="Also return the logs written during this request.")


def get_trace(db, p: GetTrace):
    """One request hop by hop: which service called which, how long each took, where it failed."""
    trace = telemetry.get_trace(db, p.trace_id.lower(), p.include_logs)
    if trace is None:
        raise ToolError(f"Trace {p.trace_id} not found", 404)
    for span in trace["spans"]:
        if not span["attributes"]:
            del span["attributes"]
    return trace


# ---------- 10. rank_root_causes ----------


class RankRootCauses(Params):
    incident_id: int = Field(ge=1, description="The incident to analyse.")
    top: int = Field(5, ge=1, le=20, description="How many services of the ranking to return.")


def rank_root_causes(db, p: RankRootCauses):
    """Which service the failure started in, and which ones only failed after it."""
    incident = db.get(Incident, p.incident_id)
    if incident is None:
        raise ToolError(f"Incident {p.incident_id} not found", 404)
    facts = incident_facts(db, [incident.id]).get(incident.id, {})
    result = root_cause.rank(db, incident, facts)
    result["ranking"] = result["ranking"][: p.top]
    return result


# ---------- The registry ----------

TOOLS = {
    "list_incidents": (ListIncidents, list_incidents, "List incidents, most serious first."),
    "get_incident": (
        GetIncident, get_incident,
        "Read one incident: severity and why, services involved, top errors and its first logs.",
    ),
    "search_logs": (
        SearchLogs, search_logs,
        "Search logs by text, severity, service, error type, request ID, trace ID and time range.",
    ),
    "get_error_timeline": (
        ErrorTimeline, get_error_timeline,
        "When each service started failing, in order, and errors per time bucket. "
        "The service that failed first is often where the problem began.",
    ),
    "get_service_status": (
        ServiceStatus, get_service_status,
        "Process status of the monitored services: running, crashed or crash loop, health check, "
        "restarts, last exit code, and recent monitor events.",
    ),
    "get_service_metrics": (
        ServiceMetrics, get_service_metrics,
        "OpenTelemetry summary per service: request count, error rate, latency p50/p95/p99, CPU and memory.",
    ),
    "get_metric_series": (
        MetricSeries, get_metric_series,
        "One OpenTelemetry metric over time, to see when a change started.",
    ),
    "search_traces": (
        SearchTraces, search_traces,
        "Find recent requests (traces), for example the failed or the slow ones.",
    ),
    "get_trace": (
        GetTrace, get_trace,
        "Follow one request across services, span by span, with its logs.",
    ),
    "rank_root_causes": (
        RankRootCauses, rank_root_causes,
        "Rank the services of an incident from probable origin to affected, with the reasons, "
        "and show how the failure spread (for example shop-db -> shop-api -> shop-web).",
    ),
}


def clean_schema(schema):
    """The JSON Schema of a parameter model, without the noise Pydantic adds."""
    if isinstance(schema, dict):
        return {key: clean_schema(value) for key, value in schema.items() if key != "title"}
    if isinstance(schema, list):
        return [clean_schema(item) for item in schema]
    return schema


def definitions(names=None):
    """Tools with their parameter schemas (what the AI model and the Tools page
    see). names: only these tools (default: all of them)."""
    return [
        {"name": name, "description": description, "parameters": clean_schema(model.model_json_schema())}
        for name, (model, _, description) in TOOLS.items()
        if names is None or name in names
    ]


def explain(error):
    """A Pydantic validation error as one readable sentence."""
    parts = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"]) or "parameters"
        parts.append(f"{where}: {item['msg']}")
    return "; ".join(parts)


def run_tool(db, name, arguments):
    """Validates the parameters, runs the tool, and returns its result."""
    if name not in TOOLS:
        raise ToolError(f"Unknown tool '{name}'. Known tools: {', '.join(TOOLS)}", 404)
    model, function, _ = TOOLS[name]
    try:
        params = model.model_validate(arguments or {})
    except ValidationError as problem:
        raise ToolError(f"Invalid parameters for {name}: {explain(problem)}", 422) from problem
    started = time.perf_counter()
    result = function(db, params)
    return {
        "tool": name,
        "parameters": params.model_dump(mode="json", exclude_none=True),
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        "result": result,
    }
