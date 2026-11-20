"""Diagnosis (Phase 7): the rule-based investigator and the AI agent loop.

The AI is never called for real in tests: a fake model replies instead, so the
loop (tool calls, errors, the final answer) is tested without a key or network.
"""

import json

import pytest
from sqlalchemy import update

from app.models import Diagnosis
from app.services import diagnosis

DATABASE_DOWN = """2026-11-17 10:00:00 INFO [shop-api] GET /checkout 200 in 12 ms request_id=req-0
2026-11-17 10:00:01 ERROR [shop-api] OperationalError: connection to shop-db at 127.0.0.1:9102 failed: Connection refused request_id=req-1
2026-11-17 10:00:01 ERROR [shop-web] Checkout page failed: upstream returned 503 request_id=req-1
2026-11-17 10:00:02 ERROR [shop-api] OperationalError: connection to shop-db at 127.0.0.1:9102 failed: Connection refused request_id=req-2
2026-11-17 10:00:02 ERROR [shop-web] Checkout page failed: upstream returned 503 request_id=req-2
2026-11-17 10:00:03 ERROR [shop-api] OperationalError: connection to shop-db at 127.0.0.1:9102 failed: Connection refused request_id=req-3
"""

BAD_CONFIG = """2026-11-17 10:00:00 ERROR [shop-api] ConfigError: invalid SHOP_DB_URL: expected "http://", got "postgres//db"
2026-11-17 10:00:00 CRITICAL [shop-api] Startup failed: invalid configuration
2026-11-17 10:00:01 ERROR [shop-api] Process monitor: Exited unexpectedly with code 1
2026-11-17 10:00:02 ERROR [shop-web] ConnectionError: shop-api unreachable request_id=req-1
"""

CRASH_LOOP = """2026-11-17 10:00:00 CRITICAL [shop-api] Unhandled exception, shutting down
Traceback (most recent call last):
  File "shop_api.py", line 120, in <module>
RuntimeError: payment module failed to initialise: missing key 'currency'
2026-11-17 10:00:01 ERROR [shop-api] Process monitor: Exited unexpectedly with code 1
2026-11-17 10:00:05 CRITICAL [shop-api] Process monitor: Crash loop: 3 crashes in the last 60 s
2026-11-17 10:00:06 ERROR [shop-web] ConnectionError: shop-api unreachable request_id=req-1
"""

ONE_SERVICE = """2026-11-17 10:00:00 ERROR [worker] KeyError: 'user_id'
2026-11-17 10:00:01 ERROR [worker] KeyError: 'user_id'
2026-11-17 10:00:02 ERROR [worker] KeyError: 'user_id'
"""


def first_incident(client, text):
    client.post("/logs/text", json={"text": text})
    return client.get("/incidents").json()[0]["id"]


def diagnose(client, incident, **params):
    response = client.post(f"/incidents/{incident}/diagnose", params={"engine": "rules", **params})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(autouse=True)
def no_ai_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)


def test_rules_follow_the_errors_to_the_service_they_point_at(client):
    result = diagnose(client, first_incident(client, DATABASE_DOWN))
    assert result["engine"] == "rules"
    assert result["root_service"] == "shop-db"
    assert "shop-db" in result["probable_cause"]
    assert any("shop-api failed first" in item for item in result["evidence"])
    assert [step["tool"] for step in result["steps"]][:3] == ["get_incident", "get_error_timeline", "search_logs"]


def test_rules_recognise_a_configuration_error(client):
    result = diagnose(client, first_incident(client, BAD_CONFIG))
    assert result["root_service"] == "shop-api"
    assert "invalid configuration" in result["probable_cause"]
    assert result["confidence"] == "high"  # the monitor saw it exit as well


def test_rules_name_the_exception_of_a_crash_loop(client):
    result = diagnose(client, first_incident(client, CRASH_LOOP))
    assert result["root_service"] == "shop-api"
    assert "RuntimeError: payment module failed to initialise" in result["probable_cause"]
    assert "crash loop" in result["probable_cause"]


def test_rules_fall_back_to_the_earliest_error(client):
    result = diagnose(client, first_incident(client, ONE_SERVICE))
    assert result["root_service"] == "worker"
    assert "KeyError" in result["probable_cause"]


