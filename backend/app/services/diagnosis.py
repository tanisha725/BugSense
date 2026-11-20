"""Diagnosis (Phase 7): the probable cause of an incident.

Two engines investigate with the SAME tools (services/tools.py):

  llm    an AI model decides which tools to call and with which parameters,
         reads the results, and writes the probable cause. It is given only
         what the tools return - compact facts - never the raw log files.
  rules  a fixed investigation written in plain Python: read the incident,
         see which service failed first, follow which service the errors
         point at, check the process monitor and the telemetry. No AI, no
         cost, and the same answer every time.

The AI is reached through the OpenAI-compatible chat API that most providers
offer, so the model can be changed with three settings:

  LLM_API_KEY   the key (no key: the rules engine is used)
  LLM_BASE_URL  default https://api.groq.com/openai/v1 (Groq, free tier)
  LLM_MODEL     default openai/gpt-oss-20b (small, free, supports tools)

Every diagnosis is stored with its tool calls and its cost facts: tokens,
time, and how many characters of raw logs were reduced to how much evidence.
"""

import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

from app.models import Diagnosis
from app.services import monitor, tools
from app.services.incidents import incident_facts, incident_logs
from app.services.root_cause import TARGET_PATTERNS

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-20b"
TOOL_RESULT_CHARS = 2000  # each tool result is cut to this size before the AI sees it
CASE_FILE_CHARS = 4500  # the facts gathered before the AI starts
MAX_ANSWER_TOKENS = 1024
# Free tiers limit tokens per minute. When the provider says "wait", BugSense
# waits (at most this many seconds in total for one diagnosis) and tries again.
MAX_RATE_LIMIT_WAIT = 120

# The case file already holds what get_incident, get_error_timeline and
# list_incidents would return, so the AI is offered only the follow-up tools.
# Every tool definition is sent with every request, so fewer tools = fewer tokens.
FOLLOW_UP_TOOLS = ("search_logs", "get_service_status", "get_service_metrics",
                   "get_metric_series", "search_traces", "get_trace")
TELEMETRY_TOOLS = ("get_service_metrics", "get_metric_series", "search_traces", "get_trace")

REQUEST_TIMEOUT = 60

SYSTEM_PROMPT = """You are BugSense's incident investigator, helping a developer find the probable root cause of a software incident.

How to work:
- You receive a case file: the incident, its first error logs, the order in which services started failing, (if monitored) the process status and monitor events, and (if available) OpenTelemetry error rate and latency per service.
- "Stopped for restart" and "Started" events are planned restarts, not crashes. High p95 latency with timeouts in callers means a slow service.
- Call more tools only when the case file is not enough, and at most a few. For example: search_logs for a service that the errors point at, get_service_metrics or search_traces and get_trace for OpenTelemetry data.
- If errors in one service point at another (connection refused, timeout, upstream error), the other service is the likely origin.
- The case file includes a root cause ranking (origin vs affected services, with reasons). Use it as evidence, but check it against the logs.
- The root cause is where the problem BEGAN, not where it was noticed.
- Use only facts returned by the tools. Never invent log lines, numbers or services.
- Be honest about uncertainty: this is a probable cause, not a certainty.
- Suggested fixes are suggestions for the developer. You never run anything.

When you have enough evidence, reply with ONLY a JSON object, no other text:
{"probable_cause": "1-2 sentences", "root_service": "service name or null", "confidence": "low|medium|high", "evidence": ["2-6 short facts, each naming the tool it came from"], "suggested_fixes": ["1-4 short steps"], "limitations": "one sentence on what could make this wrong"}"""


class DiagnosisError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class ToolCallRejected(Exception):
    """The provider refused the model's tool call (for example a value that is
    not allowed). The model is told why and gets another try."""


class LLMError(Exception):
    """The AI model could not be used (no key, network, rate limit, bad reply)."""


