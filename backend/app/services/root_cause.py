"""Root cause ordering (Phase 8): where did the failure start?

An incident shows every service that failed, but most of them are only
victims. When the database stops, shop-api fails because it cannot reach the
database, and shop-web fails because shop-api returns errors. The database
itself may write nothing at all.

This module ranks the services of an incident from "probable origin" to
"affected", using four kinds of evidence. Each one gives points, and every
point comes with the reason, so the ranking can be checked:

  requests  (up to 50)  Logs that share a request ID (or trace ID) are one
                        request. The service that failed FIRST in a request
                        is that request's origin; the others failed after it.
  named     (up to 25)  "connection to shop-db failed", "shop-api did not
                        answer": an error that names another service means
                        the failure came from that service. This also finds
                        services that write no logs because they are down.
  traces    (up to 10)  In a failed trace, the deepest failing step is where
                        the error began (outer steps only pass it on).
  first     (15)        The service with the earliest error in the incident.
  monitor   (10)        The process monitor saw the service stop or crash.

It also draws the propagation chain (shop-db -> shop-api -> shop-web): the
order in which the failure spread, counted over all requests.
"""

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Log, Span
from app.services.incident_detector import ERROR_LEVELS, PROBLEM_LEVELS, error_label
from app.services.incidents import incident_logs

# How an error names the service it could not reach
TARGET_PATTERNS = [
    re.compile(r"\bconnect(?:ion|ing)? to ([A-Za-z][\w.-]*[A-Za-z0-9])"),
    re.compile(r"\b([A-Za-z][\w.-]*[A-Za-z0-9]) (?:unreachable|did not answer|is down|not responding)"),
]

# Monitor events that mean a process stopped or crashed. A planned restart
# ("Stopped for restart") is not a failure, so it does not count.
MONITOR_EVENTS = ("Exited unexpectedly", "Crash loop", "Gave up restarting", "Stopped", "Cannot start")
PLANNED = ("Stopped for restart",)

POINTS = {"requests": 50, "named": 25, "traces": 10, "first": 15, "monitor": 10}


def utc(moment):
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment)
    moment = moment.astimezone() if moment.tzinfo is None else moment
    return moment.astimezone(timezone.utc)


def when(log):
    return utc(log.timestamp or log.created_at)


def named_service(text, known, own):
    """The service an error message says it could not reach, if any."""
    for pattern in TARGET_PATTERNS:
        for name in pattern.findall(text or ""):
            if name != own and name in known:
                return name
    return None


def known_services(db, project_id):
    """Every service ever seen in the project (logs or spans)."""
    names = set(db.scalars(select(Log.service).where(Log.project_id == project_id).distinct()))
    names |= set(db.scalars(select(Span.service).where(Span.project_id == project_id).distinct()))
    return {name for name in names if name}


def request_sequences(logs, known):
    """For every request with a problem: the services in the order they failed.
    If the first failure names another service, that service goes first."""
    by_request = defaultdict(list)
    for log in logs:
        key = log.request_id or log.trace_id
        if key and log.severity in PROBLEM_LEVELS:
            by_request[key].append(log)

    sequences = {}
    for key, request_logs in by_request.items():
        request_logs.sort(key=lambda log: (when(log), log.id))
        order, first_log = [], {}
        for log in request_logs:
            service = log.service or "unknown"
            if service not in order:
                order.append(service)
                first_log[service] = log
        origin_log = request_logs[0]
        target = named_service(origin_log.message or origin_log.raw, known, origin_log.service)
        if target and target not in order:
            order.insert(0, target)
        sequences[key] = {"order": order, "first_log": first_log, "named": target}
    return sequences