def test_cost_facts_and_history_are_stored(client):
    incident = first_incident(client, DATABASE_DOWN)
    first = diagnose(client, incident)
    # The raw size is every log of the incident (the five problem lines, not the INFO line)
    assert first["cost"]["raw_chars"] == sum(len(line) for line in DATABASE_DOWN.splitlines()[1:])
    assert first["cost"]["evidence_chars"] > 0 and first["cost"]["tokens_in"] == 0
    diagnose(client, incident)
    history = client.get(f"/incidents/{incident}/diagnoses").json()
    assert len(history) == 2 and history[0]["id"] > history[1]["id"]
    assert len(client.get(f"/incidents/{incident}/diagnoses", params={"limit": 1}).json()) == 1


def test_diagnosis_is_found_through_the_first_log_not_the_incident_id(client, session_factory):
    incident = first_incident(client, DATABASE_DOWN)
    diagnose(client, incident)
    # Detection rebuilds open incidents, which can give them a new id.
    # Pretend that happened: the stored id no longer matches.
    with session_factory() as db:
        db.execute(update(Diagnosis).values(incident_id=9999))
        db.commit()
    client.post("/incidents/detect")
    rebuilt = client.get("/incidents").json()[0]["id"]
    assert len(client.get(f"/incidents/{rebuilt}/diagnoses").json()) == 1


def test_engine_parameters(client):
    incident = first_incident(client, DATABASE_DOWN)
    assert client.post(f"/incidents/{incident}/diagnose", params={"engine": "magic"}).status_code == 422
    assert client.post(f"/incidents/{incident}/diagnose", params={"max_steps": 0}).status_code == 422
    # Asking for the AI without a key is a clear error, not a silent switch
    response = client.post(f"/incidents/{incident}/diagnose", params={"engine": "llm"})
    assert response.status_code == 400 and "LLM_API_KEY" in response.json()["detail"]
    # auto without a key uses the rules and says so
    auto = client.post(f"/incidents/{incident}/diagnose").json()
    assert auto["engine"] == "rules" and "no AI key" in auto["note"]
    assert client.get("/tools/config").json()["llm_available"] is False


