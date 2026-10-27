"""Turns raw log text into structured fields, using plain rules (no AI).

Two jobs:
  1. split_into_entries(text) - cut pasted text or a file into separate logs
  2. parse_log(raw)           - read the fields out of one log

parse_log first tries the known formats of real systems (log_formats.py).
If none fits, it uses the general rules in this file.

Example of a line the parser understands:
  2026-10-08 10:15:03 ERROR [checkout-api] OperationalError: refused request_id=req-9f31
  |-- timestamp ----| |sev| |- service -| |- error type -|          |- request id -|
"""

import re
import textwrap
from datetime import datetime

from app.services.log_formats import match_known_format

# ---------- Patterns (regular expressions) ----------

# 2026-10-08 10:15:03   2026-10-08T10:15:03.123Z   [2026-10-08 10:15:03,123]
TIMESTAMP = re.compile(
    r"^\[?(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?)\]?"
)

LEVEL_WORDS = "DEBUG|INFO|WARNING|WARN|ERROR|ERR|CRITICAL|FATAL"

# ERROR   [ERROR]   ERROR:
SEVERITY = re.compile(rf"^\[?({LEVEL_WORDS})\]?:?(?=\s|$)")

# Python's default logging style:  my.module - ERROR - message
PYTHON_LOGGING = re.compile(rf"^([\w.\-]+)\s+-\s+({LEVEL_WORDS})\s+-\s+")

# [checkout-api]
SERVICE = re.compile(r"^\[([\w.\-/]+)\]\s*")

# request_id=req-9f31   requestId: abc123
REQUEST_ID = re.compile(r"\b(?:request[_-]?id|req[_-]?id)[=:]\s*\"?([\w\-]+)", re.IGNORECASE)

# OpenStack style: req-38101a0b-2096-447d-96ea-a692162415ae
REQUEST_UUID = re.compile(r"\b(req-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\b")

# ZeroDivisionError   NullPointerException   sqlalchemy.exc.OperationalError
ERROR_TYPE = re.compile(r"\b([A-Z]\w*(?:Error|Exception))\b")

# returned 503   status 500   HTTP 404
HTTP_STATUS = re.compile(r"\b(?:returned|status(?: code)?|HTTP)[ =:]+([45]\d\d)\b")

TRACEBACK_START = "Traceback (most recent call last)"

# Words that show a problem in a log that has no level word (for example SSH logs)
ERROR_WORDS = re.compile(r"\b(error|exception|fatal|panic|crash(ed)?)\b", re.IGNORECASE)
WARNING_WORDS = re.compile(
    r"\b(fail(ed|ure)?|invalid|denied|refused|break-in|time ?out|timed out|unknown)\b",
    re.IGNORECASE,
)

# Different tools use different words for the same level
SEVERITY_NAMES = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARN": "WARNING",
    "WARNING": "WARNING",
    "ERR": "ERROR",
    "ERROR": "ERROR",
    "FATAL": "CRITICAL",
    "CRITICAL": "CRITICAL",
    # Words used by Apache, Java and Linux tools
    "TRACE": "DEBUG",
    "NOTICE": "INFO",
    "SEVERE": "ERROR",
    "CRIT": "CRITICAL",
    "ALERT": "CRITICAL",
    "EMERG": "CRITICAL",
}


# ---------- Job 1: split text into entries ----------


def split_into_entries(text):
    """Splits log text into entries. Normally one line is one entry.

    Some lines belong to the entry above them and are attached to it:
      - lines that start with a space or tab (the body of a stack trace)
      - a "Traceback (most recent call last)" or "Caused by:" line
      - the final "SomeError: ..." line that ends a Python traceback
    """
    entries = []
    in_traceback = False

    for line in text.splitlines():
        # PostgreSQL cannot store the NUL character, so remove it
        line = line.replace("\x00", "").rstrip()
        if not line:
            continue

        is_indented = line[0] in (" ", "\t")
        starts_traceback = line.startswith(TRACEBACK_START)
        ends_traceback = in_traceback and not is_indented and ERROR_TYPE.match(line)
        belongs_to_previous = (
            is_indented or starts_traceback or line.startswith("Caused by:") or ends_traceback
        )

        if belongs_to_previous and entries:
            entries[-1] += "\n" + line
        else:
            entries.append(line)

        if starts_traceback:
            in_traceback = True
        elif not is_indented:
            in_traceback = False

    return entries