def llm_settings():
    return {
        "api_key": os.getenv("LLM_API_KEY", "").strip(),
        "base_url": os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "model": os.getenv("LLM_MODEL", DEFAULT_MODEL),
    }


def config():
    """What the frontend may know about the AI setup (never the key)."""
    settings = llm_settings()
    return {
        "llm_available": bool(settings["api_key"]),
        "model": settings["model"],
        "provider": re.sub(r"^https?://", "", settings["base_url"]).split("/")[0],
        "tools": len(tools.TOOLS),
    }


def compact(value, limit=TOOL_RESULT_CHARS):
    """JSON text of a tool result, cut to `limit` characters."""
    text = json.dumps(value, default=str, separators=(",", ":"))
    return text if len(text) <= limit else text[: limit - 20] + '..."(cut)"}'


# ---------- The AI engine ----------


def retry_after(response):
    """Seconds the provider asks us to wait ("retry-after" header), or 10."""
    try:
        return min(float(response.headers.get("retry-after", 10)), 60)
    except ValueError:
        return 10


def chat(settings, messages, tool_names, waited=None):
    """One request to the AI. tool_names: the tools the model may call (empty:
    none, it must answer). waited: a one-item list that adds up the seconds
    spent waiting for the rate limit during this diagnosis."""
    waited = waited if waited is not None else [0]
    body = {"model": settings["model"], "messages": messages, "temperature": 0.1,
            "max_tokens": MAX_ANSWER_TOKENS}
    if tool_names:
        body["tools"] = [
            {"type": "function", "function": definition} for definition in tools.definitions(tool_names)
        ]
        body["tool_choice"] = "auto"
    while True:
        try:
            response = httpx.post(
                f"{settings['base_url']}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {settings['api_key']}"},
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.HTTPError as problem:
            raise LLMError(f"could not reach the AI provider ({problem.__class__.__name__})") from problem
        if response.status_code != 429:
            break
        pause = retry_after(response)
        if waited[0] + pause > MAX_RATE_LIMIT_WAIT:
            raise LLMError("the AI provider's free rate limit was reached, try again in a minute")
        time.sleep(pause + 0.5)
        waited[0] += pause + 0.5
    if response.status_code >= 400:
        try:
            detail = response.json().get("error", {}).get("message", "")
        except ValueError:
            detail = response.text[:200]
        if response.status_code == 400 and "tool call validation failed" in detail.lower():
            raise ToolCallRejected(detail[:400])
        raise LLMError(f"the AI provider answered {response.status_code}: {detail[:200]}")
    return response.json()


