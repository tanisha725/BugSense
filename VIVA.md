# BugSense — Viva Notes

Simple explanations of everything built so far. Updated after every phase.

**Built so far:** Phase 1 (Foundation), Phase 2 (Database), Phase 3 (Log ingestion),
Phase 4 (Log processing), real-world data, live mode, the new interface,
Phase 5 (Incident detection), Phase 6 (Service monitoring), OpenTelemetry
monitoring, Phase 7 (AI diagnosis with tools), Phase 8 (root cause
ordering), login, deployment setup, and the Huawei pitch

---

## The project in 30 seconds

> "BugSense is a tool that helps developers debug faster. It collects logs
> and errors from an application, groups related errors into one incident,
> finds the probable root cause, and suggests how to fix it. Normal code does
> the detecting and grouping. AI is used only at the end, to explain the
> problem in plain language."

**The full flow (the final goal):**

```
Raw logs → Parse them → Detect errors → Group into incidents
→ Find root cause → AI explains it → Suggest a fix → Report
```

**What works today:** BugSense runs on 12,000 real log lines from six real
systems (Apache, SSH, Hadoop, ZooKeeper, OpenStack). A dataset can be imported
at once, or streamed in live while the dashboard updates every 3 seconds. You
can also send your own logs in three ways. Each log is read by a parser that
picks out its time, severity, service, error type, request ID and stack
trace. Related failures are then grouped into incidents, each with a
severity, a title and its evidence. The demo shop is monitored with
OpenTelemetry (traces and metrics). For any incident, BugSense finds the
probable cause with 10 investigation tools, used by an AI agent or by rules,
and ranks the services from where the failure started to where it spread.

---

## Architecture

```
Browser → React (port 5173) → FastAPI (port 8000) → PostgreSQL (port 5432)
                                   ↑         ↓
        demo shop (OpenTelemetry) ─┘         └→ AI provider (optional, free)
```

| Part | What it is | Its job |
|---|---|---|
| React | The frontend (what the user sees) | Shows the dashboard and asks the backend for data |
| FastAPI | The backend (the server) | Receives requests, runs the logic, talks to the database |
| PostgreSQL | The database | Stores data permanently |

> "It is a three-tier architecture: frontend, backend and database. The
> browser never talks to the database directly. It always goes through the
> backend."

**Why a modular monolith and not microservices?**

> "A modular monolith is one backend application divided into clear modules.
> Microservices would mean many small servers that are harder to run, test
> and debug. For a project of this size, one well-organised backend is
> simpler and is enough."

---

## Folder structure

```
BugSense/
├── frontend/src/
│   ├── components/   small reusable pieces of the screen: the top bar,
│   │                 cards, charts (ActivityChart, RingGauge, BarList,
│   │                 SeverityBreakdown), LogForm, LogTable
│   ├── assets/       images (the brain picture in the System pulse card)
│   ├── pages/        full screens (Dashboard, Incidents, Services, Telemetry,
│   │                 Logs, Datasets, Tools)
│   ├── services/     code that calls the backend (api.js)
│   ├── App.jsx       the layout and the page routes
│   ├── index.css     all the styling
│   └── main.jsx      starts React
├── backend/
│   ├── app/main.py       starts the server, has the /health endpoint
│   ├── app/database.py   the connection to PostgreSQL
│   ├── app/models.py     the database tables
│   ├── app/schemas.py    the shape of data going in and out of the API
│   ├── app/routes/       the API endpoints, one file per feature
│   │                     (logs, incidents, monitoring, projects, datasets,
│   │                     telemetry, tools)
│   ├── app/services/     the logic the routes use: log_parser.py,
│   │                     log_formats.py, incident_detector.py, monitor.py,
│   │                     datasets.py, replay.py, projects.py, incidents.py,
│   │                     otlp.py, telemetry.py, tools.py, diagnosis.py
│   ├── datasets/         real log files from Loghub (with their source)
│   └── tests/            automatic tests
├── demo-services/    three small programs that act as a shop to monitor,
│                     plus otel.py (their OpenTelemetry setup)
├── samples/          example log files for the demo
├── .env.example      example settings
└── README.md
```

---

## Phase 1 — Foundation

**What I built:** a React page that asks the FastAPI server "are you alive?"
and shows the answer on a dashboard.

**Why:** every later feature needs the frontend and backend to talk to each
other, so I proved that connection first.

**How it works, step by step:**

1. The dashboard page loads in the browser.
2. It sends a request to `GET /health` on the backend.
3. The backend replies with JSON: `{"status": "ok", ...}`.
4. The dashboard shows **Online** in green. If no reply comes, it shows
   **Offline** in red.

**What to say:**

> "In Phase 1 I set up React with Vite for the frontend and FastAPI for the
> backend. The backend has one endpoint, /health, that returns JSON. The
> dashboard calls it when the page loads and shows whether the backend is
> online. All backend calls go through one file, services/api.js, so the
> backend address is written in only one place."

### Likely questions

**What is an API endpoint?**
A URL on the server that does one job. `GET /health` returns the server's
status.

**What is JSON?**
A simple text format for sending data, written as key–value pairs, for
example `{"status": "ok"}`. The frontend and backend use it to talk.

**Why FastAPI?**
It is a Python framework that is fast, needs very little code, and creates
API documentation automatically at `/docs`.

**Why React? What is Vite?**
React builds the screen from small reusable components. Vite is the tool that
runs the React app during development and refreshes the page instantly when I
change code.

**What is CORS and why did you need it?**
The frontend runs on port 5173 and the backend on port 8000. Browsers treat
different ports as different websites and block requests between them for
safety. CORS is the backend saying "requests from my frontend are allowed".

**What is `useEffect` in the dashboard?**
A React feature that runs code after the page appears. I use it to call the
backend once when the dashboard loads.

**What is `useState`?**
It lets a component remember a value, such as whether the backend is online.
When the value changes, React redraws that part of the screen.

**What is a virtual environment (`venv`)?**
A private folder of Python packages just for this project, so they do not
clash with other projects on the same computer.

**What is `requirements.txt` / `package.json`?**
The list of packages the project needs. `requirements.txt` is for Python,
`package.json` is for JavaScript.

**Why are settings in environment variables?**
So addresses and secrets are not written inside the code. `.env.example`
shows which settings exist. The real `.env` file is never uploaded to Git.

---

## Phase 2 — Database

**What I built:** a PostgreSQL database with four tables, connected to
FastAPI.

**Why:** logs and incidents must be saved permanently. Without a database,
all data would be lost whenever the server restarts.

**The four tables:**

| Table | What it stores | Main fields |
|---|---|---|
| `users` | People who use BugSense | name, email, password_hash |
| `projects` | An application being monitored | name, description, owner_id |
| `logs` | Every log line received | raw text, severity, service, message, timestamp |
| `incidents` | A group of related errors | title, severity, status, error_count |

**How the tables are connected:**

```
User ──owns many──> Project ──has many──> Log
                       │                   ▲
                       └──has many──> Incident ──groups many──┘
```

- One user owns many projects.
- One project has many logs and many incidents.
- One incident groups many logs.
- A log may belong to no incident (for example a normal INFO message).

**What to say:**

> "In Phase 2 I added PostgreSQL. I use SQLAlchemy, which is an ORM, so I
> write each table as a Python class instead of writing SQL by hand. There
> are four tables: users, projects, logs and incidents. They are connected
> with foreign keys. The tables are created automatically when the backend
> starts. The health endpoint also checks the database, so the dashboard
> shows whether the database is connected."

### Likely questions

**Why PostgreSQL?**
It is a free, reliable relational database. My data has clear relationships
(user → project → logs), and a relational database is designed for that.

**What is an ORM?**
Object-Relational Mapper. It lets me work with database rows as Python
objects. SQLAlchemy turns my Python code into SQL.

**What is a primary key?**
A unique ID for each row. Every table has an `id` column.

**What is a foreign key?**
A column that points to a row in another table. `projects.owner_id` points to
a user, which is how the database knows who owns a project.

**What kind of relationships do you have?**
All are one-to-many: one user has many projects, one project has many logs
and incidents, one incident has many logs.

**Why store `password_hash` and not the password?**
Storing real passwords is unsafe. A hash is a one-way scrambled version, so
even if the database leaks, the real passwords are not visible. (Login is
added in a later phase.)

**Why does the `logs` table have a `raw` column and also separate fields?**
`raw` keeps the log exactly as it arrived, so nothing is lost. The other
fields (severity, service, message and so on) are filled in by the parser in
Phase 4, which makes searching and filtering easy.

**What is `engine`, and what is a session?**
The engine is the connection to the database. A session is one conversation
with it: open it, read or write data, close it.

