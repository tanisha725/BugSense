# BugSense

AI-Powered Intelligent Debugging & Incident Analysis Platform.

BugSense will analyze application logs, errors and container events, group
related failures into incidents, and help developers find the probable root
cause. The project is built phase by phase.

**Current status: Phase 8 (root cause ordering), on top of AI diagnosis with
tools (Phase 7) and OpenTelemetry monitoring.** Logs can be pasted, uploaded, imported from six real-world
datasets, streamed in live, or received over OpenTelemetry. Related failures
are grouped into incidents. BugSense runs a three-service demo shop and
monitors it with **OpenTelemetry** traces and metrics (requests, error rate,
latency, CPU, memory). For any incident it finds the **probable cause** with
10 investigation tools, used by an AI agent (a free model) or by a rule-based
investigator when no AI key is set, and ranks the services from the one where
the failure started to the ones that only failed after it.

## Features so far

- **Runs on Podman:** every part in its own container (gateway, main UI,
  **backup UI**, API, PostgreSQL), started with `./podman.sh up` and opened at
  http://localhost:8080. If the main UI container stops, the gateway serves
  the backup and the top bar shows which one is serving. Guide:
  [PODMAN.md](PODMAN.md)
- **Online for free:** the same Podman setup runs on an Oracle Cloud Always
  Free server with one script (`containers/server-setup.sh`). Guide:
  [SERVER.md](SERVER.md)
