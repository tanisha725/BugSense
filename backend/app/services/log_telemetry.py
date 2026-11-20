"""Telemetry from uploaded logs ("metrics from logs").

Uploaded logs are records of the past, so nothing can be measured live. But
the logs themselves contain telemetry, and BugSense calculates it:

  traces     Logs that share a request ID describe one request. Each service
             that logged it becomes one span: it starts at the service's first
             log of that request, and fails if any of those logs is an error.
             The service that logged the request first is the root.
  latency    "GET /checkout 200 in 19 ms", "took 2.3 s": the duration written
             in a log line becomes the span's duration.
  activity   Logs per minute for every service, split by severity, as the
             metric "log.records". This works for any logs, even without
             request IDs.

Everything calculated here is stored with source="logs", next to the measured
OpenTelemetry data (source="otel"), so the Telemetry page, the tools and the
AI diagnosis work for uploaded logs too, and it is always clear which numbers
were measured and which were calculated.

The calculation is redone for the whole project after every upload, so it
always matches the logs that are stored.
"""

import hashlib
import re
from collections import Counter, defaultdict
from datetime import timedelta, timezone

from sqlalchemy import delete, select

from app.models import Log, MetricPoint, Span
from app.services.incident_detector import ERROR_LEVELS, message_template

SOURCE = "logs"
UNKNOWN_SERVICE = "unknown"

# "in 19 ms", "took 2.3 s", "duration=120ms", "latency: 45 ms", "elapsed 1.2s",
# "timed out after 3000 ms"
DURATION = re.compile(
    r"\b(?:in|took|after|duration|latency|elapsed|time)[=:]?\s*(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|seconds)\b",
    re.IGNORECASE,
)
# OpenStack's API log: "status: 200 len: 1916 time: 0.2717581" (seconds, no unit)
SECONDS_WITHOUT_UNIT = re.compile(r"\btime[=:]\s*(\d+\.\d+)\s*$")


def when(log):
    """The log's time in UTC, like OpenTelemetry times. Times without a time
    zone are the computer's local time."""
    moment = log.timestamp or log.created_at
    moment = moment.astimezone() if moment.tzinfo is None else moment
    return moment.astimezone(timezone.utc)


def duration_ms(text):
    """A duration written in a log line, in milliseconds, or None."""
    match = DURATION.search(text or "")
    if not match:
        bare = SECONDS_WITHOUT_UNIT.search(text or "")
        return float(bare.group(1)) * 1000 if bare else None
    value = float(match.group(1))
    return value if match.group(2).lower().startswith("m") else value * 1000


def trace_id_for(project_id, request_id):
    """A stable 32-character trace ID for a request ID (the same every time)."""
    return hashlib.md5(f"{project_id}:{request_id}".encode()).hexdigest()


def span_id_for(trace_id, service):
    return hashlib.md5(f"{trace_id}:{service}".encode()).hexdigest()[:16]


def request_spans(project_id, logs):
    """One span per service per request ID."""
    by_request = defaultdict(list)
    for log in logs:
        if log.request_id:
            by_request[log.request_id].append(log)

    spans = []
    for request_id, request_logs in by_request.items():
        request_logs.sort(key=lambda log: (when(log), log.id))
        # A log's own trace ID (from OpenTelemetry) wins over the calculated one
        trace_id = next((log.trace_id for log in request_logs if log.trace_id), None) or trace_id_for(
            project_id, request_id
        )
        by_service = defaultdict(list)
        for log in request_logs:
            by_service[log.service or UNKNOWN_SERVICE].append(log)

        root_service = request_logs[0].service or UNKNOWN_SERVICE
        root_id = span_id_for(trace_id, root_service)
        for service, service_logs in by_service.items():
            start = when(service_logs[0])
            written = [duration_ms(log.message or log.raw) for log in service_logs]
            written = [value for value in written if value is not None]
            if written:
                took = max(written)
            else:
                took = (when(service_logs[-1]) - start).total_seconds() * 1000
            errors = [log for log in service_logs if log.severity in ERROR_LEVELS]
            first = errors[0] if errors else service_logs[0]
            spans.append(
                Span(
                    project_id=project_id,
                    trace_id=trace_id,
                    span_id=span_id_for(trace_id, service),
                    parent_span_id=None if service == root_service else root_id,
                    service=service,
                    name=message_template(first.message or first.raw)[:120] or "request",
                    kind="SERVER",
                    start_time=start,
                    end_time=start + timedelta(milliseconds=took),
                    duration_ms=took,
                    status="ERROR" if errors else "UNSET",
                    status_message=(errors[0].message or errors[0].raw)[:300] if errors else None,
                    attributes={"request_id": request_id, "log_count": len(service_logs)},
                    source=SOURCE,
                )
            )
    return spans


def activity_points(project_id, logs):
    """Logs per minute for each service and severity (metric "log.records")."""
    counts = Counter()
    for log in logs:
        minute = when(log).replace(second=0, microsecond=0)
        counts[(log.service or UNKNOWN_SERVICE, log.severity or "UNKNOWN", minute)] += 1
    return [
        MetricPoint(
            project_id=project_id,
            service=service,
            name="log.records",
            kind="sum",
            unit="1",
            temporality="DELTA",
            time=minute + timedelta(seconds=59),  # a point stands for the minute that just ended
            value=count,
            attributes={"severity": severity},
            source=SOURCE,
        )
        for (service, severity, minute), count in counts.items()
    ]


def rebuild(db, project_id):
    """Recalculates the telemetry of one project from all its logs.
    Measured OpenTelemetry data is never touched. Returns what was made."""
    db.execute(delete(Span).where(Span.project_id == project_id, Span.source == SOURCE))
    db.execute(delete(MetricPoint).where(MetricPoint.project_id == project_id, MetricPoint.source == SOURCE))

    # Services that already send real OpenTelemetry data do not get
    # calculated copies (that would count their requests twice)
    measured = set(
        db.scalars(select(Span.service).where(Span.project_id == project_id, Span.source == "otel").distinct())
    )
    logs = [
        log for log in db.scalars(select(Log).where(Log.project_id == project_id))
        if (log.service or UNKNOWN_SERVICE) not in measured
    ]
    spans = request_spans(project_id, logs)
    points = activity_points(project_id, logs)
    db.add_all(spans)
    db.add_all(points)
    db.commit()
    return {
        "logs": len(logs),
        "spans": len(spans),
        "traces": len({span.trace_id for span in spans}),
        "metric_points": len(points),
    }


def clear(db, project_id=None):
    """Removes calculated telemetry (of one project, or all), e.g. when its logs are deleted."""
    spans = delete(Span).where(Span.source == SOURCE)
    points = delete(MetricPoint).where(MetricPoint.source == SOURCE)
    if project_id:
        spans = spans.where(Span.project_id == project_id)
        points = points.where(MetricPoint.project_id == project_id)
    db.execute(spans)
    db.execute(points)
    db.commit()
