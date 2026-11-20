"""Telemetry analysis: what the received traces and metrics say about each service.

Requests, errors and latency come from the spans (the "RED" method used by
monitoring tools: Rate, Errors, Duration). CPU and memory come from the
metrics each service reports about its own process.

The alert check turns telemetry into logs: when a service's error rate or
latency crosses a limit, a log such as "Telemetry: error rate 45% over the
last 60 s (limit 20%)" is stored. Incident detection then puts it into the
same incident as the errors it belongs to.
"""

import math
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Log, MetricPoint, Span

# Alert limits, checked over the last ALERT_WINDOW seconds
ALERT_WINDOW = 60
ERROR_RATE_LIMIT = 0.20  # 20% of requests failing
LATENCY_LIMIT_MS = 1000  # p95 latency above one second
MIN_REQUESTS = 5  # fewer requests than this is too little to judge
ALERT_EVERY = 10  # seconds between checks of one project

# Metrics derived from spans, usable wherever a metric name is expected
SPAN_METRICS = ("requests", "errors", "error_rate", "latency")
AGGREGATIONS = ("avg", "sum", "min", "max", "count", "rate", "p50", "p95", "p99", "last")


def now():
    return datetime.now(timezone.utc)


def as_utc(moment):
    """SQLite gives times back without a time zone. They were stored as UTC."""
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