# ---------- Job 2: read the fields out of one entry ----------


def normalize_severity(word):
    """WARN -> WARNING, fatal -> CRITICAL, and so on. Unknown words are kept."""
    if not word:
        return None
    word = word.upper()
    return SEVERITY_NAMES.get(word, word)


def parse_timestamp(text):
    """Turns '2026-10-08 10:15:03,123' into a datetime. Returns None if it cannot."""
    try:
        return datetime.fromisoformat(text.replace(",", "."))
    except ValueError:
        return None


def find_error_type(text):
    """Finds an error name like 'TimeoutError', or an HTTP error like 'HTTP 503'."""
    match = ERROR_TYPE.search(text)
    if match:
        return match.group(1)[:100]
    match = HTTP_STATUS.search(text)
    if match:
        return f"HTTP {match.group(1)}"
    return None


def find_request_id(text):
    match = REQUEST_ID.search(text) or REQUEST_UUID.search(text)
    return match.group(1)[:100] if match else None


def guess_severity(error_type, message):
    """Used only when a log has no level word. Returns None if there is no sign of a problem."""
    if error_type:
        return "WARNING" if error_type.startswith("HTTP 4") else "ERROR"
    if ERROR_WORDS.search(message):
        return "ERROR"
    if WARNING_WORDS.search(message):
        return "WARNING"
    return None


def parse_log(raw):
    """Reads the fields out of one raw log entry and returns them as a dictionary."""
    first_line, _, other_lines = raw.partition("\n")
    rest = first_line.strip()
    fields = {
        "timestamp": None,
        "severity": None,
        "service": None,
        "error_type": None,
        "message": None,
        "request_id": None,
        "stack_trace": textwrap.dedent(other_lines) if other_lines else None,
    }

    # A bare Python traceback: the useful message is its last line
    if rest.startswith(TRACEBACK_START) and other_lines:
        fields["stack_trace"] = raw
        rest = raw.splitlines()[-1].strip()

    default_severity = None
    known = match_known_format(rest)

    if known:
        # A known real-world format (Apache, Hadoop, SSH, ...) gives us every field at once
        fields["timestamp"] = known["timestamp"]
        fields["severity"] = normalize_severity(known["severity"])
        fields["service"] = known["service"]
        rest = known["message"]
        default_severity = known["default_severity"]
    else:
        # 1. Timestamp at the start of the line
        match = TIMESTAMP.match(rest)
        if match:
            fields["timestamp"] = parse_timestamp(match.group(1))
            rest = rest[match.end():].lstrip(" -|")

        # 2. Severity and service
        match = PYTHON_LOGGING.match(rest)
        if match:
            fields["service"] = match.group(1)[:100]
            fields["severity"] = normalize_severity(match.group(2))
            rest = rest[match.end():]
        else:
            match = SEVERITY.match(rest)
            if match:
                fields["severity"] = normalize_severity(match.group(1))
                rest = rest[match.end():].lstrip(" -|")
            match = SERVICE.match(rest)
            if match:
                fields["service"] = match.group(1)[:100]
                rest = rest[match.end():]

    # 3. Whatever is left is the message
    fields["message"] = rest or first_line.strip()

    # 4. Error type and request ID can be anywhere in the entry
    fields["error_type"] = find_error_type(fields["message"]) or find_error_type(raw)
    fields["request_id"] = find_request_id(raw)

    # 5. No level written: guess it from the error type or from warning words
    if fields["severity"] is None:
        fields["severity"] = guess_severity(fields["error_type"], fields["message"]) or default_severity

    return fields