def rank(db, incident, facts):
    """Ranks the services of an incident from probable origin to affected."""
    logs = incident_logs(db, incident.id)
    problems = [log for log in logs if log.severity in PROBLEM_LEVELS]
    known = known_services(db, incident.project_id)
    services = {log.service or "unknown" for log in problems}

    scores = defaultdict(float)
    reasons = defaultdict(list)
    details = defaultdict(lambda: {"origin_requests": 0, "affected_requests": 0, "named_by": 0, "first_failure": None})

    # 1. Requests: who failed first in each request
    sequences = request_sequences(problems, known)
    if sequences:
        origins = Counter(sequence["order"][0] for sequence in sequences.values())
        for sequence in sequences.values():
            for service in sequence["order"][1:]:
                details[service]["affected_requests"] += 1
        for service, count in origins.items():
            share = count / len(sequences)
            details[service]["origin_requests"] = count
            scores[service] += POINTS["requests"] * share
            reasons[service].append(f"origin of {count} of {len(sequences)} failed requests")
        for service, info in details.items():
            if info["affected_requests"] and not info["origin_requests"]:
                reasons[service].append(f"failed after another service in {info['affected_requests']} requests")
        services |= set(origins)

    # 2. Named: errors in other services that point at this one
    named = Counter()
    error_logs = [log for log in problems if log.severity in ERROR_LEVELS]
    for log in error_logs:
        target = named_service(log.message or log.raw, known, log.service)
        if target:
            named[target] += 1
    for service, count in named.items():
        scores[service] += POINTS["named"] * count / sum(named.values())
        details[service]["named_by"] = count
        reasons[service].append(f"named by {count} error(s) in other services")
        services.add(service)

    # 3. Traces: the deepest failing step of each failed trace
    deepest = Counter()
    failed_traces = 0
    if facts.get("first_seen") and facts.get("last_seen"):
        start = utc(facts["first_seen"]) - timedelta(seconds=5)
        end = utc(facts["last_seen"]) + timedelta(seconds=5)
        spans = db.scalars(
            select(Span).where(
                Span.project_id == incident.project_id, Span.start_time >= start, Span.start_time <= end
            )
        ).all()
        by_trace = defaultdict(list)
        for span in spans:
            by_trace[span.trace_id].append(span)
        for trace_spans in by_trace.values():
            failed = [span for span in trace_spans if span.status == "ERROR"]
            if not failed:
                continue
            failed_traces += 1
            ids = {span.span_id: span for span in trace_spans}

            def depth(span):
                level = 0
                while span.parent_span_id in ids and level < 50:
                    span, level = ids[span.parent_span_id], level + 1
                return level

            bottom = max(failed, key=depth)
            # A step that failed because it could not reach another service points there
            origin = named_service(bottom.status_message, known, bottom.service) or bottom.service
            deepest[origin] += 1
    for service, count in deepest.items():
        scores[service] += POINTS["traces"] * count / failed_traces
        reasons[service].append(f"deepest failing step in {count} of {failed_traces} failed traces")
        services.add(service)

    # 4. First: the earliest error of the incident
    if error_logs:
        first = min(error_logs, key=lambda log: (when(log), log.id))
        earliest = first.service or "unknown"
        scores[earliest] += POINTS["first"]
        reasons[earliest].append(f"earliest error of the incident ({error_label(first)})")
    for service in services:
        failures = [when(log) for log in problems if (log.service or "unknown") == service]
        if failures:
            details[service]["first_failure"] = min(failures).isoformat()

    # 5. Monitor: the process stopped or crashed during the incident
    if facts.get("first_seen") and facts.get("last_seen"):
        events = db.scalars(
            select(Log).where(
                Log.project_id == incident.project_id,
                Log.message.startswith("Process monitor:"),
            )
        ).all()
        start = utc(facts["first_seen"]) - timedelta(minutes=1)
        end = utc(facts["last_seen"]) + timedelta(seconds=5)
        stopped = {
            log.service for log in events
            if start <= when(log) <= end
            and any(word in log.message for word in MONITOR_EVENTS)
            and not any(word in log.message for word in PLANNED)
        }
        for service in stopped:
            scores[service] += POINTS["monitor"]
            reasons[service].append("the process monitor saw it stop or crash")
            services.add(service)

    ranking = sorted(services, key=lambda service: (-scores[service], details[service]["first_failure"] or "~"))
    result = []
    for index, service in enumerate(ranking):
        info = details[service]
        if index == 0 and scores[service] > 0:
            role = "probable origin"
        elif info["affected_requests"] or any(
            (log.service or "unknown") == service and log.severity in ERROR_LEVELS for log in problems
        ):
            role = "affected"
        else:
            role = "involved"
        result.append(
            {
                "service": service,
                "score": round(scores[service], 1),
                "role": role,
                "reasons": reasons[service] or ["no evidence that the failure started here"],
                **info,
            }
        )

    # The propagation chain: who failed after whom, counted over all requests
    edges = Counter()
    for sequence in sequences.values():
        order = sequence["order"]
        for before, after in zip(order, order[1:]):
            edges[(before, after)] += 1
    if not edges and len(result) > 1 and named:
        # No request IDs: link each named service to the services that named it
        for log in error_logs:
            target = named_service(log.message or log.raw, known, log.service)
            if target:
                edges[(target, log.service or "unknown")] += 1

    example = None
    if sequences:
        key, sequence = max(sequences.items(), key=lambda item: len(item[1]["order"]))
        example = {
            "request": key,
            "steps": [
                {
                    "service": service,
                    "time": when(sequence["first_log"][service]).isoformat() if service in sequence["first_log"] else None,
                    "message": (
                        (sequence["first_log"][service].message or sequence["first_log"][service].raw)[:200]
                        if service in sequence["first_log"]
                        else "wrote no log (named by the next service's error)"
                    ),
                }
                for service in sequence["order"]
            ],
        }

    top = result[0]["score"] if result else 0
    second = result[1]["score"] if len(result) > 1 else 0
    # Only "earliest error" (15 points) is too little evidence to be more than low
    if top >= 50 and top >= 2 * second:
        confidence = "high"
    elif top >= 25 and top > second:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "incident_id": incident.id,
        "method": "requests" if sequences else "timeline",
        "requests_analysed": len(sequences),
        "failed_traces": failed_traces,
        "confidence": confidence,
        "points": POINTS,
        "ranking": result,
        "propagation": [
            {"from": before, "to": after, "count": count} for (before, after), count in edges.most_common(10)
        ],
        "example": example,
    }
