# BugSense — Logs You Can Use

Ready-made logs to paste or upload into BugSense for testing and for the
demo. Everything here goes in through the **Logs** page → **Add logs**.

**Right now (Phase 4):** every log below is stored, searchable and parsed.
BugSense reads the time, severity, service, error type, request ID and stack
trace out of each one, so the badges and filters work for pasted text too.

---

## Real-world datasets (no copying needed)

The quickest way to get real data is the **Datasets** page. It has six real
log files from the Loghub research collection, 2,000 lines each:

| Dataset | Good for showing |
|---|---|
| Apache Web Server | Hundreds of real server errors |
| OpenSSH Server | Security: failed logins and break-in attempts |
| Hadoop HDFS | A big storage cluster working normally, with some warnings |
| ZooKeeper Cluster | Many dropped connections between servers |
| Hadoop MapReduce | A network failure causing errors, retries and a CRITICAL |
| OpenStack Nova | Request IDs and HTTP 404 errors in a cloud |

- **View lines** opens the dataset viewer: every line of the file exactly as
  it is, next to what the parser read out of it. Switch to **Loghub CSV** to
  see the researchers' official CSV of the same data, with a ✓ on every row
  BugSense agrees with. The raw file, Loghub's CSV and BugSense's own CSV can
  all be downloaded.
- On the Logs page, **Export CSV** downloads the stored logs, including
  everything received so far from a live stream.
- **Import** loads all 2,000 lines at once, with their original times.
- **Stream live** sends them in a few lines per second, as if the system
  were running right now. Watch the Overview update.

Details and the source are in `backend/datasets/README.md`.

---

## The three ways to send a log

| Tab on the Logs page | What to give it | Good for |
|---|---|---|
| **Paste text** | Plain log lines, one log per line | Copying from a terminal |
| **Structured** | Fill in severity, service and message | Adding one clear log by hand |
| **Upload file** | A `.log`, `.txt`, `.json` or `.jsonl` file | Many logs at once |

**Rules:**

- One line is one log.
- A line that starts with a space or tab is joined to the line above it. This
  keeps the indented lines of a stack trace together.
- Files can be at most 2 MB and 5000 logs.
- Other file types (for example `.py` or `.pdf`) are rejected.

---

## Recommended text format

BugSense accepts any text, but this format is the one the parser understands
best:

```
DATE TIME SEVERITY [service] message
```

Example:

```
2026-10-08 10:15:03 ERROR [checkout-api] Database connection refused
```

**Other formats the parser also understands:**

| Format | Example |
|---|---|
| ISO time | `2026-10-08T10:15:03.250Z WARN slow query` |
| Brackets | `[2026-10-08 10:15:03] [ERROR] [auth] login failed` |
| Python logging | `2026-10-08 10:15:03,123 - app.orders - ERROR - could not save order` |
| Level with colon | `FATAL: database is shutting down` |
| No time or level | `ZeroDivisionError: division by zero` (treated as an ERROR) |
| Python traceback | A pasted `Traceback (most recent call last):` block becomes one log |

`WARN` is stored as `WARNING`, `ERR` as `ERROR`, and `FATAL` as `CRITICAL`.

**What counts as an error type:** any name ending in `Error` or `Exception`
(for example `TimeoutError`), or an HTTP failure such as `returned 503`,
which is stored as `HTTP 503`.

**Severity levels, from least to most serious:**

| Level | Meaning | Example |
|---|---|---|
| `DEBUG` | Detail for developers | `Retrying request, attempt 2` |
| `INFO` | Normal activity | `User 81 logged in` |
| `WARNING` | Something looks wrong but still works | `Query took 4200 ms` |
| `ERROR` | Something failed | `Connection refused` |
| `CRITICAL` | A whole feature or service is down | `Checkout page failed to load` |

---

## Scenario 1 — Database goes down

The main demo. PostgreSQL stops, the backend cannot connect, the API returns
503 and the frontend breaks. Paste this into **Paste text**:

