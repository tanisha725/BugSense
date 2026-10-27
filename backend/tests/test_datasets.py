from sqlalchemy import func, select

from app.models import Log
from app.services import replay
from app.services.datasets import DATASETS, catalog, read_entries
from app.services.projects import find_or_create_project


def test_catalog_lists_every_dataset_with_2000_lines():
    datasets = catalog()

    assert [item["key"] for item in datasets] == list(DATASETS)
    assert all(item["lines"] == 2000 for item in datasets)


def test_import_dataset_creates_a_project_with_parsed_logs(client):
    result = client.post("/datasets/apache/import").json()

    assert result["created"] == 2000
    stats = client.get("/logs/stats", params={"project_id": result["project_id"]}).json()
    assert stats["total"] == 2000
    assert stats["errors"] == 595
    assert stats["by_severity"] == {"ERROR": 595, "INFO": 1405}


def test_importing_twice_replaces_the_old_copy(client):
    client.post("/datasets/hdfs/import")
    project_id = client.post("/datasets/hdfs/import").json()["project_id"]

    projects = client.get("/projects").json()
    assert [project["log_count"] for project in projects if project["id"] == project_id] == [2000]


def test_unknown_dataset_is_rejected(client):
    assert client.post("/datasets/windows/import").status_code == 404
    assert client.post("/datasets/apache/stream", params={"speed": 7}).status_code == 400


def test_project_filter_and_timeline(client):
    apache = client.post("/datasets/apache/import").json()["project_id"]
    client.post("/logs/text", json={"text": "ERROR [shop] TimeoutError: slow"})

    logs = client.get("/logs", params={"project_id": apache, "limit": 500}).json()
    assert {log["project_id"] for log in logs} == {apache}

    slots = client.get("/logs/timeline", params={"project_id": apache, "slots": 20}).json()
    assert len(slots) == 20
    assert sum(slot["total"] for slot in slots) == 2000
    assert sum(slot["errors"] for slot in slots) == 595


def test_replay_stores_lines_with_the_current_time(session_factory, monkeypatch):
    monkeypatch.setattr(replay, "session_factory", session_factory)
    with session_factory() as db:
        project_id = find_or_create_project(db, "Live test").id
        db.commit()

    entries = read_entries("openssh")[:7]
    replay.run(entries, DATASETS["openssh"], project_id, speed=3, pause_seconds=0)

    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Log)) == 7
        services = set(db.scalars(select(Log.service)))
    assert services == {"sshd"}
    assert replay.status()["sent"] == 7


def test_dataset_viewer_shows_raw_lines_with_parsed_fields(client):
    data = client.get("/datasets/apache").json()

    assert data["lines"] == 2000
    assert data["format"] == "Apache" and data["recognised"] == 2000
    assert data["by_severity"] == {"INFO": 1405, "ERROR": 595}
    assert data["matches"] == 2000 and len(data["rows"]) == 50

    first = data["rows"][0]
    assert first["line"] == 1
    assert first["raw"].startswith("[Sun Dec 04 04:47:44 2005] [notice]")
    assert first["severity"] == "INFO"


def test_dataset_viewer_search_and_pages(client):
    page = client.get("/datasets/openssh", params={"search": "break-in", "offset": 10, "limit": 5}).json()

    assert page["matches"] > 15
    assert len(page["rows"]) == 5
    assert all("break-in" in row["raw"].lower() for row in page["rows"])


def test_dataset_download_gives_the_original_file(client):
    response = client.get("/datasets/hdfs/download")

    assert response.status_code == 200
    assert response.text.startswith("081109 203615 148 INFO")
    assert client.get("/datasets/nope/download").status_code == 404


def test_bugsense_agrees_with_loghubs_csv_on_every_line(client):
    for key in ["apache", "openssh", "hdfs", "zookeeper", "hadoop", "openstack"]:
        verification = client.get(f"/datasets/{key}", params={"limit": 1}).json()["verification"]

        assert verification["csv_rows"] == verification["parsed_lines"] == 2000
        for check in verification["checks"]:
            assert check["matched"] == check["compared"] == 2000, (key, check)


def test_csv_view_shows_loghubs_columns(client):
    page = client.get("/datasets/apache/csv", params={"limit": 3}).json()

    assert page["header"][:4] == ["LineId", "Time", "Level", "Content"]
    assert page["matches"] == 2000
    assert page["rows"][1]["values"][:3] == ["2", "Sun Dec 04 04:47:44 2005", "error"]
    assert page["rows"][1]["agrees"] is True


def test_csv_downloads(client):
    original = client.get("/datasets/hdfs/csv/download")
    parsed = client.get("/datasets/hdfs/parsed.csv")

    assert original.text.startswith("LineId,Date,Time,Pid,Level,Component,Content")
    assert parsed.text.startswith("line,timestamp,severity,service,error_type,request_id,message")
    assert len(parsed.text.strip().splitlines()) == 2001


def test_export_stored_logs_as_csv(client):
    client.post("/logs/text", json={"text": "ERROR [shop] TimeoutError: slow\nINFO [shop] ok"})

    lines = client.get("/logs/export", params={"severity": "ERROR"}).text.strip().splitlines()
    assert lines[0] == "line,timestamp,severity,service,error_type,request_id,message"
    assert len(lines) == 2
    assert ",ERROR,shop,TimeoutError,," in lines[1]