def parse_answer(text):
    """The JSON object in the model's final reply."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("the AI did not reply with a JSON answer")
    try:
        answer = json.loads(text[start : end + 1])
    except json.JSONDecodeError as problem:
        raise LLMError("the AI's answer was not valid JSON") from problem
    if not isinstance(answer, dict) or not answer.get("probable_cause"):
        raise LLMError("the AI's answer has no probable_cause")
    confidence = str(answer.get("confidence", "low")).lower()
    return {
        "probable_cause": str(answer["probable_cause"])[:2000],
        "root_service": (str(answer["root_service"])[:100] if answer.get("root_service") else None),
        "confidence": confidence if confidence in ("low", "medium", "high") else "low",
        "evidence": [str(item)[:400] for item in answer.get("evidence", [])][:8],
        "suggested_fixes": [str(item)[:400] for item in answer.get("suggested_fixes", [])][:6],
        "limitations": str(answer.get("limitations") or "")[:600] or None,
    }


def slim(log):
    """A log with only the fields that help the AI, to save tokens."""
    keep = ("time", "severity", "service", "error_type", "message", "exception")
    return {key: log[key] for key in keep if log.get(key)}


def event_window(facts):
    """Monitor events from one minute before the incident started: older events
    belong to earlier problems and would mislead the investigation."""
    if not facts.get("first_seen"):
        return {}
    return {"since": (facts["first_seen"] - timedelta(minutes=1)).isoformat()}


def telemetry_window(incident, facts):
    """Parameters for the telemetry tools: the incident's time, plus a few
    minutes before it to compare with."""
    window = {"project_id": incident.project_id, "window_minutes": 15}
    if facts.get("first_seen") and facts.get("last_seen"):
        duration = int((facts["last_seen"] - facts["first_seen"]).total_seconds() // 60)
        window["window_minutes"] = max(5, min(43200, duration + 6))
        window["until"] = (facts["last_seen"] + timedelta(minutes=1)).isoformat()
    return window


def case_file(db, incident, facts, steps):
    """The facts every investigation needs, gathered before the AI starts, so
    the AI makes fewer tool calls and the conversation stays small."""
    case = {}
    detail = _call(db, steps, "get_incident", incident_id=incident.id, log_limit=8, errors_only=True)
    if detail:
        case["incident"] = {key: detail[key] for key in ("severity_reasons", "services", "signatures", "logs_matching")}
        case["first_error_logs"] = [slim(log) for log in detail["logs"]]
    timeline = _call(db, steps, "get_error_timeline", incident_id=incident.id, bucket_seconds=30)
    if timeline:
        case["services_in_order_of_first_error"] = [
            {key: item[key] for key in ("service", "seconds_after_first", "error")} for item in timeline["first_errors"]
        ]
    if incident.project_id == monitor.project_id_if_known():
        status = _call(db, steps, "get_service_status", event_limit=8, **event_window(facts))
        if status:
            case["process_status"] = [
                {key: item[key] for key in ("name", "status", "healthy", "restart_count", "exit_code")}
                for item in status["services"]
            ]
            case["monitor_events"] = [
                f"{event['service']}: {event['message']}" for event in status["events"]
            ]
    ranking = _call(db, steps, "rank_root_causes", incident_id=incident.id, top=4)
    if ranking and ranking["ranking"]:
        case["root_cause_ranking"] = {
            "method": ranking["method"],
            "confidence": ranking["confidence"],
            "services": [
                {key: item[key] for key in ("service", "score", "role", "reasons")} for item in ranking["ranking"]
            ],
            "failure_spread": [f"{edge['from']} -> {edge['to']} ({edge['count']}x)" for edge in ranking["propagation"][:4]],
        }
    metrics = _call(db, steps, "get_service_metrics", **telemetry_window(incident, facts))
    if metrics and metrics["services"]:
        case["telemetry_per_service"] = [
            {
                "service": item["service"],
                "requests": item["requests"],
                "error_rate": item["error_rate"],
                "latency_p95_ms": item["latency_ms"]["p95"],
                "latency_p50_ms": item["latency_ms"]["p50"],
            }
            for item in metrics["services"]
        ]
    for step in steps:
        step["prefetched"] = True
    return case


def investigate_with_llm(db, incident, facts, max_steps):
    settings = llm_settings()
    if not settings["api_key"]:
        raise LLMError("no AI key is set (LLM_API_KEY in backend/.env)")

    steps, usage, waited = [], {"in": 0, "out": 0}, [0]
    case = case_file(db, incident, facts, steps)
    window = telemetry_window(incident, facts)
    task = (
        f"Investigate incident #{incident.id} in project #{incident.project_id}: \"{incident.title}\", "
        f"severity {incident.severity}, from {facts.get('first_seen')} to {facts.get('last_seen')}. "
        f"For telemetry tools, use {json.dumps(window)}. Find the probable root cause.\n\nCase file:\n"
        + compact(case, CASE_FILE_CHARS)
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": task}]
    evidence_chars = len(task)

    # Only the tools that can help with this incident: process status only for
    # the monitored demo shop, telemetry tools only when telemetry exists
    offered = [
        name for name in FOLLOW_UP_TOOLS
        if (name != "get_service_status" or "process_status" in case)
        and (name not in TELEMETRY_TOOLS or "telemetry_per_service" in case)
    ]
    rejections = 0
    for step in range(max_steps + 1):
        allow_tools = step < max_steps
        if not allow_tools:
            messages.append({"role": "user", "content": "No more tool calls. Give your final JSON answer now."})
        try:
            reply = chat(settings, messages, offered if allow_tools else [], waited)
        except ToolCallRejected as problem:
            rejections += 1
            if rejections > 2:
                raise LLMError("the AI kept making tool calls the provider refused") from problem
            steps.append({"tool": "(refused by provider)", "parameters": None, "ok": False, "error": str(problem)})
            messages.append({"role": "user", "content": f"Your last tool call was refused: {problem} "
                             "Use only the tools and parameter values in their definitions."})
            continue
        usage["in"] += reply.get("usage", {}).get("prompt_tokens", 0)
        usage["out"] += reply.get("usage", {}).get("completion_tokens", 0)
        message = reply["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            answer = parse_answer(message.get("content") or "")
            return answer, steps, usage, evidence_chars, settings["model"]

        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
        for call in calls:
            name = call["function"]["name"]
            try:
                arguments = json.loads(call["function"].get("arguments") or "{}")
                output = tools.run_tool(db, name, arguments)
                content = compact(output["result"])
                steps.append({"tool": name, "parameters": output["parameters"], "ok": True,
                              "duration_ms": output["duration_ms"], "result_chars": len(content)})
            except (tools.ToolError, json.JSONDecodeError) as problem:
                # The model sees the error and can correct its parameters
                content = json.dumps({"error": str(problem)})
                steps.append({"tool": name, "parameters": call["function"].get("arguments"), "ok": False,
                              "error": str(problem), "result_chars": len(content)})
            evidence_chars += len(content)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})

    raise LLMError("the AI did not finish within the step limit")


# ---------- The rule-based engine ----------


def _call(db, steps, name, **arguments):
    """Runs one tool for the rules engine and records it like an AI tool call."""
    try:
        output = tools.run_tool(db, name, arguments)
    except tools.ToolError as problem:
        steps.append({"tool": name, "parameters": arguments, "ok": False, "error": str(problem)})
        return None
    content = compact(output["result"])
    steps.append({"tool": name, "parameters": output["parameters"], "ok": True,
                  "duration_ms": output["duration_ms"], "result_chars": len(content)})
    return output["result"]


def _short_time(text):
    return text[11:19] if text and len(text) >= 19 else text


def investigate_with_rules(db, incident, facts):
    steps = []
    project_id = incident.project_id
    detail = _call(db, steps, "get_incident", incident_id=incident.id, log_limit=10)
    timeline = _call(db, steps, "get_error_timeline", incident_id=incident.id, bucket_seconds=30)
    problems = _call(db, steps, "search_logs", incident_id=incident.id, min_severity="WARNING", limit=100)
    logs = problems["logs"] if problems else []
    first_errors = timeline["first_errors"] if timeline else []
    ranked = _call(db, steps, "rank_root_causes", incident_id=incident.id, top=4)
    top_ranked = ranked["ranking"][0] if ranked and ranked["ranking"] else None

    monitored = project_id == monitor.project_id_if_known()
    status = _call(db, steps, "get_service_status", event_limit=20, **event_window(facts)) if monitored else None
    process = {service["name"]: service for service in (status or {}).get("services", [])}

    window = telemetry_window(incident, facts)
    metrics = _call(db, steps, "get_service_metrics", **window)
    red = {service["service"]: service for service in (metrics or {}).get("services", [])}
    failed_trace = None
    if red:
        traces = _call(db, steps, "search_traces", status="ERROR", limit=3, **window)
        if traces and traces["traces"]:
            failed_trace = _call(db, steps, "get_trace", trace_id=traces["traces"][0]["trace_id"])

    evidence = []
    services = {log["service"] for log in logs if log["service"]} | set(process) | set(red)
    # A service that is down writes no logs, but the errors of others name it:
    # "connection to shop-db failed", "shop-api unreachable"
    for log in logs:
        if log["severity"] in ("ERROR", "CRITICAL"):
            for pattern in TARGET_PATTERNS:
                services.update(pattern.findall(log["message"] or ""))
    services = sorted(services)
    if first_errors:
        first = first_errors[0]
        evidence.append(
            f"get_error_timeline: {first['service']} failed first at {_short_time(first['time'])} ({first['error']})"
        )

    def logs_with(*words, levels=("ERROR", "CRITICAL")):
        return [
            log for log in logs
            if log["severity"] in levels and any(word.lower() in (log["message"] or "").lower() for word in words)
        ]

    # Which service do the errors point at? "connection to shop-db failed" in
    # shop-api means shop-api depends on shop-db.
    mentions = Counter()
    example = {}
    for log in logs:
        if log["severity"] not in ("ERROR", "CRITICAL") or not log["service"]:
            continue
        for target in services:
            if target != log["service"] and target in (log["message"] or ""):
                mentions[(log["service"], target)] += 1
                example.setdefault((log["service"], target), log["message"])

    def chain_end(start):
        """Follows 'A's errors mention B' links to the service at the end."""
        current, seen = start, {start}
        while True:
            targets = [(count, target) for (source, target), count in mentions.items() if source == current]
            if not targets:
                return current
            _, target = max(targets)
            if target in seen:
                return current
            seen.add(target)
            current = target

    fixes, limitations = [], "Based on logs, process events and telemetry in the incident window only."
    cause, root, confidence = None, None, "low"

    config = logs_with("ConfigError", "invalid configuration")
    crash_events = logs_with("Crash loop", "Exited unexpectedly", "Gave up restarting")
    exceptions = [log for log in logs if log["has_stack_trace"] or "Unhandled exception" in (log["message"] or "")]

    if config:
        root = config[0]["service"]
        cause = f"{root} refuses to start because of an invalid configuration: {config[0]['message']}"
        confidence = "high" if crash_events else "medium"
        evidence.append(f"search_logs: {len(config)} configuration error(s) in {root}, e.g. \"{config[0]['message'][:120]}\"")
        if crash_events:
            evidence.append(f"search_logs: the monitor recorded {len(crash_events)} exit/crash-loop event(s) for {root}")
        fixes = [f"Correct the setting named in the error and restart {root}",
                 "Validate configuration before deploying, so a bad value is caught early"]
    elif crash_events and exceptions:
        crashing = Counter(log["service"] for log in crash_events).most_common(1)[0][0]
        exception_logs = [log for log in exceptions if log["service"] == crashing] or exceptions
        # A stack trace ends with the real exception, so it is the best description
        traced = [log for log in exception_logs if log["exception"]]
        failure = traced[-1]["exception"] if traced else exception_logs[-1]["message"]
        root = crashing
        cause = f"{root} crashes during start-up ({failure}), so it is restarted again and again (crash loop)."
        confidence = "high"
        evidence.append(f"search_logs: {len(crash_events)} monitor event(s) show {root} exiting and restarting")
        evidence.append(f"search_logs: the crash message is \"{failure[:140]}\"")
        if root in process:
            evidence.append(
                f"get_service_status: {root} is '{process[root]['status']}' after {process[root]['restart_count']} "
                f"restart(s), last exit code {process[root]['exit_code']}"
            )
        fixes = [f"Read the stack trace of {root} and fix the failing start-up code",
                 "Add a check for the missing value, so the service fails with a clear message"]
    elif mentions and first_errors:
        caller = first_errors[0]["service"]
        root = chain_end(caller)
        if root == caller:
            (source, root), _ = mentions.most_common(1)[0]
            caller = source
        link_count = sum(count for (source, target), count in mentions.items() if target == root)
        evidence.append(
            f"search_logs: {link_count} error(s) in {caller} point at {root}, e.g. \"{example[(caller, root)][:130]}\""
            if (caller, root) in example
            else f"search_logs: {link_count} error(s) point at {root}"
        )
        slow = red.get(root, {}).get("latency_ms", {}).get("p95")
        timeouts = logs_with("timeout", "did not answer", "timed out")
        if root in process and process[root]["status"] != "running":
            cause = (f"{root} is not running ({process[root]['status']}). Services that depend on it cannot reach it, "
                     f"so their requests fail.")
            confidence = "high"
            evidence.append(f"get_service_status: {root} is '{process[root]['status']}'")
            fixes = [f"Start {root} again and check why it stopped",
                     f"Make callers of {root} retry with back-off and show a clear error"]
        elif timeouts and (slow is None or slow >= 1000):
            cause = (f"{root} is responding too slowly" + (f" (p95 latency {slow:.0f} ms)" if slow else "")
                     + f", so the services calling it time out.")
            confidence = "high" if slow else "medium"
            evidence.append(f"search_logs: {len(timeouts)} timeout error(s) while calling {root}")
            if slow:
                evidence.append(f"get_service_metrics: {root} p95 latency is {slow:.0f} ms in the incident window")
            fixes = [f"Find what makes {root} slow (a slow query, a lock, too little capacity)",
                     f"Set a timeout and a fallback in the callers of {root}"]
        else:
            cause = f"{root} is failing or unreachable, and the errors in the services that depend on it follow from that."
            confidence = "medium"
            fixes = [f"Check {root}: is it running, healthy and reachable at the address the callers use?"]
        if root in process and process[root].get("healthy") is False:
            evidence.append(f"get_service_status: {root} fails its health check")
    elif top_ranked and ranked["method"] == "requests" and ranked["confidence"] != "low":
        # Request IDs show who failed first in each request: stronger than one earliest error
        root = top_ranked["service"]
        affected = [item["service"] for item in ranked["ranking"][1:] if item["role"] == "affected"]
        cause = f"The failures start in {root}" + (
            f"; {', '.join(affected)} fail after it in the same requests." if affected else "."
        )
        confidence = "medium"
        fixes = [f"Start with the first errors of {root} in the failed requests"]
    elif first_errors:
        first = first_errors[0]
        root = first["service"]
        others = [item["service"] for item in first_errors[1:]]
        cause = f"The earliest failure is \"{first['error']}\" in {root}" + (
            f"; the later errors in {', '.join(others)} probably follow from it." if others else "."
        )
        confidence = "medium" if not others else "low"
        fixes = [f"Start with the first error in {root}: \"{first['message'][:120]}\""]
        limitations = ("No dependency between services could be seen in the logs, so the earliest error is "
                       "only a starting point.")
    else:
        top = detail["signatures"][0]["label"] if detail and detail["signatures"] else "warnings"
        root = incident.affected_service
        cause = f"Repeated {top} in {root or 'the system'}, without errors. Probably a symptom to watch, not an outage."
        fixes = ["Check whether these warnings are expected"]

    if top_ranked and top_ranked["score"] > 0:
        evidence.append(
            f"rank_root_causes: {top_ranked['service']} is the probable origin "
            f"(score {top_ranked['score']}: {'; '.join(top_ranked['reasons'][:2])})"
        )
        if ranked["propagation"]:
            chain = ranked["propagation"][0]
            evidence.append(f"rank_root_causes: the failure spread {chain['from']} -> {chain['to']} ({chain['count']}x)")
    alert = logs_with("Telemetry:", levels=("ERROR", "WARNING"))
    if alert:
        evidence.append(f"search_logs: telemetry alert in {alert[0]['service']}: \"{alert[0]['message'][11:150]}\"")
    if failed_trace:
        failed = [span for span in failed_trace["spans"] if span["status"] == "ERROR"]
        deepest = max(failed, key=lambda span: span["depth"]) if failed else None
        if deepest:
            evidence.append(
                f"get_trace: in a failed request the deepest failing step is {deepest['service']} "
                f"\"{deepest['name']}\" ({deepest['status_message'] or 'error'})"
            )

    answer = {
        "probable_cause": cause,
        "root_service": root,
        "confidence": confidence,
        "evidence": evidence[:8],
        "suggested_fixes": fixes,
        "limitations": limitations,
    }
    evidence_chars = sum(step.get("result_chars", 0) for step in steps)
    return answer, steps, evidence_chars