```
2026-10-08 10:14:58 INFO [checkout-api] Order 4821 created for user 77
2026-10-08 10:15:01 WARNING [checkout-api] Database query took 4200 ms
2026-10-08 10:15:02 ERROR [postgres] FATAL: the database system is shutting down
2026-10-08 10:15:03 ERROR [checkout-api] OperationalError: connection to server at "localhost", port 5432 failed: Connection refused request_id=req-9f31
2026-10-08 10:15:03 ERROR [checkout-api] POST /checkout returned 503 Service Unavailable request_id=req-9f31
2026-10-08 10:15:04 ERROR [checkout-api] OperationalError: connection to server at "localhost", port 5432 failed: Connection refused request_id=req-9f32
2026-10-08 10:15:04 ERROR [checkout-api] POST /checkout returned 503 Service Unavailable request_id=req-9f32
2026-10-08 10:15:05 CRITICAL [web-frontend] Checkout page failed to load: upstream returned 503
```

The same scenario with a stack trace is in `samples/checkout-outage.log`.

**Try searching for:** `503`, `Connection refused`, `req-9f31`

---

## Scenario 2 — Service keeps crashing (crash loop)

A service starts, fails and restarts again and again.

```
2026-10-08 12:00:01 INFO [inventory-api] Starting inventory-api v2.3.1
2026-10-08 12:00:02 ERROR [inventory-api] RuntimeError: cache warm-up failed: out of memory
2026-10-08 12:00:02 CRITICAL [inventory-api] Process exited with code 1
2026-10-08 12:00:07 INFO [inventory-api] Starting inventory-api v2.3.1
2026-10-08 12:00:08 ERROR [inventory-api] RuntimeError: cache warm-up failed: out of memory
2026-10-08 12:00:08 CRITICAL [inventory-api] Process exited with code 1
2026-10-08 12:00:13 INFO [inventory-api] Starting inventory-api v2.3.1
2026-10-08 12:00:14 ERROR [inventory-api] RuntimeError: cache warm-up failed: out of memory
2026-10-08 12:00:14 CRITICAL [inventory-api] Process exited with code 1
```

**Try searching for:** `exited with code`, `out of memory`

---

## Scenario 3 — Timeouts and an error spike

An outside payment gateway becomes slow, then requests start failing.

```
2026-10-08 11:02:10 INFO [payment-api] Payment gateway health check passed
2026-10-08 11:02:41 WARNING [payment-api] Gateway response slow: 2900 ms request_id=req-a110
2026-10-08 11:02:44 ERROR [payment-api] TimeoutError: gateway request timed out after 5000 ms request_id=req-a111
2026-10-08 11:02:45 ERROR [payment-api] TimeoutError: gateway request timed out after 5000 ms request_id=req-a112
2026-10-08 11:02:46 ERROR [payment-api] TimeoutError: gateway request timed out after 5000 ms request_id=req-a113
2026-10-08 11:02:47 ERROR [payment-api] POST /pay returned 504 Gateway Timeout request_id=req-a113
2026-10-08 11:02:48 WARNING [payment-api] Error rate is 62% over the last minute
```

The JSON version of this scenario is in `samples/payment-errors.jsonl`.

**Try searching for:** `timed out`, `504`

---

## Scenario 4 — Wrong configuration at startup

A service cannot start because a setting is missing or wrong.

```
2026-10-08 09:30:00 INFO [notification-service] Loading configuration from .env
2026-10-08 09:30:00 ERROR [notification-service] KeyError: 'SMTP_PASSWORD'
2026-10-08 09:30:00 ERROR [notification-service] ConfigError: required setting SMTP_PASSWORD is missing
2026-10-08 09:30:00 ERROR [notification-service] ValueError: invalid DATABASE_URL: expected "postgresql://", got "postgres//localhost"
2026-10-08 09:30:01 CRITICAL [notification-service] Startup failed: invalid configuration
```

**Try searching for:** `SMTP_PASSWORD`, `ConfigError`

---

## A log with a stack trace

The indented lines stay attached to the line above them. Paste it as it is:

```
2026-10-08 14:20:11 ERROR [orders-api] ZeroDivisionError: division by zero request_id=req-c701
  File "/app/routes/orders.py", line 57, in get_average
    average = total / count
  File "/app/services/stats.py", line 12, in safe_average
    return total / count
```

Click the row after sending it to see the whole stack trace.

---

## Real errors from buggy code

`samples/buggy-code-errors.log` holds the real output of two small buggy
programs (a Python inventory script and a JavaScript user script). Each
program was run, its first error was fixed, and it was run again, until every
runtime error had appeared. Upload it with **Upload file**: 42 logs, 8 of
them errors with a stack trace.

