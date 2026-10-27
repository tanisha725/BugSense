"""Real-world log datasets that can be imported into BugSense.

The files in backend/datasets/ are 2,000-line samples from Loghub, a public
collection of logs from real systems made for research (github.com/logpai/loghub).

Each dataset has two files from Loghub:
  <name>_2k.log                 - the raw log lines
  <name>_2k.log_structured.csv  - the same lines split into columns by the researchers

The CSV is used to check BugSense's parser: both should agree on every line.
"""

import csv
import io
from collections import Counter
from functools import cache
from pathlib import Path

from sqlalchemy import delete

from app.models import Incident, Log
from app.services.incident_detector import detect_incidents
from app.services.log_formats import match_known_format
from app.services.log_parser import normalize_severity, parse_log, split_into_entries
from app.services.projects import find_or_create_project

DATASET_FOLDER = Path(__file__).resolve().parents[2] / "datasets"
SOURCE_URL = "https://github.com/logpai/loghub"

DATASETS = {
    "apache": {
        "name": "Apache Web Server",
        "system": "Web server",
        "file": "Apache_2k.log",
        "service": "apache",
        "description": "Error log of an Apache web server: worker start-ups, "
        "notices and mod_jk connector errors.",
    },
    "openssh": {
        "name": "OpenSSH Server",
        "system": "Security",
        "file": "OpenSSH_2k.log",
        "service": "sshd",
        "description": "Logins on a lab SSH server, full of failed passwords, "
        "invalid users and possible break-in attempts.",
    },
    "hdfs": {
        "name": "Hadoop HDFS",
        "system": "Distributed storage",
        "file": "HDFS_2k.log",
        "service": "hdfs",
        "description": "Block operations of a Hadoop file system running on a "
        "cluster of Amazon EC2 machines.",
    },
    "zookeeper": {
        "name": "ZooKeeper Cluster",
        "system": "Coordination service",
        "file": "Zookeeper_2k.log",
        "service": "zookeeper",
        "description": "Leader election and connections between ZooKeeper servers, "
        "with many dropped-connection warnings.",
    },
    "hadoop": {
        "name": "Hadoop MapReduce",
        "system": "Big data processing",
        "file": "Hadoop_2k.log",
        "service": "hadoop",
        "description": "A MapReduce job hit by an injected failure: a machine loses "
        "its network connection and tasks fail and retry.",
    },
    "openstack": {
        "name": "OpenStack Nova",
        "system": "Cloud platform",
        "file": "OpenStack_2k.log",
        "service": "nova",
        "description": "API requests and virtual machine operations in an OpenStack "
        "cloud, with request IDs and HTTP status codes.",
    },
}


def get_dataset(key):
    """Returns the dataset's settings, or None if the key is unknown."""
    return DATASETS.get(key)


@cache
def read_entries(key):
    """Reads and splits a dataset file once, then remembers the result."""
    path = DATASET_FOLDER / DATASETS[key]["file"]
    return tuple(split_into_entries(path.read_text(encoding="utf-8", errors="replace")))


def parse_entry(entry, dataset):
    """Parses one line. Lines without a service name get the dataset's service."""
    fields = parse_log(entry)
    fields["service"] = fields["service"] or dataset["service"]
    return fields


def dataset_path(key):
    return DATASET_FOLDER / DATASETS[key]["file"]


@cache
def parsed_entries(key):
    """Every line of the dataset together with the fields the parser found in it."""
    dataset = DATASETS[key]
    return tuple((entry, parse_entry(entry, dataset)) for entry in read_entries(key))


@cache
def summary(key):
    """Facts about a whole dataset, for the dataset viewer page."""
    rows = parsed_entries(key)
    times = [fields["timestamp"] for _, fields in rows if fields["timestamp"]]
    formats = Counter(
        (match_known_format(entry.split("\n")[0]) or {}).get("format") for entry, _ in rows
    )
    format_name, format_count = formats.most_common(1)[0]
    by_severity = Counter(fields["severity"] or "UNKNOWN" for _, fields in rows)
    services = Counter(fields["service"] for _, fields in rows if fields["service"])
    error_types = Counter(fields["error_type"] for _, fields in rows if fields["error_type"])

    return {
        "file": DATASETS[key]["file"],
        "file_size": dataset_path(key).stat().st_size,
        "source_url": SOURCE_URL,
        "lines": len(rows),
        "first_time": min(times) if times else None,
        "last_time": max(times) if times else None,
        "format": format_name,
        "recognised": format_count,
        "by_severity": dict(by_severity),
        "service_count": len(services),
        "top_services": [{"service": name, "count": count} for name, count in services.most_common(5)],
        "top_errors": [{"error_type": name, "count": count} for name, count in error_types.most_common(5)],
    }