**What does `get_db()` do?**
It gives a route a database session and always closes it afterwards, even if
an error happens.

**How are the tables created?**
`Base.metadata.create_all(engine)` runs when the server starts and creates
any table that does not exist yet.

**What is the limitation of that?**
It only creates missing tables. It does not change a table that already
exists. A real product would use a migration tool such as Alembic. I avoided
it to keep the project simple.

**What happens if the database is down?**
The backend still starts. `/health` reports `"database": "unavailable"` and
the dashboard shows it in red, so the problem is visible instead of the whole
app crashing.

**How do you test without a database?**
The tests use a temporary in-memory SQLite database, so they run anywhere
without PostgreSQL.

---

## Phase 3 — Log ingestion

**What I built:** a way to send logs into BugSense, save them, and look at
them. "Ingestion" simply means taking data in.

**Why:** BugSense cannot analyse anything until it has logs. This phase is
the entry door for all the data.

**Three ways to send logs:**

| Way | Endpoint | Used for |
|---|---|---|
| Paste text | `POST /logs/text` | Copying log lines from a terminal |
| Structured JSON | `POST /logs` | Applications that send logs automatically |
| File upload | `POST /logs/upload` | A saved `.log`, `.txt`, `.json` or `.jsonl` file |

**Reading logs back:** `GET /logs` returns the newest logs first. It can
filter by search text, severity and service. `GET /logs/stats` counts logs by
severity for the dashboard.

**Deleting logs:** `DELETE /logs/{id}` removes one log and `DELETE /logs`
removes all of them. On the Logs page, click a row to find **Delete log**, or
use **Delete all** to start a demo with an empty list.

**How it works, step by step (file upload):**

1. The user picks a file on the Logs page and clicks **Send logs**.
2. React sends the file to `POST /logs/upload`.
3. The backend checks the file type and the size (maximum 2 MB).
4. It reads the file as text and splits it into separate log entries.
5. Each entry is saved as one row in the `logs` table.
6. The backend replies with how many logs were saved, and the page refreshes
   the list.

**What to say:**

> "In Phase 3 I built log ingestion. Logs can come in three ways: pasted
> text, structured JSON, or a file upload. Every log is stored in PostgreSQL
> with its original text kept in a raw column. The Logs page shows the newest
> logs and lets me search and filter them. In this phase text was only
> stored as it is. Reading the severity and service out of it was added in
> Phase 4."

### Likely questions

**What is the difference between a raw log and a structured log?**
A raw log is one line of plain text. A structured log is JSON with named
fields such as `severity`, `service` and `message`, so nothing has to be
guessed.

**How do you split text into log entries?**
One line is one log. A line that starts with a space or tab belongs to the
line above it, which keeps the indented lines of a stack trace together. A
Python `Traceback` block is also kept with the line above it. This is in
`services/log_parser.py`.

**How do you keep file upload safe?**
- Only `.log`, `.txt`, `.json` and `.jsonl` files are accepted.
- Files larger than 2 MB are rejected.
- At most 5000 entries are accepted at once.
- The file is only read as text. It is never run.

**What is the difference between GET, POST and DELETE?**
GET asks for data and changes nothing. POST sends new data to the server to
be saved. DELETE removes data. Together with PUT (update) these make up CRUD:
create, read, update, delete.

**Why does "Delete all" ask for confirmation?**
Deleting cannot be undone, so the page asks "are you sure?" first. Deleting a
single log does not ask, because losing one log is a small mistake.

**What do the status codes mean?**
`200` OK, `201` created, `400` bad request (for example a wrong file type),
`404` not found, `413` too large, `422` the data has the wrong shape.

**What is Pydantic / what is `schemas.py`?**
Pydantic checks that incoming data has the right shape before my code uses
it. `schemas.py` describes those shapes. For example, a structured log must
have a message. If it does not, FastAPI rejects it automatically with `422`.

**What is the difference between `models.py` and `schemas.py`?**
Models describe database tables. Schemas describe the data that travels
through the API.

**Why are there `routes/` and `services/` folders?**
Routes receive the request and send the reply. Services hold the actual
logic. Keeping them apart makes the code easier to read and to test.

**What is `Depends(get_db)`?**
It is FastAPI's dependency injection. FastAPI gives each route a database
session automatically and closes it when the route finishes.

**How does the search work, and is it safe from SQL injection?**
It uses a case-insensitive "contains" match on the raw text. SQLAlchemy sends
the user's text as a parameter, separately from the SQL, so it cannot change
the query.

**Which project do the logs belong to?**
The one chosen in the top bar. If "All projects" is chosen, your own logs go
into a "Demo Project" that is created automatically. Each imported dataset
gets its own project. Real users come with authentication later.

**Why is there a limit of 100 logs on the page?**
Loading every log would get slow as the table grows. The API returns the
newest 100 by default and never more than 500.

**How does the frontend have several pages?**
React Router. The address `/` shows the Overview, `/logs` the Logs page and
`/datasets` the Datasets page, without reloading the whole site.

**How is this tested?**
There are 52 automatic tests. They cover all three ways of sending logs, the
parser (including the six real formats), the filters, the counts, deleting,
importing datasets, the live replay, CSV export, the check against
Loghub's CSV, incident detection, service monitoring with a real crashing
program, and that a wrong file type is rejected.

---

## Phase 4 — Log processing

**What I built:** a parser. It reads one raw log line and pulls out the
separate pieces of information inside it.

**Why:** a raw log is just a sentence to a computer. To count errors, filter
by service or group failures later, BugSense needs each piece in its own
column.

**Example:**

```
2026-10-08 10:15:03 ERROR [checkout-api] OperationalError: refused request_id=req-9f31
```

| Field | Value found | How it is found |
|---|---|---|
| timestamp | `2026-10-08 10:15:03` | Date and time at the start of the line |
| severity | `ERROR` | A level word right after the time |
| service | `checkout-api` | The name inside square brackets |
| error type | `OperationalError` | A word ending in `Error` or `Exception` |
| request ID | `req-9f31` | The value after `request_id=` |
| message | `OperationalError: refused ...` | Whatever is left |
| stack trace | (none here) | The indented lines under the first line |

**How it works, step by step:**

1. The text is split into entries (one log each).
2. For each entry, the parser looks for a timestamp at the start and removes
   it from the text.
3. It looks for a severity word, then a service name in brackets, removing
   each one as it is found.
4. What remains is the message.
5. It searches the whole entry for an error type and a request ID.
6. If no severity was written but an error type was found, it marks the log
   as `ERROR`.
7. The fields are saved in their own columns in the `logs` table.

**What to say:**

> "In Phase 4 I built a rule-based log parser in plain Python. It uses
> regular expressions to read the timestamp, severity, service, error type,
> request ID and stack trace out of each log. I did not use AI here because
> log formats follow patterns, and normal code is faster, free and always
> gives the same answer for the same input. The parsed fields are stored in
> separate columns, so the dashboard can count errors and show the most
> common error types."

### Likely questions

**What is a regular expression (regex)?**
A pattern that describes what text should look like. For example,
`\d{4}-\d{2}-\d{2}` means "four digits, a dash, two digits, a dash, two
digits", which matches a date such as `2026-10-08`.

**Why did you not use AI for parsing?**
Four reasons: normal code is much faster, it costs nothing, it gives the same
result every time, and I can explain exactly why it gave that result. AI is
kept for the part where it really helps, explaining the root cause.

**What does "rule-based" mean?**
The program follows fixed rules that I wrote, such as "a word ending in
Error is an error type". It does not learn or guess.

**Which log formats does it understand?**
The common ones: `time LEVEL [service] message`, ISO timestamps, bracketed
levels, Python's default logging format, levels with a colon such as
`FATAL:`, and Python tracebacks. The full list with examples is in `LOGS.md`.

**What happens to a log it cannot understand?**
Nothing is lost. The whole line is kept as the message and in the raw
column, and the other fields stay empty. It shows as "No level" on the
dashboard.

**What is normalisation?**
Different tools use different words for the same level. The parser stores
`WARN` as `WARNING`, `ERR` as `ERROR` and `FATAL` as `CRITICAL`, so the
filters need only five levels.

**How does it find the error type?**
It looks for a word ending in `Error` or `Exception`, such as
`ZeroDivisionError`. If there is none, it looks for an HTTP failure such as
`returned 503` and stores `HTTP 503`.

**Why guess the severity when it is missing?**
Raw crash output such as `ZeroDivisionError: division by zero` has no level
word, but it is clearly an error. Without this rule it would not be counted
as one. HTTP 4xx codes become `WARNING` and everything else becomes `ERROR`.