# ---------- Running a diagnosis ----------


def as_datetime(value):
    """SQLite gives some times back as text; both databases end up as aware datetimes."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.astimezone()
    return value


def diagnose(db, incident, engine="auto", max_steps=4):
    facts = incident_facts(db, [incident.id]).get(incident.id)
    if not facts:
        raise DiagnosisError("This incident has no logs", 409)
    facts["first_seen"], facts["last_seen"] = as_datetime(facts["first_seen"]), as_datetime(facts["last_seen"])
    raw_chars = sum(len(log.raw) for log in incident_logs(db, incident.id))
    started = time.perf_counter()
    note, model, usage = None, None, {"in": 0, "out": 0}

    if engine == "llm" and not llm_settings()["api_key"]:
        raise DiagnosisError("No AI key is set. Add LLM_API_KEY to backend/.env, or use engine=rules.", 400)

    answer = None
    if engine in ("auto", "llm"):
        try:
            answer, steps, usage, evidence_chars, model = investigate_with_llm(db, incident, facts, max_steps)
            used = "llm"
        except LLMError as problem:
            if engine == "llm":
                raise DiagnosisError(f"AI diagnosis failed: {problem}", 503) from problem
            note = f"AI not used: {problem}. The rule-based investigator was used instead."
    if answer is None:
        answer, steps, evidence_chars = investigate_with_rules(db, incident, facts)
        used = "rules"

    record = Diagnosis(
        project_id=incident.project_id,
        incident_id=incident.id,
        anchor_log_id=facts["first_log_id"],
        incident_title=incident.title,
        engine=used,
        model=model,
        steps=steps,
        tokens_in=usage["in"],
        tokens_out=usage["out"],
        duration_ms=round((time.perf_counter() - started) * 1000),
        raw_chars=raw_chars,
        evidence_chars=evidence_chars,
        note=note,
        **answer,
    )
    db.add(record)
    db.commit()
    return to_dict(record)


def to_dict(record):
    return {
        "id": record.id,
        "incident_id": record.incident_id,
        "incident_title": record.incident_title,
        "engine": record.engine,
        "model": record.model,
        "probable_cause": record.probable_cause,
        "root_service": record.root_service,
        "confidence": record.confidence,
        "evidence": record.evidence,
        "suggested_fixes": record.suggested_fixes,
        "limitations": record.limitations,
        "steps": record.steps,
        "note": record.note,
        "cost": {
            "tokens_in": record.tokens_in,
            "tokens_out": record.tokens_out,
            "duration_ms": record.duration_ms,
            "raw_chars": record.raw_chars,
            "evidence_chars": record.evidence_chars,
            # How many times smaller the evidence is than the raw logs
            "reduction": round(record.raw_chars / record.evidence_chars, 1) if record.evidence_chars else None,
        },
        "created_at": record.created_at,
    }


def history(db, incident, limit=10):
    facts = incident_facts(db, [incident.id]).get(incident.id)
    if not facts:
        return []
    records = db.scalars(
        select(Diagnosis)
        .where(Diagnosis.anchor_log_id == facts["first_log_id"])
        .order_by(Diagnosis.id.desc())
        .limit(limit)
    ).all()
    return [to_dict(record) for record in records]