# ---------- Loghub's CSV, and checking BugSense against it ----------


def csv_path(key):
    return DATASET_FOLDER / f"{DATASETS[key]['file']}_structured.csv"


@cache
def read_csv(key):
    """Returns the CSV's column names and its rows (each row is a list of values)."""
    with open(csv_path(key), encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        header = next(reader)
        return tuple(header), tuple(tuple(row) for row in reader)


def row_checks(header, values, fields):
    """Compares one CSV row with what BugSense parsed from the same line.

    Returns {check name: True/False}. A check is skipped if the CSV lacks that column.
    """
    row = dict(zip(header, values))
    checks = {}
    # Loghub's message text must be found in BugSense's message
    checks["message"] = row["Content"].strip() in (fields["message"] or "")
    # The clock time must agree (Loghub writes it as 06:55:46 or 065546)
    moment = fields["timestamp"]
    checks["time"] = bool(moment) and (
        moment.strftime("%H:%M:%S") in row["Time"] or moment.strftime("%H%M%S") == row["Time"]
    )
    if "Level" in row:
        checks["severity"] = normalize_severity(row["Level"]) == fields["severity"]
    return checks


@cache
def verify(key):
    """Checks every line of the dataset against Loghub's CSV and counts the agreements."""
    header, rows = read_csv(key)
    parsed = parsed_entries(key)
    totals = Counter()
    for values, (_, fields) in zip(rows, parsed):
        for name, passed in row_checks(header, values, fields).items():
            totals[name] += passed

    labels = {"message": "Message text", "time": "Clock time", "severity": "Severity level"}
    return {
        "csv_rows": len(rows),
        "parsed_lines": len(parsed),
        "checks": [
            {"name": labels[name], "matched": totals[name], "compared": min(len(rows), len(parsed))}
            for name in labels
            if name in totals or (name == "severity" and "Level" in header)
        ],
    }


def browse_csv(key, search=None, offset=0, limit=50):
    """One page of Loghub's CSV, each row marked with whether BugSense agrees with it."""
    header, rows = read_csv(key)
    parsed = parsed_entries(key)
    matching = [
        (values, fields)
        for values, (_, fields) in zip(rows, parsed)
        if not search or any(search.lower() in value.lower() for value in values)
    ]
    return {
        "header": header,
        "matches": len(matching),
        "rows": [
            {"values": values, "agrees": all(row_checks(header, values, fields).values())}
            for values, fields in matching[offset : offset + limit]
        ],
    }


# The columns of BugSense's own CSV export, used for datasets and for stored logs
EXPORT_COLUMNS = ["line", "timestamp", "severity", "service", "error_type", "request_id", "message"]


def to_csv(rows):
    """Turns a list of dictionaries into CSV text (only the export columns)."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: "" if row.get(name) is None else row[name] for name in EXPORT_COLUMNS})
    return output.getvalue()


def parsed_csv(key):
    """BugSense's own result for a dataset, as CSV, to open next to Loghub's CSV."""
    return to_csv({"line": number, **fields} for number, (_, fields) in enumerate(parsed_entries(key), start=1))


def browse(key, search=None, offset=0, limit=50):
    """One page of lines (raw text plus parsed fields), optionally only lines containing `search`."""
    rows = [
        {"line": number, "raw": entry, **fields}
        for number, (entry, fields) in enumerate(parsed_entries(key), start=1)
        if not search or search.lower() in entry.lower()
    ]
    return {"matches": len(rows), "rows": rows[offset : offset + limit]}


def catalog():
    """The list shown on the Datasets page."""
    return [
        {
            "key": key,
            "name": dataset["name"],
            "system": dataset["system"],
            "description": dataset["description"],
            "lines": len(read_entries(key)),
            "sample": read_entries(key)[0],
        }
        for key, dataset in DATASETS.items()
    ]


def import_dataset(db, key):
    """Stores a whole dataset as its own project. Importing again replaces the old copy."""
    dataset = DATASETS[key]
    project = find_or_create_project(db, dataset["name"], dataset["description"])
    db.execute(delete(Log).where(Log.project_id == project.id))
    db.execute(delete(Incident).where(Incident.project_id == project.id))

    logs = [
        Log(project_id=project.id, raw=entry, **parse_entry(entry, dataset))
        for entry in read_entries(key)
    ]
    db.add_all(logs)
    db.commit()
    detect_incidents(db, project.id)
    return project, len(logs)