- **Easy to understand:** every page starts with an "In simple words" guide
  (what it is for, three steps, the words it uses). Telemetry shows a LIVE
  badge and one plain sentence per service ("Healthy: 0 of 120 requests
  failed..."). Each tool shows the question it answers
- **Why BugSense page:** the pitch inside the app: Huawei Cloud workflow
  before and after, and a savings calculator (engineer hours, money, AI cost)
- **Login:** every feature needs a signed-in user. The first account becomes
  the owner, then sign-up closes (unless `ALLOW_SIGNUP=true`). Passwords are
  stored as scrypt hashes; sign-in tokens are signed with `SECRET_KEY` and
  last 7 days. OpenTelemetry senders use a separate `INGEST_TOKEN`
- **Public link on Render:** `render.yaml` builds the same api and web
  container images on Render (free), plus a database, so anyone can try
  BugSense at one https link. Step-by-step guide: [DEPLOY.md](DEPLOY.md)
- **Root cause ordering (Phase 8):** every incident shows "Where did it
  start?": its services ranked from probable origin to affected, with points
  and reasons. Evidence: who failed first in each request (request IDs and
  trace IDs), which service other services' errors name ("connection to
  shop-db failed"), the deepest failing step in failed traces, the earliest
  error, and process crashes. It also shows how the failure spread
  (shop-db → shop-api → shop-web) and one failed request step by step
- **AI diagnosis (Phase 7):** "Find probable cause" on any incident. An AI
  agent calls 10 read-only investigation tools (incident, error timeline, log
  search, process status, telemetry metrics, metric series, trace search,
  trace detail, incident list, root cause ranking) and answers with the root service, confidence,
  evidence and suggested fixes. Without an AI key a rule-based investigator
  uses the same tools. Every tool call, the tokens used and the evidence size
  are stored and shown
- **Tools page:** run any tool by hand with any parameters. Every parameter is
  typed and limited (JSON Schema); a wrong or unknown parameter is refused,
  never ignored
- **OpenTelemetry monitoring:** BugSense is an OTLP/HTTP receiver
  (`/v1/traces`, `/v1/metrics`, `/v1/logs`, protobuf or JSON). The demo shop
  is instrumented with the OpenTelemetry SDK: one checkout is one trace across
  shop-web → shop-api → shop-db. The Telemetry page shows request rate, error
  rate, latency p50/p95/p99, CPU and memory per service, any metric over time,
  and each request as a waterfall. High error rate or latency raises an alert
  that joins the incident
- **Telemetry from uploaded logs:** for logs that are uploaded, pasted or
  imported, BugSense calculates telemetry from the logs themselves: traces
  from shared request IDs, latency from durations written in the text ("in
  19 ms", "took 2.3 s", OpenStack's "time: 0.27"), and logs per minute and error
  share for every service. It is marked "From logs" (measured data is marked
  "Measured"), is recalculated after every upload, and the Telemetry page's
  "All data" view shows data from the past
- Incident detection: problems close together in time (10-minute gap) are
  grouped into one incident, rated CRITICAL / HIGH / MEDIUM / LOW by clear
  rules, with the reason shown; incidents can be resolved and kept as history
- Service monitoring (replaces Docker): BugSense starts the demo shop in
  `demo-services/`, restarts crashed services with back-off, detects crash
  loops (3 crashes in 60 s), checks `/health` every 3 s, stores everything
  they print, and records events as logs so crashes join incidents. Four
  one-click failure scenarios: database down, crash loop, slow API, bad config
- Overview dashboard: health, counts, open incidents, error and warning
  rates, activity over time, severity breakdown, top error types, busiest
  services, active incidents
- Real-world data: six Loghub datasets (Apache, OpenSSH, HDFS, ZooKeeper,
  Hadoop, OpenStack), 12,000 real log lines - see `backend/datasets/README.md`
- Verified: BugSense's parser agrees with Loghub's official CSV on every line
  of all six datasets (message text, clock time and severity level), shown on
  each dataset's page; the CSVs can be viewed and downloaded
- Live mode: a dataset can be replayed a few lines per second, and the
  dashboard updates every 3 seconds
- Projects: each dataset is its own project, chosen in the top bar
- Three ways to send your own logs: paste text, structured JSON, file upload
- Rule-based log parser (plain Python, no AI) that knows 6 real-world formats
  plus common application formats
- Logs page with text search and severity / service filters

## Research background and pitch

[RESEARCH.md](RESEARCH.md) compares BugSense with **GRLIA** from Huawei Cloud
(incident grouping, IEEE/ACM ASE 2021), describes Huawei Cloud's monitoring
products, and gives the evaluation so far.

[PITCH.md](PITCH.md) pitches BugSense to Huawei Cloud: how it fits the
workflow (OpenTelemetry, AOM/APM), the time developers save, and why it is
cost-effective. The same content is on the **Why BugSense** page in the app.

## Architecture

On Podman ([PODMAN.md](PODMAN.md)):

```
Browser -> gateway :8080 -+-> web-main   (UI)
                          +-> web-backup (UI, used when web-main is down)
                          +-> api :8000  -> db (PostgreSQL)
                                ^   demo shop inside the api container,
                                +-- sending OpenTelemetry to it
```

Local development:

```
Browser -> React (port 5173) -> FastAPI (port 8000) -> PostgreSQL (port 5432)
                                    ^       |
     demo shop (OpenTelemetry SDK) -+       +-> AI provider (optional, free tier)
```

## Stack

- Frontend: React + Vite, plain CSS, hand-made SVG/HTML charts (no chart library)
- Backend: Python + FastAPI
- Database: PostgreSQL (via Postgres.app), accessed with SQLAlchemy
- Containers: Podman (`compose.yaml`, `containers/`); for development it also runs as plain local processes

## Project structure

```
BugSense/
├── frontend/            React app
│   └── src/
│       ├── components/  Reusable UI pieces (TopNav, charts, cards, LogTable, DiagnosisPanel, TraceWaterfall)
│       ├── pages/       Full screens (Dashboard, Incidents, Services, Telemetry, Logs, Datasets, Tools, Why BugSense)
│       └── services/    Code that calls the backend
├── backend/             FastAPI app
│   ├── app/main.py      API entry point
│   ├── app/database.py  PostgreSQL connection
│   ├── app/models.py    Tables: users, projects, logs, incidents, spans, metric_points, diagnoses
│   ├── app/schemas.py   Shapes of API requests and replies
│   ├── app/routes/      API endpoints, one file per feature (logs, incidents, monitoring, projects, datasets, telemetry, tools)
│   ├── app/services/    Logic used by the routes (parser, incident detector, monitor, otlp, telemetry, tools, diagnosis, ...)
│   ├── datasets/        Real-world log files from Loghub
│   └── tests/           Pytest tests
├── demo-services/       A three-program demo shop, instrumented with OpenTelemetry (otel.py)
├── containers/          Containerfiles and nginx configs for Podman
├── compose.yaml         The five containers (see PODMAN.md)
├── podman.sh            ./podman.sh up | status | failover | logs | down
├── samples/             Example log files to upload
└── .env.example         Example environment variables
```

## Setup (local)

Database, once:

1. Install [Postgres.app](https://postgresapp.com), open it and click
   **Initialize** (later: **Start**).
2. Create the database:

```bash
/Applications/Postgres.app/Contents/Versions/latest/bin/createdb bugsense
```

The tables are created automatically when the backend starts.

Backend, in one terminal:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend, in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, go to **Datasets** and import or stream one.

**If port 8000 is busy** (another app is using it), run the backend on any
free port (for example 8010) and tell the frontend:

```bash
uvicorn app.main:app --reload --port 8010          # in backend/
VITE_API_URL=http://localhost:8010 npm run dev     # in frontend/
```

The demo shop sends its OpenTelemetry data to whichever port the backend is
on (it is taken from the request that starts the shop).

**AI diagnosis (optional, free):** create a free key at
[console.groq.com](https://console.groq.com) and put it in `backend/.env`:

```bash
LLM_API_KEY=your-key-here
```

Without a key everything works: the rule-based investigator is used. Any
provider with an OpenAI-compatible chat API can be used instead (see below).

## Environment variables

| Variable       | Used by  | Default                 |
| -------------- | -------- | ----------------------- |
| `FRONTEND_URL` | backend  | `http://localhost:5173` |
| `VITE_API_URL` | frontend | `http://localhost:8000` |
| `DATABASE_URL` | backend  | `postgresql+psycopg://localhost:5432/bugsense` |
| `LLM_API_KEY`  | backend  | empty: no AI, the rule-based investigator is used |
| `SECRET_KEY`   | backend  | random at each start (everyone signs in again after a restart); set it when deployed |
| `ALLOW_SIGNUP` | backend  | `false`: only the first account can be created |
| `INGEST_TOKEN` | backend  | empty: anyone may send OpenTelemetry data; set it when deployed |
| `LLM_BASE_URL` | backend  | `https://api.groq.com/openai/v1` |
| `LLM_MODEL`    | backend  | `openai/gpt-oss-20b` (small, free tier, supports tools) |

## API overview

| Method | Path      | Description              |
| ------ | --------- | ------------------------ |
| GET    | `/health` | Checks the backend and database are up (no sign-in needed) |
| GET    | `/auth/status` | Whether an account can be created (no sign-in needed) |
| POST   | `/auth/signup`, `/auth/signin` | Creates an account / signs in; returns a token |
| GET    | `/auth/me` | The signed-in user |
| POST   | `/logs` | Stores one structured JSON log |
| POST   | `/logs/text` | Parses and stores pasted log text |
| POST   | `/logs/upload` | Parses and stores logs from a `.log`, `.txt`, `.json` or `.jsonl` file (max 2 MB) |
| GET    | `/logs` | Lists logs. Filters: `search`, `severity`, `min_severity`, `service`, `error_type`, `request_id`, `trace_id`, `incident_id`, `since`, `until`, `project_id`; plus `order`, `limit` (1–500), `offset` |
| GET    | `/logs/count` | How many logs match the same filters |
| GET    | `/logs/stats` | Counts by severity, top error types, busiest services |
| GET    | `/logs/timeline` | Log counts in equal time slots (`minutes=5` for live view) |
| DELETE | `/logs/{id}` | Deletes one log |
| DELETE | `/logs` | Deletes all logs (of one project with `project_id`) |
| GET    | `/incidents` | Incidents, most serious first (`project_id`, `status` = OPEN, RESOLVED or ALL, `min_severity`, `service`, `limit`, `offset`) |
| GET    | `/incidents/summary` | Open incident counts by severity |
| GET    | `/incidents/{id}` | One incident: reasons for its severity, services, error types, its logs in time order (`log_limit`, `errors_only`) |
| POST   | `/incidents/{id}/diagnose` | Probable cause (`engine` = auto, llm or rules; `max_steps` 1–12) |
| GET    | `/incidents/{id}/diagnoses` | Earlier diagnoses of the incident (`limit`) |
| GET    | `/incidents/{id}/root-cause` | Services ranked from probable origin to affected, with reasons and the failure chain |
| PATCH  | `/incidents/{id}` | Changes the status to `OPEN` or `RESOLVED` |
| POST   | `/incidents/detect` | Runs incident detection again (one project or all) |
| GET    | `/monitor` | Status, health, restarts and events of the demo services |
| POST   | `/monitor/start-all` / `/monitor/stop-all` | Starts or stops the whole demo shop |
| POST   | `/monitor/services/{name}/{action}` | `start`, `stop` or `restart` one demo service (`fault` with restart of shop-api) |
| POST   | `/monitor/scenarios/{key}` | `database-down`, `crash-loop`, `slow`, `bad-config` or `recover` |
| GET    | `/projects` | Projects with their log and error counts |
| GET    | `/datasets` | The real-world datasets that can be imported |
| GET    | `/datasets/{key}` | Dataset viewer: facts about the file and a page of raw lines with their parsed fields (`search`, `offset`, `limit`) |
| GET    | `/datasets/{key}/download` | Downloads the original, unchanged dataset file |
| GET    | `/datasets/{key}/csv` | A page of Loghub's official CSV, each row marked with whether BugSense agrees |
| GET    | `/datasets/{key}/csv/download` | Downloads Loghub's original CSV, unchanged |
| GET    | `/datasets/{key}/parsed.csv` | Downloads BugSense's own parsing result as CSV |
| GET    | `/logs/export` | Downloads stored logs as CSV (same filters as `/logs`; works for live streams) |
| POST   | `/datasets/{key}/import` | Imports a whole dataset as its own project |
| POST   | `/datasets/{key}/stream?speed=5` | Replays a dataset live, `speed` lines per second |
| GET    | `/datasets/stream` | Status of the live replay |
| POST   | `/datasets/stream/stop` | Stops the live replay |
| POST   | `/v1/traces`, `/v1/metrics`, `/v1/logs` | OpenTelemetry (OTLP/HTTP) receiver, protobuf or JSON, gzip allowed |
| GET    | `/telemetry/services` | Per service: requests, error rate, latency p50/p95/p99, CPU, memory (`project_id`, `service`, `window_minutes`, `until`) |
| GET    | `/telemetry/metrics` | Metric names that can be charted |
| GET    | `/telemetry/series` | One metric over time (`metric`, `service`, `window_minutes`, `step_seconds`, `aggregation`, `until`) |
| GET    | `/telemetry/traces` | Recent requests (`service`, `status`, `min_duration_ms`, `window_minutes`, `limit`, `until`) |
| GET    | `/telemetry/traces/{trace_id}` | One request as a span tree, with its logs (`include_logs`) |
| GET    | `/telemetry/range` | First and last moment of a project's telemetry (`project_id`) |
| POST   | `/telemetry/from-logs` | Recalculates a project's telemetry from its logs (`project_id`) |
| GET    | `/tools` | The 10 investigation tools with their parameter schemas |
| POST   | `/tools/{name}` | Runs one tool; the JSON body is its parameters |
| GET    | `/tools/config` | Whether an AI model is set up, and which one |

Interactive API docs: http://localhost:8000/docs

## Testing

```bash
cd backend
source venv/bin/activate
python -m pytest
```