def tool_call(call_id, name, arguments):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def reply(message, tokens_in=100, tokens_out=20):
    return {"choices": [{"message": message}], "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out}}


def test_ai_agent_loop_with_a_fake_model(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    incident = first_incident(client, DATABASE_DOWN)
    answer = {
        "probable_cause": "shop-db is down, so shop-api cannot connect.",
        "root_service": "shop-db",
        "confidence": "high",
        "evidence": ["get_error_timeline: shop-api failed first"],
        "suggested_fixes": ["Start shop-db"],
        "limitations": "Only logs were available.",
    }
    script = [
        # 1. a call with a bad parameter: the model is told why and tries again
        reply({"content": "", "tool_calls": [tool_call("1", "search_logs", {"incident_id": incident, "limit": 999})]}),
        reply({"content": "", "tool_calls": [tool_call("2", "search_logs", {"incident_id": incident, "service": "shop-api"})]}),
        reply({"content": "Here is my answer:\n" + json.dumps(answer)}),
    ]
    seen = []

    def fake_chat(settings, messages, tool_names, waited=None):
        seen.append([dict(message) for message in messages])
        return script.pop(0)

    monkeypatch.setattr(diagnosis, "chat", fake_chat)
    result = client.post(f"/incidents/{incident}/diagnose", params={"engine": "llm"}).json()

    assert result["engine"] == "llm" and result["root_service"] == "shop-db"
    # The case file is gathered first, then the model's own calls follow
    assert [step["tool"] for step in result["steps"] if step.get("prefetched")] == [
        "get_incident", "get_error_timeline", "get_service_metrics"
    ]
    own = [step for step in result["steps"] if not step.get("prefetched")]
    assert [(step["tool"], step["ok"]) for step in own] == [("search_logs", False), ("search_logs", True)]
    assert "limit" in own[0]["error"]
    assert "Case file" in seen[0][1]["content"] and "first_error_logs" in seen[0][1]["content"]
    assert result["cost"]["tokens_in"] == 300 and result["cost"]["tokens_out"] == 60
    # The model saw the tool error, then the timeline result
    tool_messages = [message for message in seen[-1] if message["role"] == "tool"]
    assert "error" in tool_messages[0]["content"] and "total_matching" in tool_messages[1]["content"]


def test_ai_step_limit_forces_a_final_answer(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    incident = first_incident(client, DATABASE_DOWN)
    final = {"probable_cause": "Unclear.", "confidence": "low"}
    calls = []

    def fake_chat(settings, messages, tool_names, waited=None):
        calls.append(bool(tool_names))
        if tool_names:
            return reply({"content": "", "tool_calls": [tool_call(str(len(calls)), "list_incidents", {})]})
        return reply({"content": json.dumps(final)})

    monkeypatch.setattr(diagnosis, "chat", fake_chat)
    result = client.post(f"/incidents/{incident}/diagnose", params={"engine": "llm", "max_steps": 2}).json()
    assert calls == [True, True, False]  # two tool rounds, then tools are taken away
    assert result["confidence"] == "low"
    assert len([step for step in result["steps"] if not step.get("prefetched")]) == 2


def test_ai_failure_falls_back_to_rules_in_auto_mode(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    def broken_chat(settings, messages, tool_names, waited=None):
        raise diagnosis.LLMError("the AI provider's free rate limit was reached")

    monkeypatch.setattr(diagnosis, "chat", broken_chat)
    incident = first_incident(client, DATABASE_DOWN)
    result = client.post(f"/incidents/{incident}/diagnose").json()
    assert result["engine"] == "rules" and "rate limit" in result["note"]
    strict = client.post(f"/incidents/{incident}/diagnose", params={"engine": "llm"})
    assert strict.status_code == 503


def test_answers_that_are_not_json_are_rejected():
    with pytest.raises(diagnosis.LLMError):
        diagnosis.parse_answer("I think the database is down.")
    parsed = diagnosis.parse_answer('{"probable_cause": "x", "confidence": "VERY HIGH"}')
    assert parsed["confidence"] == "low"  # unknown values become low, never invented


def test_rate_limit_waits_then_retries(monkeypatch):
    replies = [
        type("R", (), {"status_code": 429, "headers": {"retry-after": "2"}})(),
        type("R", (), {"status_code": 200, "headers": {}, "json": lambda self: {"ok": True}})(),
    ]
    monkeypatch.setattr(diagnosis.httpx, "post", lambda *args, **kwargs: replies.pop(0))
    slept = []
    monkeypatch.setattr(diagnosis.time, "sleep", slept.append)
    waited = [0]
    settings = {"model": "m", "base_url": "http://ai", "api_key": "k"}
    assert diagnosis.chat(settings, [], [], waited) == {"ok": True}
    assert slept == [2.5] and waited == [2.5]


def test_rate_limit_gives_up_after_the_wait_budget(monkeypatch):
    always_busy = type("R", (), {"status_code": 429, "headers": {"retry-after": "30"}})()
    monkeypatch.setattr(diagnosis.httpx, "post", lambda *args, **kwargs: always_busy)
    monkeypatch.setattr(diagnosis.time, "sleep", lambda seconds: None)
    with pytest.raises(diagnosis.LLMError, match="rate limit"):
        diagnosis.chat({"model": "m", "base_url": "http://ai", "api_key": "k"}, [], [], [0])


def test_refused_tool_call_is_explained_to_the_model(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    incident = first_incident(client, DATABASE_DOWN)
    offered, attempts = [], []

    def fake_chat(settings, messages, tool_names, waited=None):
        offered.append(list(tool_names))
        attempts.append(messages[-1]["content"])
        if len(attempts) == 1:
            raise diagnosis.ToolCallRejected("tool call validation failed: /service must be one of shop-db")
        return reply({"content": json.dumps({"probable_cause": "x", "confidence": "low"})})

    monkeypatch.setattr(diagnosis, "chat", fake_chat)
    result = client.post(f"/incidents/{incident}/diagnose", params={"engine": "llm"}).json()
    assert result["engine"] == "llm"
    assert "was refused" in attempts[1]
    # No monitor and no telemetry for this project: only log search is offered
    assert offered[0] == ["search_logs"]