def percentile(values, share):
    """Nearest-rank percentile: percentile([...], 0.95) is the p95."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(share * len(ordered)) - 1))
    return ordered[index]


def is_entry_span(span):
    """A span that is one request *to* this service: a SERVER span, or the
    first span of a trace (a service like shop-web starts requests itself)."""
    return span.kind == "SERVER" or span.parent_span_id is None


def entry_spans(db, project_id, since, until=None, service=None):
    query = select(Span).where(Span.start_time >= since)
    if until:
        query = query.where(Span.start_time <= until)
    if project_id:
        query = query.where(Span.project_id == project_id)
    if service:
        query = query.where(Span.service == service)
    return [span for span in db.scalars(query) if is_entry_span(span)]


def red_numbers(spans, seconds):
    """Rate, errors and duration of a list of entry spans."""
    durations = [span.duration_ms for span in spans]
    errors = sum(1 for span in spans if span.status == "ERROR")
    return {
        "requests": len(spans),
        "errors": errors,
        "error_rate": round(errors / len(spans), 4) if spans else 0.0,
        "requests_per_minute": round(len(spans) * 60 / seconds, 2),
        "latency_ms": {
            "avg": round(sum(durations) / len(durations), 1) if durations else None,
            "p50": round(percentile(durations, 0.50), 1) if durations else None,
            "p95": round(percentile(durations, 0.95), 1) if durations else None,
            "p99": round(percentile(durations, 0.99), 1) if durations else None,
            "max": round(max(durations), 1) if durations else None,
        },
    }


# ---------- Metric points ----------


def metric_points(db, project_id, service, name, since, until=None):
    query = select(MetricPoint).where(MetricPoint.name == name, MetricPoint.time >= since)
    if until:
        query = query.where(MetricPoint.time <= until)
    if project_id:
        query = query.where(MetricPoint.project_id == project_id)
    if service:
        query = query.where(MetricPoint.service == service)
    return db.scalars(query.order_by(MetricPoint.time)).all()


def as_deltas(points):
    """Counter and histogram points as increases. DELTA points already are;
    CUMULATIVE points become the difference with the previous point of the
    same series (same service and attributes)."""
    previous = {}
    result = []
    for point in points:
        if point.temporality != "CUMULATIVE":
            result.append((point, point.value, point.count, point.bucket_counts))
            continue
        key = (point.service, tuple(sorted((point.attributes or {}).items())))
        before = previous.get(key)
        previous[key] = point
        if before is None:
            continue  # the first cumulative point has nothing to compare with
        buckets = None
        if point.bucket_counts and before.bucket_counts:
            buckets = [max(0, a - b) for a, b in zip(point.bucket_counts, before.bucket_counts)]
        count = None if point.count is None else max(0, point.count - (before.count or 0))
        result.append((point, max(0.0, point.value - before.value), count, buckets))
    return result


def histogram_percentile(bounds, counts, share):
    """Estimates a percentile from histogram buckets (upper bound of the bucket)."""
    total = sum(counts)
    if not total:
        return None
    needed = share * total
    running = 0
    for index, count in enumerate(counts):
        running += count
        if running >= needed:
            return bounds[index] if index < len(bounds) else (bounds[-1] if bounds else None)
    return bounds[-1] if bounds else None


def aggregate_points(points, aggregation, seconds):
    """One number from the metric points of one time slot."""
    if not points:
        return None
    kind = points[0].kind
    if kind == "gauge":
        values = [point.value for point in points]
        if aggregation == "last":
            return values[-1]
        if aggregation in ("p50", "p95", "p99"):
            return percentile(values, int(aggregation[1:]) / 100)
        if aggregation == "rate":
            return None
        return {"avg": sum(values) / len(values), "sum": sum(values), "min": min(values),
                "max": max(values), "count": len(values)}[aggregation]

    deltas = as_deltas(points)
    if not deltas:
        return None
    if kind == "sum":
        increases = [value for _, value, _, _ in deltas]
        return {
            "sum": sum(increases), "rate": sum(increases) / seconds, "count": len(increases),
            "avg": sum(increases) / len(increases), "min": min(increases), "max": max(increases),
            "last": increases[-1], "p50": percentile(increases, 0.5), "p95": percentile(increases, 0.95),
            "p99": percentile(increases, 0.99),
        }[aggregation]

    # Histogram: merge the buckets of every point in the slot
    total = sum(value for _, value, _, _ in deltas)
    count = sum(count or 0 for _, _, count, _ in deltas)
    bounds = deltas[-1][0].bounds or []
    merged = [0] * (len(bounds) + 1)
    for _, _, _, buckets in deltas:
        for index, value in enumerate(buckets or []):
            if index < len(merged):
                merged[index] += value
    if aggregation in ("p50", "p95", "p99"):
        return histogram_percentile(bounds, merged, int(aggregation[1:]) / 100)
    return {
        "avg": total / count if count else None, "sum": total, "count": count,
        "rate": count / seconds, "min": None, "max": None, "last": total / count if count else None,
    }[aggregation]


def process_numbers(db, project_id, service, since, until, seconds):
    """CPU (percent of one core) and peak memory (MB) from the process metrics."""
    cpu = aggregate_points(
        metric_points(db, project_id, service, "process.cpu.time", since, until), "sum", seconds
    )
    memory = aggregate_points(
        metric_points(db, project_id, service, "process.memory.usage", since, until), "last", seconds
    )
    return {
        "cpu_percent": round(cpu / seconds * 100, 2) if cpu is not None else None,
        "memory_mb": round(memory / 1e6, 1) if memory is not None else None,
    }


# ---------- What the API and the tools ask for ----------


def service_overview(db, project_id=None, window_minutes=5, service=None, until=None):
    """RED numbers plus CPU and memory for every service seen in the window
    that ends at `until` (default: now)."""
    seconds = window_minutes * 60
    end = until.astimezone(timezone.utc) if until else now()
    since = end - timedelta(seconds=seconds)
    spans = entry_spans(db, project_id, since, end, service)
    by_service = defaultdict(list)
    for span in spans:
        by_service[span.service].append(span)

    # Services that only sent metrics are listed too
    metric_query = (
        select(MetricPoint.service).where(MetricPoint.time >= since, MetricPoint.time <= end).distinct()
    )
    if project_id:
        metric_query = metric_query.where(MetricPoint.project_id == project_id)
    if service:
        metric_query = metric_query.where(MetricPoint.service == service)
    names = sorted(set(by_service) | set(db.scalars(metric_query)))

    result = []
    for name in names:
        service_spans = by_service.get(name, [])
        last = max((as_utc(span.end_time) for span in service_spans), default=None)
        result.append(
            {
                "service": name,
                **red_numbers(service_spans, seconds),
                **process_numbers(db, project_id, name, since, end, seconds),
                "last_seen": last.isoformat() if last else None,
            }
        )
    return {"window_minutes": window_minutes, "until": end.isoformat(), "services": result}


def metric_series(db, project_id, service, metric, window_minutes=15, step_seconds=60, aggregation="avg",
                  until=None):
    """One metric over time, in slots of step_seconds.

    metric is a received metric name (for example http.server.request.duration)
    or one of the span-derived metrics: requests, errors, error_rate, latency.
    """
    end = until.astimezone(timezone.utc) if until else now()
    seconds = window_minutes * 60
    start = end - timedelta(seconds=seconds)
    slot_count = max(1, min(240, seconds // step_seconds))
    step = timedelta(seconds=seconds / slot_count)
    slots = [{"start": (start + step * index).isoformat(), "value": None} for index in range(slot_count)]

    def slot_of(moment):
        return min(int((as_utc(moment) - start) / step), slot_count - 1)

    if metric in SPAN_METRICS:
        grouped = defaultdict(list)
        for span in entry_spans(db, project_id, start, end, service):
            grouped[slot_of(span.start_time)].append(span)
        for index, spans in grouped.items():
            durations = [span.duration_ms for span in spans]
            errors = sum(1 for span in spans if span.status == "ERROR")
            if metric == "requests":
                value = len(spans) / step.total_seconds() if aggregation == "rate" else len(spans)
            elif metric == "errors":
                value = errors / step.total_seconds() if aggregation == "rate" else errors
            elif metric == "error_rate":
                value = errors / len(spans)
            elif aggregation in ("p50", "p95", "p99"):
                value = percentile(durations, int(aggregation[1:]) / 100)
            elif aggregation in ("min", "max"):
                value = min(durations) if aggregation == "min" else max(durations)
            elif aggregation == "sum":
                value = sum(durations)
            elif aggregation == "count":
                value = len(durations)
            else:
                value = sum(durations) / len(durations)
            slots[index]["value"] = round(value, 4)
        unit = {"requests": "1", "errors": "1", "error_rate": "ratio", "latency": "ms"}[metric]
    else:
        points = metric_points(db, project_id, service, metric, start, end)
        grouped = defaultdict(list)
        for point in points:
            grouped[slot_of(point.time)].append(point)
        for index, slot_points in grouped.items():
            value = aggregate_points(slot_points, aggregation, step.total_seconds())
            slots[index]["value"] = None if value is None else round(value, 6)
        unit = points[0].unit if points else None

    return {
        "service": service,
        "metric": metric,
        "aggregation": aggregation,
        "unit": unit,
        "step_seconds": round(step.total_seconds(), 1),
        "points": slots,
    }


def metric_names(db, project_id=None, service=None):
    """Every metric name received, with its kind and unit."""
    query = select(MetricPoint.name, MetricPoint.kind, MetricPoint.unit).distinct()
    if project_id:
        query = query.where(MetricPoint.project_id == project_id)
    if service:
        query = query.where(MetricPoint.service == service)
    received = [{"name": name, "kind": kind, "unit": unit} for name, kind, unit in db.execute(query)]
    derived = [{"name": name, "kind": "from spans", "unit": None} for name in SPAN_METRICS]
    return sorted(received, key=lambda item: item["name"]) + derived


def search_traces(db, project_id=None, service=None, status="ANY", min_duration_ms=None,
                  window_minutes=15, limit=20, until=None):
    """Traces in the window that ends at `until` (default: now), newest first,
    one line per request."""
    end = until.astimezone(timezone.utc) if until else now()
    since = end - timedelta(minutes=window_minutes)
    query = select(Span).where(Span.start_time >= since, Span.start_time <= end)
    if project_id:
        query = query.where(Span.project_id == project_id)
    traces = defaultdict(list)
    for span in db.scalars(query):
        traces[span.trace_id].append(span)

    result = []
    for trace_id, spans in traces.items():
        root = next((span for span in spans if span.parent_span_id is None), None) or min(
            spans, key=lambda span: span.start_time
        )
        services = sorted({span.service for span in spans})
        failed = [span for span in spans if span.status == "ERROR"]
        if service and service not in services:
            continue
        if status == "ERROR" and not failed:
            continue
        if status == "OK" and failed:
            continue
        if min_duration_ms is not None and root.duration_ms < min_duration_ms:
            continue
        result.append(
            {
                "trace_id": trace_id,
                "root": f"{root.service}: {root.name}",
                "start_time": as_utc(root.start_time).isoformat(),
                "duration_ms": round(root.duration_ms, 1),
                "span_count": len(spans),
                "services": services,
                "error": bool(failed),
                "first_error": (
                    f"{failed[0].service}: {failed[0].status_message or failed[0].name}" if failed else None
                ),
            }
        )
    result.sort(key=lambda item: item["start_time"], reverse=True)
    return result[:limit]


def get_trace(db, trace_id, include_logs=True):
    """Every span of one trace as a tree (depth and offset), plus its logs."""
    spans = db.scalars(select(Span).where(Span.trace_id == trace_id).order_by(Span.start_time)).all()
    if not spans:
        return None
    by_id = {span.span_id: span for span in spans}
    trace_start = min(as_utc(span.start_time) for span in spans)

    def depth(span):
        level, seen = 0, set()
        while span.parent_span_id in by_id and span.span_id not in seen:
            seen.add(span.span_id)
            span = by_id[span.parent_span_id]
            level += 1
        return level

    result = {
        "trace_id": trace_id,
        "duration_ms": round(
            max((as_utc(span.end_time) - trace_start).total_seconds() * 1000 for span in spans), 1
        ),
        "spans": [
            {
                "span_id": span.span_id,
                "parent_span_id": span.parent_span_id,
                "service": span.service,
                "name": span.name,
                "kind": span.kind,
                "depth": depth(span),
                "offset_ms": round((as_utc(span.start_time) - trace_start).total_seconds() * 1000, 1),
                "duration_ms": round(span.duration_ms, 1),
                "status": span.status,
                "status_message": span.status_message,
                "attributes": span.attributes,
            }
            for span in spans
        ],
    }
    if include_logs:
        logs = db.scalars(select(Log).where(Log.trace_id == trace_id).order_by(Log.id)).all()
        result["logs"] = [
            {"service": log.service, "severity": log.severity, "message": log.message or log.raw}
            for log in logs
        ]
    return result


# ---------- Alerts: telemetry becomes evidence ----------

_alert_state = {}  # (project_id, service, kind) -> True while the alert is on
_last_check = {}
_alert_lock = threading.Lock()


def _alert_log(project_id, service, severity, message, error_type):
    moment = datetime.now().astimezone()
    return Log(
        project_id=project_id,
        raw=f"{moment:%Y-%m-%d %H:%M:%S} {severity} [{service}] Telemetry: {message}",
        timestamp=moment,
        severity=severity,
        service=service,
        error_type=error_type,
        message=f"Telemetry: {message}",
    )


def check_alerts(db, project_id, force=False):
    """Compares each service's last minute with the limits. Stores a log when
    an alert starts or ends (not on every check). Returns the new logs."""
    with _alert_lock:
        if not force and time.time() - _last_check.get(project_id, 0) < ALERT_EVERY:
            return []
        _last_check[project_id] = time.time()

        since = now() - timedelta(seconds=ALERT_WINDOW)
        by_service = defaultdict(list)
        for span in entry_spans(db, project_id, since):
            by_service[span.service].append(span)

        new_logs = []
        for service, spans in by_service.items():
            if len(spans) < MIN_REQUESTS:
                continue
            numbers = red_numbers(spans, ALERT_WINDOW)
            checks = [
                (
                    "error_rate",
                    numbers["error_rate"] >= ERROR_RATE_LIMIT,
                    "ERROR",
                    f"error rate {numbers['error_rate']:.0%} over the last {ALERT_WINDOW} s "
                    f"({numbers['errors']} of {numbers['requests']} requests failed, limit {ERROR_RATE_LIMIT:.0%})",
                    "HighErrorRate",
                ),
                (
                    "latency",
                    (numbers["latency_ms"]["p95"] or 0) >= LATENCY_LIMIT_MS,
                    "WARNING",
                    f"p95 latency {numbers['latency_ms']['p95']:.0f} ms over the last {ALERT_WINDOW} s "
                    f"(limit {LATENCY_LIMIT_MS} ms)",
                    "HighLatency",
                ),
            ]
            for kind, broken, severity, message, error_type in checks:
                key = (project_id, service, kind)
                was_on = _alert_state.get(key, False)
                if broken and not was_on:
                    new_logs.append(_alert_log(project_id, service, severity, message, error_type))
                elif was_on and not broken:
                    label = "error rate" if kind == "error_rate" else "latency"
                    new_logs.append(_alert_log(project_id, service, "INFO", f"{label} back to normal", None))
                _alert_state[key] = broken

        if new_logs:
            db.add_all(new_logs)
            db.commit()
        return new_logs


def reset_alerts():
    """Forgets alert state (used by tests)."""
    with _alert_lock:
        _alert_state.clear()
        _last_check.clear()