**What is a stack trace and how is it handled?**
It is the list of code lines the program was running when it failed. Its
lines are indented, so the parser keeps them with the error line above and
stores them in the `stack_trace` column.

**What is a request ID and why does it matter?**
A label given to one user request. Every log written while handling that
request carries the same ID, so searching for it shows the whole story of one
failure. Phase 8 uses it to link related errors.

**Are structured JSON logs parsed too?**
They already have named fields, so they are not parsed line by line. The
parser only fills gaps: it normalises the severity and finds an error type or
request ID inside the message if the sender did not give one.

**What are the limits of this parser?**
- It only knows the formats I wrote rules for. A very unusual format would be
  stored but not split into fields.
- A timestamp without a time zone is assumed to be local time.
- A silent bug that prints no error cannot be detected from logs at all.

**How is the parser tested?**
There are 9 tests only for the parser, one per format, plus tests that check
an uploaded file ends up with the right fields in the database.

---

## Phase 5 — Incident detection

**What I built:** BugSense now groups related failures into **incidents**. An
incident is one problem, even if it produced hundreds of error lines.

**Why:** a developer cannot read 600 separate errors. They need to see "there
are 3 problems right now, this one is the most serious". Grouping also keeps
related errors together, so the cause is easier to find.

**The rule, in one sentence:** problems that happen close together in time are
probably one incident.

**How it works, step by step** (`services/incident_detector.py`):

1. Take the project's problem logs (WARNING, ERROR, CRITICAL), oldest first.
2. Cut them into **bursts**: a quiet gap of more than 10 minutes starts a new
   burst.
3. A burst becomes an incident only if it matters: at least one CRITICAL log,
   or at least 3 errors, or at least 10 warnings. One error on its own is
   treated as noise.
4. Give the incident a **severity**, a **title** and an **affected service**.
5. Link every log in the burst to the incident, through the `incident_id`
   column planned in Phase 2.

**Severity rules:**

| Severity | When |
|---|---|
| CRITICAL | any CRITICAL log, or errors in 3 or more services at once |
| HIGH | 20 or more errors, or errors in 2 services at once |
| MEDIUM | 3 or more errors |
| LOW | only warnings (10 or more) |
| INFO | part of the scale, but BugSense opens incidents only from LOW up |

The incident page shows **why** it got its severity, for example "1 CRITICAL
log(s)", next to this table.

**Title:** the first error in the burst, for example
"FATAL: the database system is shutting down in postgres (+2 more
services)". The first failure is often the best hint about where the trouble
started. Numbers and IDs are replaced by `<*>`, so "error state 6" and
"error state 7" read as the same problem.

**The demo scenario:** in `samples/checkout-outage.log` the database stops,
the backend cannot connect, the API returns 503 and the web page fails. These
errors arrive within seconds, so they become **one CRITICAL incident** across
3 services, instead of 7 separate errors.

**When detection runs:** automatically, every time logs arrive (paste, upload,
dataset import, and every second of a live stream), and when logs are deleted.
There is also a **Run detection again** button. Open incidents are rebuilt
from scratch each time. Resolved incidents are kept as history and are never
changed.

**What to say:**

> "In Phase 5 BugSense groups related failures into incidents. The rule is
> simple: problems that happen close together in time are probably one
> incident. I sort the warnings and errors by time, and a gap of more than 10
> minutes starts a new group. A group becomes an incident if it has a CRITICAL
> log, at least 3 errors, or at least 10 warnings. The severity comes from
> clear rules, for example errors in three services at the same time is
> CRITICAL. In the demo, a database failure that causes backend errors, API
> 503s and a broken page becomes one critical incident instead of seven
> separate errors."

### Likely questions

**Why group by time?**
When something breaks, everything that depends on it fails at about the same
moment. Time is the simplest strong signal that errors are related. Phase 8
adds request IDs and service dependencies to find which failure came first.

**Why 10 minutes?**
I tested it on the six real datasets. With 5 minutes, one Apache problem that
kept coming back was split into 59 incidents. With 10 minutes it became 18.
Longer gaps start joining unrelated problems. The value is one constant at
the top of the file, `BURST_GAP`, so it is easy to change.

**Why is one error not an incident?**
Real systems log single errors all the time, for example one user typing a
wrong URL. Opening an incident for each one would bury the real problems.
This is called alert fatigue.

**Why not use AI or machine learning to group errors?**
The rules are fast, free, give the same result every time, and I can explain
every decision. The incident page even lists the reason for each severity. AI
comes later, to explain an incident in plain language, not to decide what an
incident is.

**What is a message template?**
The message with its changing parts (numbers, IDs, IP addresses) replaced by
`<*>`. It shows that "Child 6725 in slot 10" and "Child 6726 in slot 8" are
the same kind of event. Loghub calls this an "EventTemplate".

**What does "resolved" do?**
A developer marks an incident resolved when it is fixed. Resolved incidents
are kept as history and are never rebuilt. Only open incidents are
recalculated when new logs arrive.

**Where are first seen, duration and the services stored?**
They are not stored. They are calculated from the incident's logs whenever
the incident is shown. That way they can never get out of date, and the
incidents table from Phase 2 did not need to change.

**What are the limits of this approach?**
- Two unrelated problems that happen at the same time end up in one incident.
- A slow problem with gaps longer than 10 minutes is split into several.
- The title uses the first error, which is a hint, not proof of the cause.
  Proper root cause analysis is Phase 8.

**How is it tested?**
Unit tests check bursts, templates and every severity rule. API tests check
the checkout outage (one CRITICAL incident across 3 services), that a single
error makes no incident, that resolved incidents stay, and that importing the
Hadoop dataset gives one CRITICAL incident with 152 errors.

**What do the six datasets give?**

| Dataset | Incidents | Notes |
|---|---|---|
| Hadoop MapReduce | 1 CRITICAL | The network failure: 152 errors, 8 services |
| Apache | 18 | The same connector error coming back during the day |
| OpenSSH | 7 | Waves of failed logins |
| ZooKeeper | 1 | Long runs of dropped connections |
| HDFS | 3 LOW | Only warnings: a healthy cluster |
| OpenStack | 1 LOW | Repeated "unknown base file" warnings |

---

## Phase 6 — Service monitoring (instead of Docker)

**What I built:** BugSense now starts a small demo shop of three real
programs and watches them: whether each one is running, whether it is
healthy, how often it restarted, and whether it is stuck in a crash loop.

**Why:** many failures are not just error messages. A program can crash,
refuse to start or stop answering. A debugging tool should notice that and
connect it to the errors it causes.

**Why not Docker?** The original plan was to monitor Docker containers, but
Docker made my laptop hang. So BugSense does the supervising itself. The
ideas are exactly the same:

| Docker does | BugSense does it with |
|---|---|
| `docker start` / `docker stop` | starting and stopping a normal process (`subprocess`) |
| restart policy | restarting a crashed service, waiting longer each time |
| "restarting" (crash loop) state | 3 crashes within 60 seconds = crash loop, give up after 6 |
| healthcheck | calling the service's `/health` page every 3 seconds |
| `docker logs` | reading everything the program prints |
| `docker events` | an event list: started, exited with code 1, unhealthy... |

**The demo shop** (`demo-services/`, plain Python, no extra packages):

```
shop-web  →  shop-api (port 9101)  →  shop-db (port 9102)
```

- **shop-web** acts like customers: one checkout every second.
- **shop-api** handles the checkout and asks shop-db. It is "healthy" only
  if it can reach shop-db.
- **shop-db** is a pretend database.
- Every checkout carries one request ID through all three.

**How it works, step by step** (`services/monitor.py`):

1. **Start all** starts the three programs as child processes of BugSense.
2. A small thread per program reads every line it prints and stores it as a
   log. The lines of a crash's stack trace are kept together.
3. A watcher thread looks at the programs twice a second:
   - Did one exit on its own? That is a crash: record "Exited unexpectedly
     with code 1" and restart it after 2 s, then 4 s, then 6 s...
   - 3 crashes within 60 s: record a **crash loop** (CRITICAL). After 6, it
     gives up.
   - Every 3 s it calls `/health`, and records when a service becomes
     unhealthy or healthy again.
4. Each event is stored as a log of that service, so incident detection
   groups a crash together with the errors it caused.

**The four demo failures** (Services page, one click each):

| Scenario | What happens | What BugSense shows |
|---|---|---|
| Database goes down | shop-db is stopped | shop-api unhealthy, 503 errors in shop-api and shop-web, one HIGH incident |
| Crash loop | shop-api crashes 1.5 s after starting | exit code 1, restarts, crash loop, gave up, one CRITICAL incident |
| Slow API | many checkouts hang | timeouts in shop-web, warnings in shop-api |
| Wrong configuration | shop-api gets a broken database address | "ConfigError" and "Startup failed", then a crash loop |