**Important:** BugSense reads what a program *prints when it runs*, not the
source code itself. Uploading a `.py` or `.js` file's code as a `.txt` would
only store each line of code as a meaningless "log".

**Try searching for:** `ZeroDivisionError`, `TypeError`, `inventory.py`

---

## Normal logs (nothing is wrong)

Useful for showing that BugSense does not treat everything as a problem.

```
2026-10-08 08:00:00 INFO [auth-service] Service started on port 9001
2026-10-08 08:00:12 INFO [auth-service] User 14 logged in
2026-10-08 08:01:40 DEBUG [auth-service] Token refreshed for user 14
2026-10-08 08:03:05 INFO [checkout-api] Order 4790 created for user 14
2026-10-08 08:03:06 INFO [payment-api] Payment of 1499.00 INR succeeded for order 4790
```

---

## Structured (JSON) logs

**By hand:** on the **Structured** tab, choose a severity, type a service and
a message. Some to try:

| Severity | Service | Message |
|---|---|---|
| ERROR | `checkout-api` | `Database connection refused` |
| WARNING | `payment-api` | `Gateway response slow: 2900 ms` |
| CRITICAL | `web-frontend` | `Checkout page failed to load` |
| INFO | `auth-service` | `User 81 logged in` |

**As a file:** save the lines below as `my-logs.jsonl` and upload it. Each
line is one log.

```json
{"time": "2026-10-08T15:00:01Z", "level": "info", "service": "search-api", "msg": "Index rebuilt in 840 ms"}
{"time": "2026-10-08T15:00:09Z", "level": "warning", "service": "search-api", "msg": "Memory usage at 91%"}
{"time": "2026-10-08T15:00:15Z", "level": "error", "service": "search-api", "msg": "Out of memory while building index", "error_type": "MemoryError", "request_id": "req-d220"}
```

**Fields a JSON log can have:**

| Field | Required | Other accepted name | Example |
|---|---|---|---|
| `message` | Yes | `msg` | `"Database connection refused"` |
| `severity` | No | `level` | `"ERROR"` |
| `timestamp` | No | `time` | `"2026-10-08T10:15:03Z"` |
| `service` | No | | `"checkout-api"` |
| `error_type` | No | | `"TimeoutError"` |
| `request_id` | No | | `"req-9f31"` |
| `stack_trace` | No | | `"File app.py, line 3 ..."` |

A JSON log without a message is skipped, and BugSense tells you how many
were skipped.

---

## Which logs become incidents

BugSense groups problems (warnings and errors) that happen within 10 minutes
of each other. A group becomes an incident when it has a CRITICAL log, at
least 3 errors, or at least 10 warnings.

| Paste this | Result |
|---|---|
| Scenario 1 (database goes down) | 1 CRITICAL incident across 3 services |
| Scenario 2 (crash loop) | 1 CRITICAL incident (it has CRITICAL lines) |
| Scenario 3 (timeouts) | 1 MEDIUM incident (4 errors, one service) |
| Scenario 4 (wrong configuration) | 1 CRITICAL incident |
| A single error line | No incident: one error alone is treated as noise |
| Normal logs | No incident |

## Things to try on the Logs page

| What to do | What it shows |
|---|---|
| Search `503` | Finds every log containing that text |
| Search `req-9f31` | Follows one request across several logs |
| Severity filter → **ERROR** | Shows only error logs |
| Service filter → `payment` | Shows one service |
| Click a row | Opens the full raw log, with its request ID and stack trace size |
| Look at the **Error type** column | Shows what kind of failure each log is |
| Dashboard → **Top error types** | Shows which failure happens most |
| Click a row → **Delete log** | Removes that one log |
| **Delete all** | Empties the list, for example before starting a new scenario |
| Upload a `.py` file | The upload is rejected |
| Send a `.jsonl` file with a broken line | The good lines are saved, the bad one is skipped |

---

## What changes in later phases

| Phase | What will happen to these logs |
|---|---|
| 7 — AI diagnosis | BugSense explains the probable cause, for example "the database stopped first" |
| 8 — Root cause | It separates the first failure (postgres) from the failures it caused (503s) |
