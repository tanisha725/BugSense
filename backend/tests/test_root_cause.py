"""Root cause ordering (Phase 8): which service the failure started in, and
which services only failed after it."""

# shop-db is down and writes nothing. shop-api fails first in every request and
# names shop-db; shop-web fails after shop-api in the same request.
DATABASE_DOWN = """2026-11-17 10:00:00 INFO [shop-db] Database listening on port 9102
2026-11-17 10:00:00 INFO [shop-api] GET /checkout 200 in 12 ms request_id=req-0
2026-11-17 10:00:01 ERROR [shop-api] OperationalError: connection to shop-db failed request_id=req-1
2026-11-17 10:00:01 ERROR [shop-web] Checkout page failed: upstream returned 503 request_id=req-1
2026-11-17 10:00:02 ERROR [shop-api] OperationalError: connection to shop-db failed request_id=req-2
2026-11-17 10:00:02 ERROR [shop-web] Checkout page failed: upstream returned 503 request_id=req-2
2026-11-17 10:00:03 ERROR [shop-api] OperationalError: connection to shop-db failed request_id=req-3
2026-11-17 10:00:03 ERROR [shop-web] Checkout page failed: upstream returned 503 request_id=req-3
"""

# No request IDs: only the order in time and what the errors name
NO_REQUEST_IDS = """2026-11-17 10:00:00 INFO [cache] started
2026-11-17 10:00:05 ERROR [api] ConnectionError: cache unreachable
2026-11-17 10:00:06 ERROR [api] ConnectionError: cache unreachable
2026-11-17 10:00:07 ERROR [web] page failed with 502
"""


def ranking_for(client, text):
    client.post("/logs/text", json={"text": text})
    incident = client.get("/incidents").json()[0]["id"]
    response = client.get(f"/incidents/{incident}/root-cause")
    assert response.status_code == 200
    return response.json()


def test_the_silent_service_named_by_the_errors_is_the_origin(client):
    result = ranking_for(client, DATABASE_DOWN)
    ranking = {item["service"]: item for item in result["ranking"]}

    assert result["method"] == "requests" and result["requests_analysed"] == 3
    assert result["ranking"][0]["service"] == "shop-db"
    assert ranking["shop-db"]["role"] == "probable origin"
    assert ranking["shop-db"]["origin_requests"] == 3
    assert "named by 3 error(s) in other services" in ranking["shop-db"]["reasons"]
    assert ranking["shop-api"]["role"] == "affected" and ranking["shop-web"]["role"] == "affected"
    assert result["confidence"] == "high"


def test_the_failure_chain_follows_the_requests(client):
    result = ranking_for(client, DATABASE_DOWN)
    chain = [(edge["from"], edge["to"], edge["count"]) for edge in result["propagation"]]
    assert chain == [("shop-db", "shop-api", 3), ("shop-api", "shop-web", 3)]
    steps = result["example"]["steps"]
    assert [step["service"] for step in steps] == ["shop-db", "shop-api", "shop-web"]
    assert "wrote no log" in steps[0]["message"]


def test_without_request_ids_time_and_names_are_used(client):
    result = ranking_for(client, NO_REQUEST_IDS)
    assert result["method"] == "timeline"
    assert result["ranking"][0]["service"] == "cache"
    # The cache is named by two errors and failed first: more than the earliest error alone
    assert result["confidence"] in ("medium", "high")
    assert ("cache", "api") in [(edge["from"], edge["to"]) for edge in result["propagation"]]


def test_failed_traces_point_at_the_deepest_step(client):
    client.post("/logs/text", json={"text": DATABASE_DOWN})
    # Telemetry from the logs: one span per service per request, all flat under the root
    incident = client.get("/incidents").json()[0]["id"]
    result = client.get(f"/incidents/{incident}/root-cause").json()
    assert result["failed_traces"] == 3


def test_points_add_up_with_reasons(client):
    result = ranking_for(client, DATABASE_DOWN)
    top = result["ranking"][0]
    assert set(result["points"]) == {"requests", "named", "traces", "first", "monitor"}
    assert 0 < top["score"] <= sum(result["points"].values())
    assert all(item["reasons"] for item in result["ranking"])


def test_root_cause_tool_and_parameters(client):
    client.post("/logs/text", json={"text": DATABASE_DOWN})
    incident = client.get("/incidents").json()[0]["id"]
    result = client.post("/tools/rank_root_causes", json={"incident_id": incident, "top": 1}).json()["result"]
    assert [item["service"] for item in result["ranking"]] == ["shop-db"]
    assert client.post("/tools/rank_root_causes", json={"incident_id": incident, "top": 0}).status_code == 422
    assert client.post("/tools/rank_root_causes", json={"incident_id": 999}).status_code == 404
    assert client.get("/incidents/999/root-cause").status_code == 404


def test_rules_diagnosis_cites_the_ranking(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    client.post("/logs/text", json={"text": DATABASE_DOWN})
    incident = client.get("/incidents").json()[0]["id"]
    result = client.post(f"/incidents/{incident}/diagnose", params={"engine": "rules"}).json()
    assert result["root_service"] == "shop-db"
    assert any(item.startswith("rank_root_causes: shop-db is the probable origin") for item in result["evidence"])
    assert any("shop-db -> shop-api" in item for item in result["evidence"])


def test_earliest_error_alone_gives_low_confidence(client):
    result = ranking_for(client, """2026-11-17 10:00:00 ERROR [worker] KeyError: 'id'
2026-11-17 10:00:01 ERROR [worker] KeyError: 'id'
2026-11-17 10:00:02 ERROR [mailer] SMTPError: timeout
""")
    assert result["method"] == "timeline" and result["ranking"][0]["service"] == "worker"
    assert result["confidence"] == "low"