**Recover** removes every fault and starts everything normally.

**What to say:**

> "Instead of Docker, BugSense supervises the services itself. It starts
> three demo programs, a small shop with a web front end, an API and a
> database, as normal processes. Like Docker, it restarts a program that
> crashes, notices a crash loop after three crashes in a minute, and checks
> each service's health page every three seconds. Every event, such as
> 'exited with code 1' or 'health check failed', is stored as a log of that
> service, so the incident detector puts the crash and the errors it caused
> into the same incident."

### Likely questions

**What is a process?**
A program that is running. Each demo service is a separate process with its
own process ID (PID), shown on its card.

**What is a crash loop?**
A program that crashes, is restarted, and crashes again straight away, over
and over. Restarting cannot fix it, so BugSense reports it as CRITICAL and
stops trying after 6 crashes.

**Why wait longer before each restart?**
This is called back-off. Restarting instantly would waste the computer's
effort and fill the logs. Docker and Kubernetes do the same.

**What is a health check?**
A small page, `/health`, that says whether the service can do its job.
shop-api's health page also checks shop-db, so when the database stops, the
API is still running but reported as **unhealthy**. Running is not the same
as working.

**What is an exit code?**
The number a program returns when it ends. 0 means it finished normally.
Anything else, like 1, means it failed.

**How are the crashes connected to incidents?**
Every monitor event is stored as a log with the service's name, a severity
and an error type (`ProcessExit`, `CrashLoop`, `HealthCheckFailed`). The
incident detector from Phase 5 then groups them with the service's own
errors, because they happen at the same time.

**Is it safe? Can it run any program?**
No. It can only start the three programs listed in the code. A request for
any other name is refused with "Unknown service". No user input is ever run
as a command.

**What happens to the demo programs when BugSense stops?**
BugSense stops them when it shuts down, so nothing is left running.

**What would change with Docker?**
Only how programs are started and observed: the Docker API instead of
`subprocess`. Health checks, restart counting, crash loops and the link to
incidents would stay the same.

**How is it tested?**
A test runs a real little program that crashes on purpose. It checks that
BugSense restarts it, calls it a crash loop, gives up, stores `ProcessExit`
and `CrashLoop` logs, and opens one CRITICAL incident. Other tests check
that stack trace lines stay together and that unknown services are refused.

---

## Real-world data and live mode

**What I built:** BugSense can now load real logs from six real systems, and
can replay one of them "live" so the dashboard fills up in real time.

**Why:** made-up examples only prove that the code works on the examples I
wrote. Real logs prove that it works on data I did not design.

**Where the data comes from:** **Loghub**, a public collection of logs from
real systems, published by researchers (Zhu et al., IEEE ISSRE 2023) and used
in many log-analysis papers. I used its 2,000-line sample of six systems:

| Dataset | System | What is interesting in it |
|---|---|---|
| Apache | Web server | 595 errors from a failing connector |
| OpenSSH | Security | Hundreds of failed logins and break-in attempts |
| HDFS | Distributed storage | Block operations on a 200+ machine cluster |
| ZooKeeper | Coordination | Many dropped-connection warnings |
| Hadoop MapReduce | Big data | A job hit by a network failure, with retries |
| OpenStack | Cloud | Request IDs and HTTP 404 errors |

**How the parser handles them:** every system writes logs in its own format,
so I added a list of known formats in `log_formats.py`. Each format is one
regular expression with named parts (time, level, service, message). The
parser tries them in order and uses the first that fits. This is the same
idea as "grok patterns" in real tools such as Logstash. On all 12,000 lines,
every line matched its format and got a timestamp.

**How live mode works, step by step:**

1. On the Datasets page I click **Stream live** and choose a speed.
2. The backend starts a background thread (`services/replay.py`).
3. Every second the thread takes the next few lines, parses them, stamps
   them with the current time, and saves them.
4. The browser asks the backend for new numbers every 3 seconds
   ("polling"), so the counters, the chart and the latest errors update.
5. **Stop** tells the thread to finish. Only one stream runs at a time.

**What to say:**

> "To test BugSense on real data, I used Loghub, a public research
> collection of logs from real systems. I imported six of them: 12,000 lines
> from Apache, SSH, Hadoop, ZooKeeper and OpenStack. Each system has its own
> log format, so the parser has a list of known formats and tries each one.
> To show real-time monitoring, BugSense can replay a dataset a few lines per
> second, and the dashboard polls the backend every three seconds."

### Likely questions

**Why Loghub and not a Kaggle dataset?**
Loghub is the standard source for log research, and it is cited in many
papers. Kaggle mostly has mirrors of it, and downloading from Kaggle needs an
account and an API key. Loghub's files come straight from its GitHub page.

**Is the live data really live?**
It is real data replayed in real time. The log lines are real, but they were
recorded in the past. Replay is a normal way to test monitoring tools,
because you can repeat the exact same situation in every demo. In a real
deployment, an application would send its logs to `POST /logs` as they
happen.

**What is a background thread and why use one?**
A thread is a second line of work running inside the same program. The
replay runs in a thread so the API keeps answering requests while the replay
sends lines.

**What is polling? Why not WebSockets?**
Polling means the browser asks "anything new?" at a fixed interval, here
every 3 seconds. WebSockets would let the server push updates, but they add
complexity. For a dashboard, a 3-second delay is fine, so polling is the
simpler choice.

**Why are replayed logs stamped with the current time?**
So they appear as "happening now" on the live chart. The original line, with
its original time, is still kept in the raw column.

**SSH logs have no year. How do you date them?**
The parser assumes this year. If that date would be in the future, it uses
last year instead. This is the usual rule for syslog-style logs.

**What is a project here?**
One monitored application. Each dataset becomes its own project, and the
dropdown in the top bar chooses which project the dashboard shows. This uses
the `projects` table designed in Phase 2.

**Can you show me the dataset?**
Yes. On the Datasets page, click a dataset to open the dataset viewer. It
shows:
- facts about the file: number of lines, size, time range, and how many
  lines the parser recognised (100% for all six)
- the severity mix, the top services and the top error types
- every line of the file exactly as it is, next to the time, severity,
  service and error type the parser read out of it, with search and pages
- a **Download raw file** button for the original file, and a link to the
  Loghub source

The files themselves are in `backend/datasets/`, unchanged.

**How can I (the examiner) verify the dataset and the results?**
Three ways, all on the dataset's page:
1. **Loghub CSV view.** Loghub's researchers published each dataset as a CSV
   with every line already split into columns (time, level, component,
   content). BugSense shows that CSV exactly as published.
2. **Automatic check.** BugSense parses the raw `.log` file on its own and
   never reads the CSV to do it. Then every line is compared with the same
   CSV row: message text, clock time and severity level. The result is shown
   in the dark "Verification" card: 2,000 out of 2,000 lines match, for all
   six datasets. Each CSV row also gets a ✓ in the "BugSense agrees" column.
3. **Downloads.** The raw `.log`, Loghub's CSV and BugSense's own CSV can be
   downloaded and opened side by side in Excel.

A direct link that opens the CSV view: `http://localhost:5173/datasets/apache?view=csv`.

**Can you export the live data?**
Yes. On the Logs page, **Export CSV** downloads every stored log that matches
the current filters as a CSV file, including everything a live stream has
sent so far. The project in the top bar decides which logs are exported.

**Why is OpenStack's message check "contained" and not "equal"?**
Loghub moves the request ID into its own column. BugSense keeps it in the
message and also stores it in its `request_id` field. So the check is that
Loghub's text is found inside BugSense's message, and that holds for every
line.

**How did testing on real data help?**
It found two real bugs. Pasted logs were going into the wrong project, and
SSH dates landed in the future. Both were fixed and now have tests.

---

## The interface

**Design idea:** frosted-glass cards on a soft light background, with a few
dark cards for the most important things: the System pulse and the latest
errors. It follows a "bento grid" layout: different-sized boxes that fit
together like a lunch box.

**What is on the Overview page:**

| Card | What it shows |
|---|---|
| System pulse | The brain-and-heart picture with a beating glow, backend and database status, and a Live badge |
| Four numbers | Total logs, errors, warnings, open incidents (they count up smoothly) |
| Health rings | Error rate and warning rate as percentage rings |
| Activity over time | Stacked columns: errors, warnings and other logs over time |
| Logs by severity | One split bar plus exact numbers and percentages |
| Top error types | The most common named errors |
| Busiest services | Which services log the most, with their errors in red |
| Open incidents | How many incidents are open, and how many are critical |
| Active incidents | The most serious open incidents, linking to their pages |

### Likely questions

**Which chart library did you use?**
None. The charts are plain HTML and SVG drawn by my own small React
components, for example `ActivityChart.jsx` and `RingGauge.jsx`. This keeps
the project light and I can explain every line.

**How did you choose the colours?**
Colour is used only for meaning. Red means errors, amber means warnings, and
normal logs are grey, so problems stand out at a glance. These red and amber
shades come from a palette tested for colour-blind readers, and every colour
always has a text label next to it. All colours are defined once as CSS
variables at the top of `index.css`.

**How does the frosted glass effect work?**
The CSS `backdrop-filter: blur()` property blurs whatever is behind a
see-through card. Behind the cards are a few large, soft, blurred circles of
colour.

**How does the brain picture work?**
It sits inside the dark System pulse card. The CSS blend mode `screen` hides
the black parts of the picture and keeps only its light lines. A red glow
placed on the heart pulses in a double beat, like a real heart.

**Does the animation slow the app down?**
No. The animations only change `transform` and `opacity`, which the
graphics card handles without redrawing the page. They switch off
automatically for people who turn on "Reduce motion" on their computer.

**Does it work on a phone?**
Yes. The grid changes from 12 columns to 6, then to 1 on small screens.

---

## OpenTelemetry monitoring (professor's feedback: "use telemetry")

**What I built:** BugSense now monitors the demo shop with **OpenTelemetry**,
the industry standard for telemetry. Each service sends:

| Signal | What it is | Example |
|---|---|---|
| **Traces** | One request, step by step, across services | shop-web → shop-api → shop-db, 20 ms, which step failed |
| **Metrics** | Numbers over time | request durations, CPU seconds, memory |
| **Logs** | Log lines, linked to their trace by a trace ID | "OperationalError ... trace_id=4bf9..." |

**How it works, in order:**

1. Each demo service calls `otel.setup("shop-api")` (in `demo-services/otel.py`).
2. Every checkout becomes a **span**. The trace ID travels to the next service
   in the standard `traceparent` HTTP header, so one checkout is **one trace**.
3. The OpenTelemetry SDK sends the data every few seconds with **OTLP**
   (OpenTelemetry Protocol) to BugSense at `/v1/traces` and `/v1/metrics`.
4. BugSense (`services/otlp.py`) reads the message (binary protobuf or JSON)
   and stores spans and metric points in two new tables.
5. `services/telemetry.py` calculates, per service: requests per minute,
   error rate, latency p50/p95/p99, CPU % and memory.
6. If a service's error rate goes above 20% or its p95 latency above 1 second
   (over the last minute), BugSense stores an **alert log**. Incident
   detection then puts the alert into the same incident as the errors.

> "Before, BugSense only knew if a process was running and if /health
> answered. Now it sees every request: how long it took, where it went, and
> where it failed. That is what professional monitoring tools do, and I used
> the same standard, OpenTelemetry, that Huawei Cloud's AOM and APM accept."

### Telemetry from uploaded logs

Uploaded logs are records of the past, so nothing can be measured live. But
the logs **contain** telemetry, and BugSense calculates it ("metrics from
logs", a normal technique in monitoring tools):

| From the logs | Becomes |
|---|---|
| Logs with the same request ID in several services | One **trace**; each service is a span; failed if any of its logs is an error |
| "in 19 ms", "took 2.3 s", "time: 0.27" | The **latency** of that span |
| Every log | **Logs per minute** and the share of error logs, per service (metric `log.records`) |

It is stored with `source = "logs"`, so the page shows **"From logs"**, while
the demo shop's data shows **"Measured"**. It is recalculated after every
upload, and the **All data** button shows the logs' own time range.

Real example: the OpenStack dataset gives 938 traces from its request IDs,
and 809 API requests with p50 264 ms and p95 411 ms, read from lines ending in
`time: 0.2717581`.

> "Live programs send telemetry over OpenTelemetry. For uploaded logs,
> BugSense calculates the same telemetry from the logs: request IDs become
> traces, written durations become latency, and every log counts towards the
> activity and error rate. The page always says which numbers were measured
> and which were calculated."

### Likely questions

**Is telemetry from logs as good as measured telemetry?**
No. It can only use what the logs say. Without request IDs there are no
traces, and without written durations there is no latency, only log activity
and error share. That is why every number is marked "Measured" or "From logs".

**What is a span? What is a trace?**
A span is one step (for example "shop-api handles GET /checkout"). A trace is
all the spans of one request. Each span knows its parent, so a trace is a tree.

**How does the trace go from one service to the next?**
The calling service adds a `traceparent` header to its HTTP request. The next
service reads it and makes its span a child of the caller's span.

**What are p50, p95 and p99?**
Percentiles. p95 = 300 ms means 95% of requests took 300 ms or less. Averages
hide slow requests; p95 shows what the slowest users feel.

**What is the RED method?**
Rate (requests per minute), Errors (how many failed), Duration (latency).
BugSense computes all three from the spans.

**Why DELTA temporality for metrics?**
Each export says how much was added since the last one, so adding up the
points in a time window gives the total for that window.

**Did you need an OpenTelemetry Collector?**
No. BugSense itself receives OTLP, like a collector would. In a company, a
collector could send one copy to Huawei AOM/APM and one to BugSense.

**What bug did you find while building it?**
The trace broke between services. Python's urllib sends the header as
`Traceparent` with a capital T, and OpenTelemetry looked for `traceparent`.
Reading the headers in lower case fixed it.

---

## Phase 7 — AI diagnosis with tools

**What I built:** a **"Find probable cause"** button on every incident. An
investigator calls **tools** to collect evidence, then gives the probable
cause, the root service, a confidence, the evidence and suggested fixes.

**The 10 tools (all read-only):**

| Tool | Question it answers |
|---|---|
| `list_incidents` | Which incidents are there? |
| `get_incident` | What is in this incident? |
| `get_error_timeline` | Which service failed **first**? |
| `search_logs` | Find logs by text, severity, service, error type, request ID, trace ID, time |
| `get_service_status` | Is the process running, crashed, in a crash loop? Health? Restarts? |
| `get_service_metrics` | Telemetry: requests, error rate, latency, CPU, memory |
| `get_metric_series` | One metric over time: when did it change? |
| `search_traces` | Find the failed or slow requests |
| `get_trace` | Follow one request hop by hop |
| `rank_root_causes` | Which service did the failure **start** in? (Phase 8) |

**"All tool parameters completely implemented" (professor's feedback):**
every parameter is a field of a **Pydantic model**. That one model:

1. becomes the **JSON Schema** the AI is shown (type, minimum, maximum,
   allowed values, description),
2. **validates** every call: a wrong type, a number out of range or an
   unknown parameter is refused with a clear message (never ignored),
3. is used as a **filter in the database query**, so no parameter is decorative.

The tests call every parameter of every tool and check that it really
changes the result (`backend/tests/test_tools.py`). The **Tools** page builds
a form from the same schema, so the examiner can try any tool.

**Two engines, same tools:**

| | AI engine (`llm`) | Rules engine (`rules`) |
|---|---|---|
| Who picks the tools | The AI model, by itself | A fixed order in Python |
| Model | `openai/gpt-oss-20b` on Groq (free tier), changeable | none |
| Cost | Small: tokens are counted and shown | Zero |
| When | A key is set (`LLM_API_KEY`) | No key, or the AI fails |

**How the AI agent works (the loop):**

1. BugSense first builds a **case file** itself, with four tools: the
   incident and its first errors, which service failed first, the process
   status (demo shop only) and a telemetry summary (error rate, p95 latency).
2. It sends the model the instructions, the case file, and only the
   **follow-up tools** that fit this incident (for example, no telemetry tools
   for a dataset without telemetry).
3. The model answers, for example, "call `search_logs` with service=shop-db".
4. BugSense validates the parameters, runs the tool, and sends back the result
   (cut to 2,000 characters). If a parameter was wrong, the model sees the
   error and corrects itself.
5. At most 4 rounds, then the model must give its final answer as JSON:
   cause, root service, confidence, evidence, fixes, limitations.
6. If the free tier says "too many tokens this minute", BugSense waits and
   tries again (up to 2 minutes), or falls back to the rules in `auto` mode.

**How the rules engine decides:**

- configuration error in the logs → "refuses to start because of an invalid
  configuration"
- crash-loop events + a stack trace → "crashes during start-up (the exception)"
- errors that **name another service** ("connection to shop-db failed") →
  follow the chain to its end; if that service is stopped → it is the root;
  if callers time out and it is slow → "responding too slowly"
- otherwise → the earliest error is the starting point (low confidence)

**Results (measured, real AI on Groq's free tier):**

| | Rules | AI |
|---|---|---|
| 4 live scenarios, right root service | 4 of 4 | 4 of 4 |
| Time | under 25 ms | 6–70 s (mostly waiting for the free limit) |
| AI tokens | 0 | 6.6–16.7 K, average 11.8 K |
| Hadoop network failure | missed (earliest error only) | found "ERROR IN CONTACTING RM" ×147 and NoRouteToHost; partly right (named the ResourceManager, not the network) |

**Why the case file?** The free tier allows 8,000 tokens per minute. When the
AI fetched everything itself, each step resent the whole conversation and one
diagnosis went over the limit. Gathering the basics first cut the tokens and
the number of AI rounds.

> "The AI never sees raw log files. It asks for exactly the facts it needs
> through tools, and every fact in its answer names the tool it came from. If
> there is no AI, the rules use the same tools, so BugSense always gives an
> answer, for free."

### Likely questions

**What is "tool calling"?**
The model does not run code. It replies with the name of a tool and the
parameters it wants. BugSense checks them, runs the tool, and gives the
result back to the model.

**Why tools instead of pasting the logs into the prompt?**
A big incident has hundreds of thousands of characters of logs. Tools
return small, exact facts: on Hadoop, 175 K characters became 9 K of evidence (18.7× smaller).
Smaller input means cheaper, faster, and less made-up text.

**Can the AI break something?**
No. Every tool only reads. Suggested fixes are text for the developer.

**Why a free, small model?**
Cost: the evidence is small, so a small model is enough. The model is a
setting, so a Huawei-hosted model could replace it.

**How do you stop the AI from cheating in the demo?**
The demo fault ("crash", "slow") is never written into the logs, and the
status tool hides it. The investigator must find the cause from evidence.

**What if the AI is down or the free limit is reached?**
In `auto` mode BugSense falls back to the rules and says so in a note.

**What went wrong while testing the AI, and how did you fix it?**
Three things. (1) Too many tokens for the free tier: fixed with the case
file. (2) It blamed the slow API on a "crash" because it misread a planned
restart: fixed by putting the p95 latency in the case file. (3) Monitor events
from an earlier problem misled it: the status tool got a `since` parameter.
Also, on Hadoop the model asked about a service the status tool does not
know, and the provider refused the call: now BugSense only offers tools that
fit the incident, and tells the model when a call was refused.

**Does the AI give the same answer every time?**
No, a language model varies a little between runs. That is why BugSense shows
the evidence, so the engineer can check it, and why the rules engine exists
as a repeatable baseline.

**Why is the diagnosis linked to the first log, not the incident id?**
Detection rebuilds open incidents, which can change their id. The first log
of an incident stays the same, so earlier diagnoses are found again.

---

## Phase 8 — Root cause ordering

**The problem:** an incident lists every service that failed, but most of
them are only victims. When the database stops, shop-api fails because it
cannot reach the database, and shop-web fails because shop-api returns errors.
The database itself writes **nothing**, because it is stopped.

**What I built:** on every incident page, a card **"Where did it start?"**:
the services ranked from **probable origin** to **affected**, with points and
the reason for each point, the **chain** of how the failure spread, and one
failed request step by step. It is also the 10th tool, and part of the AI's
case file.

**The evidence, and the points it gives:**

| Evidence | Points | Plain meaning |
|---|---|---|
| Failed first in the requests | up to 50 | Logs with the same request ID are one request. Who failed first in it? |
| Named by other services' errors | up to 25 | "connection to **shop-db** failed": the error points at shop-db |
| Deepest failing step in traces | up to 10 | In a failed trace, the innermost failing step is where it began |
| Earliest error of the incident | 15 | Who had the first error at all |
| Process monitor saw it stop or crash | 10 | A planned restart does not count |

**How a silent service gets found:** in each failed request, shop-api fails
first, but its error says "connection to shop-db failed". So shop-db is put
in front: it becomes the origin of that request, even with no logs of its own.

**Results:** all 4 live scenarios rank the true origin first (3 with high
confidence, the slow API with medium). Database down: shop-db 95 points, chain shop-db → shop-api (15×)
→ shop-web (14×). On datasets without request IDs, only the earliest error is
known, so it honestly says "low confidence".

> "An incident has a cause and its victims. Phase 8 separates them. For every
> failed request it checks which service failed first, and whether that error
> names another service. It adds evidence from traces and the process monitor,
> gives points with reasons, and draws how the failure spread. In the database
> scenario it ranks shop-db first although shop-db wrote no logs at all."

### Likely questions

**Why points and not machine learning?**
Every point has a reason the engineer can check. A learned model, like GRLIA,
needs failure history and cannot explain its answer.

**How is this related to GRLIA?**
GRLIA learns how failures cascade from past failures. BugSense sees the cascade
directly in one incident's requests and traces, without history.

**What if there are no request IDs?**
Then only the order in time and the named services are left. The ranking still
gives a starting point, but marks it "low confidence".

**Why does the slow API only get medium confidence (58 vs 42 points)?**
When a service is slow, the caller gives up first: shop-web logs its timeout
before shop-api finishes, so shop-web "failed first" in 6 of 11 requests. But
shop-web's errors name shop-api ("did not answer"), and shop-api is the
deepest failing step in all 11 failed traces, so shop-api still comes first.
Lesson: for slowness, traces are better evidence than the order of logs.

---

## Login and deployment

**Login:** every feature now needs a signed-in user. On the first visit
BugSense asks to create the **owner account**; after that, sign-up is closed
(unless `ALLOW_SIGNUP=true`), so strangers cannot use it or spend the AI
quota once it is online.

| Part | How it works |
|---|---|
| Passwords | Never stored. Only a **scrypt hash** with a random salt (slow on purpose, so stolen hashes are hard to guess) |
| Token | After sign-in the browser gets "user id . expiry . signature". The signature uses `SECRET_KEY`, so the token cannot be changed or forged. It lasts 7 days |
| Every request | Sends "Authorization: Bearer <token>"; a missing or wrong token gets 401 |
| OpenTelemetry | Programs are not people: they use a separate `INGEST_TOKEN` |

**Deployment:** on **Render**, from GitHub, with no Docker. `render.yaml`
(a "Blueprint") creates three parts: the backend (Python), the frontend
(static files) and PostgreSQL. Secrets (`SECRET_KEY`, `INGEST_TOKEN`, the
Groq key) live in Render's settings, never in GitHub. Every `git push`
deploys the new version. Guide: `DEPLOY.md`.

### Likely questions

**Why not store the password and compare it?**
If the database leaked, every password would leak. With a salted scrypt hash,
the password cannot be read back, and guessing is slow.

**Why does a token need a signature?**
Otherwise anyone could write "user 1" into a token and become the owner.
Only the server knows `SECRET_KEY`, so only the server can make valid tokens.

**Why is sign-up closed after the first account?**
Once BugSense is on the internet, anyone could create an account, delete
logs or use up the free AI quota.

**Why Render?**
It builds from GitHub on its own servers (no Docker on my laptop), has free
plans, and one file (`render.yaml`) describes the whole setup.

---

## Research comparison (Huawei only — professor's feedback)

The professor asked to research **one company, Huawei**, and not Microsoft.
The comparison uses one paper. Full details: `RESEARCH.md`. The pitch:
`PITCH.md`.

| Paper | Huawei team | Venue | Matches |
|---|---|---|---|
| GRLIA: Graph-based Incident Aggregation | Huawei Cloud | IEEE/ACM ASE 2021 | Grouping incidents (Phase 5) |

**What to say in one minute:**

> "I studied Huawei. GRLIA, from Huawei Cloud at ASE 2021, groups the many
> incidents caused by one failure by learning how failures cascade between
> services, using a graph model trained on past failures and metrics. It
> needs that history and cannot say why it grouped two incidents. BugSense
> groups by time with stated reasons, needs no training, and sees the cascade
> directly in OpenTelemetry traces. It then goes one step further than GRLIA:
> it finds the probable cause with investigation tools, which GRLIA leaves to
> the engineers. And it plugs into OpenTelemetry, which Huawei Cloud's AOM
> and APM already accept."

### GRLIA (Huawei Cloud)

- **They did:** grouped incidents from one failure with a graph model trained
  on past cascades and metrics (KPIs). Real Huawei Cloud data; deployed.
- **Limits:** needs history and metrics, gives no reason for a grouping, and
  is an internal company system.
- **BugSense:** 10-minute time bursts with the reason shown, no training,
  traces show the cascade (web → api → db and the failing hop), and Phase 7
  explains the probable cause.

### Likely questions

**Why only one paper?**
The professor asked for one company, Huawei. GRLIA is Huawei Cloud's paper on
the same problem as BugSense's grouping, so it is the direct comparison.

**Which part of BugSense goes beyond GRLIA?**
Explaining the incident: GRLIA stops at grouping. BugSense also finds which
service failed first, follows the failure across services, and gives a
probable cause with evidence.

**Is BugSense better than GRLIA?**
No. GRLIA works at huge scale on private data. BugSense is an open, small
tool that explains itself and works from the first day, without history.

**Why not use deep learning like GRLIA?**
It needs a history of past failures and gives no reason for its result.
BugSense uses rules first, so every decision can be explained and checked.

---

## The pitch to Huawei (cost and workflow)

Full text: `PITCH.md`.

**Workflow:** Huawei's services already send OpenTelemetry to AOM/APM. An
OpenTelemetry Collector can send a second copy to BugSense, with no change to
the services. The engineer gets a grouped incident, the service that failed
first, the failing hop in a trace, and a probable cause with evidence.

**Cost-effectiveness, in four points:**

1. **No training, no GPU.** Rules plus a general, free model.
2. **Rules first:** clear cases cost nothing (0 tokens, under 25 ms).
3. **The AI sees evidence, not logs:** 7–13 K characters whatever the size
   of the incident, so AI cost does not grow with log volume.
4. **Runs as small containers** on Podman (about 1.2 GB of memory in total), or as one process on a laptop.

> "BugSense gives engineers explanations they can check, needs no training
> data, keeps the AI's input small, plugs into OpenTelemetry which Huawei
> Cloud already uses, and costs almost nothing per incident."

**Proposed pilot:** 4 weeks; one service; label 20 past incidents; measure
root-service accuracy, seconds and tokens per diagnosis, and time to the first
hypothesis.

---

## Podman, the backup UI, and making it easy to pitch (professor's feedback)

The feedback: show how BugSense helps developers and companies (time and
cost), make every page easy to understand, explain live monitoring with
telemetry clearly, and **deploy on Podman, fully containerised, with a backup
container for the UI**.

### What a container is (easy words)

A **container** is a program packed together with everything it needs
(Python, libraries, settings), so it runs the same on any computer. An
**image** is the packed recipe; a container is one running copy of it.

**Podman** is the tool that runs containers. It does the same job as Docker
but needs no always-running background service ("daemonless"), and runs
containers as a normal user, not as administrator. On a Mac it uses a small
Linux virtual machine; ours is limited to 2 CPUs and 2 GB, so the laptop stays
fast.

### The five containers

| Container | Job |
|---|---|
| gateway | The front door (port 8080). `/api/...` goes to the API, pages go to the UI |
| web-main | The main UI |
| web-backup | A second copy of the same UI |
| api | FastAPI backend, plus the demo shop sending live OpenTelemetry to it |
| db | PostgreSQL; data kept in a volume, so it survives restarts |

`compose.yaml` describes all five; `./podman.sh up` starts them.

### How the backup UI works

The gateway is **nginx** (a fast web server). In its config web-main is the
normal server and web-backup is marked `backup`. If web-main does not answer
within 2 seconds, nginx sends the **same request** to web-backup, so the user
sees no error. For the next 10 seconds it keeps using the backup, then tries
web-main again. This is called **failover**.

The top bar shows a pill: green **UI · web-main**, or yellow
**Backup UI · web-backup**. Each UI container answers `/served-by` with its
name; the page asks every 3 seconds.

**Demo:** `./podman.sh failover`, or `podman stop bugsense-web-main`, reload
the page (it still works, the pill is yellow), then
`podman start bugsense-web-main`.

Also: every container has `restart: always` (Podman restarts it if it
crashes) and a **health check** (a small command Podman runs to see whether it
still works).

### Safety in the containers

- Secrets are never inside an image: `.containerignore` leaves out `.env`;
  `./podman.sh` makes random secrets in a private `.env` file.
- The API container runs as a normal user, not root.
- The UI image has no Node.js in it: Node only builds the files, then nginx
  serves them (a "multi-stage build"), so the image is small.
- Fixed addresses inside the container network (10.90.7.x), so a container
  that restarts comes back at the same address and the gateway finds it.

### Live monitoring with telemetry, explained on the page

The Telemetry page now shows:

- A **LIVE** badge that pulses while data keeps arriving, and "updated 3 s ago".
- One sentence for everything: "All 3 services are healthy" or
  "1 of 3 services need attention: shop-api".
- A strip of four steps: programs run → they report over OpenTelemetry →
  BugSense stores traces, metrics, logs → the page reads them every 5 s.
- On each service card, a plain sentence: "Healthy: 0 of 120 requests
  failed; most answered within 40 ms", or "Problem: 34 of 100 requests failed".
  Red uses the same rules as the alerts: 1 in 5 requests failing, or the
  slowest 5% taking 1 second or more.

> "Telemetry is like a car's dashboard: the programs report their own speed
> and warning lights while they run. BugSense reads that dashboard every five
> seconds and tells you in one sentence which service is in trouble."

### Telemetry for uploaded logs (on the same page)

Uploaded logs get telemetry too: BugSense calculates it from the lines
(logs per minute and error share for every service; requests, latency and
traces when lines share a request ID and say "took 120 ms").

- Uploaded logs are usually from the past, so the page **opens on "All data"
  by itself** for them ("These logs are from the past, so all their data is
  shown"). Live data opens on the last 15 minutes.
- The badge says **FROM UPLOADED LOGS** instead of LIVE, and the 4-step strip
  explains how the numbers were calculated.
- Logs with no request IDs (for example Apache) show log lines, logs per
  minute and error logs, with a chart of logs per minute; the page explains
  why there are no traces instead of showing empty boxes.

> "If my logs have request IDs and durations, BugSense rebuilds the requests
> as traces, the same as live telemetry. If they don't, it still shows each
> service's activity and error share over time."

### Easy to understand: the page guides

Every page starts with an **"In simple words"** box: what the page is for,
how to use it in three steps, the words it uses (trace, p95, incident...),
and why it helps. It folds away, and the browser remembers. On the Tools page,
each tool shows the plain question it answers, for example
`get_error_timeline`: "Which service failed first?".

### The Why BugSense page (the pitch inside the app)

- **For developers / for the company / for trust:** three short cards.
- **Huawei Cloud workflow:** services → OpenTelemetry Collector → AOM/APM
  *and* BugSense. Then each step of one incident, today vs with BugSense,
  with example minutes (95 vs 12).
- **Savings calculator:** the company types its own numbers (incidents per
  month, engineers, minutes, hourly cost, AI price). Example: 30 incidents ×
  2 engineers × 83 minutes saved = **83 engineer hours a month**, about
  **$3,300 a month** at $40 an hour. AI cost: 0 on the free tier, about $0.05
  a month at an example price of $0.30 per million tokens.
- **Cost table:** manual vs a large AI reading raw logs vs BugSense.
- **Measured results** and the **4-week pilot**.

**Be honest when asked:** "The minutes are assumptions to show the size of
the saving. What we measured is BugSense's part: under 25 ms for rules, about
10 seconds and 12 K tokens for the AI, and correct root service in 4 of 4
faults. The pilot would measure the engineers' real minutes."

### Online for others: Oracle Cloud Always Free

The same five containers run on a free cloud server: Oracle Cloud "Always
Free", an Ampere (ARM) server with Ubuntu. One script
(`containers/server-setup.sh`) installs Podman, opens port 8080, makes the
containers start again after a reboot, asks for the AI key, and starts
everything. The link is `http://<server IP>:8080`. Guide: `SERVER.md`.

- **Free:** Always Free includes up to 4 ARM CPUs and 24 GB; BugSense needs
  about 1.2 GB. The account is never charged unless upgraded.
- **ARM works** because every base image (Python, Node, nginx, PostgreSQL)
  is published for ARM as well as Intel.
- **Two firewalls:** Oracle's website (Security List rule for port 8080) and
  the server's own (`iptables`); the script opens the second.
- **Survives reboots:** `restart: always` plus Podman's `podman-restart`
  service, with "linger" so it runs without anyone logged in.
- **Updates:** push from the Mac, then `./podman.sh update` on the server
  (git pull + rebuild what changed; the data stays in its volume).
- **Guests:** `./podman.sh signup on`, then `off` again.

> "BugSense runs in Podman containers on a free Oracle Cloud server, the same
> setup as on my laptop, with a backup UI. Anyone can open the link."

### Likely questions

**Why a backup for the UI and not for the API?**
The UI is what people look at, and it holds no data, so two copies are
simple. The API runs the demo shop and its background jobs; two copies would
start the shop twice. A second API would need those jobs moved out first
(future work).

**What happens to data if a container stops?**
The data is in PostgreSQL's volume, not in the container, so nothing is lost.

**Can it run on Huawei Cloud?**
Yes: the same images run on any container platform, for example Huawei
Cloud's container service; only the addresses and secrets change.

---

## Design decisions I can defend

**Why Podman and not Docker?**

> "Docker made my laptop hang. Podman runs the same containers without a
> background service and without root, and I limit its virtual machine to
> 2 CPUs and 2 GB. For quick development I can still run everything as plain
> local processes."

**Why plain CSS and not Tailwind?**
There is nothing extra to install or explain. Every style lives in one file,
`index.css`, with the colours defined once at the top.

**Why is AI not used everywhere?**
Parsing and grouping logs can be done reliably with normal code, which is
faster, free and predictable. AI is used only where it adds value: explaining
the root cause in plain language. And even there, a rules engine can do the
job without AI.

**Why an OpenAI-compatible API and not one company's SDK?**
Most providers (Groq, many others, and self-hosted models) offer the same chat
API, so changing the model is a setting, not new code. No extra library is
needed: BugSense calls it with httpx.

**Why are wrong parameters an error and not ignored?**
If `limit=0` or a typo like `servce=api` were silently ignored, the AI (or a
person) would get a wrong answer without knowing. A clear error lets the AI
correct itself.

---

## How to run the demo

1. Open the **Postgres** app and click **Start**.
2. Terminal 1 — backend:
   ```bash
   cd ~/Desktop/BugSense/backend
   source venv/bin/activate
   uvicorn app.main:app --reload
   ```
3. Terminal 2 — frontend:
   ```bash
   cd ~/Desktop/BugSense/frontend
   npm run dev
   ```
4. Open http://localhost:5173.

If port 8000 is already used by another program, use any free port, for
example `uvicorn app.main:app --reload --port 8010` and
`VITE_API_URL=http://localhost:8010 npm run dev` instead.

For the AI engine, put a free Groq key in `backend/.env` as
`LLM_API_KEY=...`. Without it, the rules engine is used.

**Things to show the examiner now (Phase 7 and telemetry):**

- **Services → Start all.** Each card shows live OpenTelemetry numbers:
  requests per minute, error rate, p95 latency, CPU.
- **Telemetry:** the service cards, the chart (try `latency` with `p95`, then
  `process.cpu.time` with `rate`), and the **Traces** table. Click a trace:
  the waterfall shows shop-web → shop-api → shop-db and their logs.
- **Services → Database goes down,** wait 15 seconds, **See incidents,** open
  the incident, click **Find probable cause.** Answer: shop-db is not
  running, high confidence, with evidence from logs, process status, a
  telemetry alert and a trace. Click **Show tool calls.**
- Repeat with **Slow API**: the Telemetry page turns p95 red; the diagnosis
  says shop-api is too slow (p95 about 2,300 ms).
- **Tools:** pick `search_logs`, set `min_severity=ERROR` and `service=shop`,
  run it. Then set `limit` to 0: a clear error. Click **Schema the AI sees.**
- **Logs → More filters:** request ID, trace ID, time range, paging.

**Earlier phases:**

- **Services:** click **Start all**. All three cards turn green and healthy.
  Run **Database goes down**: shop-db stops, shop-api turns unhealthy, and
  errors appear. Click **See incidents**: one incident. Then **Recover**,
  **Clear demo logs**, and run **Crash loop**: watch the restart count climb,
  "Crash loop" appear, and BugSense give up after 6 crashes.

- **Incidents:** paste `samples/checkout-outage.log` (or upload it). Open
  **Incidents**: one CRITICAL incident, "FATAL: the database system is
  shutting down in postgres (+2 more services)". Open it: why it is CRITICAL,
  the 3 services involved, and the evidence in time order. Click **Mark as
  resolved**.
- Pick **Hadoop MapReduce** in the top bar: 960 problem logs become one
  CRITICAL incident with 152 errors across 8 services.
- Stream a dataset live and watch incidents appear and grow on the Overview.

- Go to **Datasets**, choose 10/s and click **Stream live** on Hadoop
  MapReduce. The Overview fills up live: the counters rise, the columns
  grow, and errors appear in the dark card.
- Open **Datasets → Hadoop MapReduce → View lines**: the raw file next to
  the parsed fields. Search `NoRouteToHost` to find the network failure.
- Click **Loghub CSV**: the researchers' official CSV, every row marked
  ✓ Yes. Point at the Verification card: 2,000 / 2,000 match.
- Download **Loghub CSV** and **BugSense CSV** and open both in Excel.
- Pick **Apache Web Server** in the top bar: 2,000 real logs, 595 errors.
- Pick **OpenStack Nova**, open Logs and search `req-`: real request IDs.
- The dashboard with Backend **Online** and Database **Connected**.
- On the Logs page, upload `samples/payment-errors.jsonl`: five logs appear
  with coloured severity badges.
- Upload `samples/checkout-outage.log`: every line gets its severity,
  service and error type filled in by the parser.
- Upload `samples/buggy-code-errors.log`: real crash output from two buggy
  programs, each error with its stack trace.
- On the Dashboard, show **Top error types** and the **Errors** count.
- Type `503` in the search box, or choose **ERROR** in the severity filter.
- Click any row to see the full raw log.
- Try to upload a `.py` file: it is rejected.
- Click **Stop** in the Postgres app and refresh: Database turns
  **Unavailable** while the backend stays online.
- http://localhost:8000/docs — the automatic API documentation.
  (Use port 8001 if you started the backend there.)

---

## Quick glossary

| Word | Simple meaning |
|---|---|
| Frontend | The part the user sees in the browser |
| Backend | The server that does the work |
| API | The way the frontend asks the backend for something |
| Endpoint | One URL of the API that does one job |
| JSON | A simple text format for sending data |
| Port | A numbered door on the computer that a program listens on |
| localhost | "This computer" |
| CORS | The browser rule about which website may call which server |
| ORM | A tool that lets you use database tables as Python classes |
| Primary key | The unique ID of a row |
| Foreign key | A column that links to a row in another table |
| Environment variable | A setting kept outside the code |
| OpenTelemetry (OTel) | The standard way for programs to send traces, metrics and logs |
| OTLP | The protocol OpenTelemetry uses to send that data |
| Span / trace | One step of a request / all the steps of one request |
| p95 latency | 95% of requests were at least this fast |
| Tool calling | The AI asks for a tool with parameters; the app runs it |
| JSON Schema | A description of what parameters are allowed (types, limits) |
| Zero-shot | Using an AI model without training it on your own data |
| Token | A piece of a word; AI providers count (and charge) by tokens |
| Log | A line of text a program writes about what it is doing |
| Ingestion | Taking data into the system |
| Raw log | A log kept exactly as it arrived |
| Structured log | A log sent as JSON with named fields |
| Severity | How serious a log is: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| Stack trace | The list of code lines a program was running when it failed |
| Parser | Code that reads text and pulls structured information out of it |
| Regex | A pattern that describes what a piece of text looks like |
| Rule-based | Following fixed rules written by the programmer, not learned ones |
| Normalise | Turn different spellings of the same thing into one |
| Request ID | A label shared by every log from one user request |
| Schema | A description of what shape some data must have |
| Status code | A number in the reply that says whether the request worked |
| Route | The code that handles one endpoint |
| Dataset | A collection of real data used for testing or research |
| Loghub | A public collection of real system logs used in research |
| Replay | Sending recorded data again, in real time, as if it were live |
| Polling | Asking the server for new data again and again at a fixed interval |
| Thread | A second line of work running inside the same program |
| Bento grid | A layout of different-sized boxes that fit together |
| Incident | One problem, made of all the related failures it caused |
| Burst | Problems that happen close together in time |
| Message template | A message with its numbers and IDs replaced by `<*>` |
| Alert fatigue | Ignoring alerts because there are too many of them |
| Process | A program that is running, with its own process ID (PID) |
| Supervisor | A program that starts other programs and restarts them if they crash |
| Exit code | The number a program ends with: 0 = fine, anything else = failed |
| Crash loop | Crashing again right after every restart |
| Back-off | Waiting longer before each new retry |
| Health check | A page a service offers to say whether it can do its job |
| Incident | A group of related errors treated as one problem |
| Container | A program packed with everything it needs, so it runs the same anywhere |
| Image | The packed recipe a container is started from |
| Podman | The tool that builds and runs containers, without a background service or root |
| Compose file | One file (`compose.yaml`) describing all the containers and how they connect |
| Volume | Storage kept outside a container, so data survives when it stops |
| Gateway | The one front door that sends each request to the right container |
| Failover | Switching to a backup automatically when the main one stops answering |
| Multi-stage build | Build with big tools in one step, keep only the result in the final image |
