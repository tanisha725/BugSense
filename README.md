# BugSense

AI-Powered Intelligent Debugging & Incident Analysis Platform.

BugSense will analyze application logs, errors and container events, group
related failures into incidents, and help developers find the probable root
cause. The project is built phase by phase.

**Current status: Phase 6 (Service monitoring)** - logs can be pasted,
uploaded, imported from six real-world datasets, or streamed in live. Each log
is parsed into fields (time, severity, service, error type, request ID, stack
trace) and stored in PostgreSQL. Related failures are grouped into incidents
with a severity, a title and their evidence, shown on a live dashboard.
BugSense also runs a three-program demo shop and watches it like Docker
would: status, health checks, restarts and crash loops.

## Features so far

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

## Research background

[RESEARCH.md](RESEARCH.md) compares BugSense with two IEEE papers from
companies: GRLIA from Huawei Cloud (incident grouping, ASE 2021) and
Microsoft's study of LLMs for root cause analysis (ICSE 2023). It covers what
they did, what BugSense does, what is new, and the evaluation so far.

## Architecture

```
Browser -> React (port 5173) -> FastAPI (port 8000) -> PostgreSQL (port 5432)
```

## Stack

- Frontend: React + Vite, plain CSS, hand-made SVG/HTML charts (no chart library)
- Backend: Python + FastAPI
- Database: PostgreSQL (via Postgres.app), accessed with SQLAlchemy
- Runs as plain local processes (no Docker needed)

## Project structure

```
BugSense/
├── frontend/            React app
│   └── src/
│       ├── components/  Reusable UI pieces (TopNav, charts, cards, LogForm, LogTable)
│       ├── pages/       Full screens (Dashboard, Incidents, Services, Logs, Datasets)
│       └── services/    Code that calls the backend
├── backend/             FastAPI app
│   ├── app/main.py      API entry point
│   ├── app/database.py  PostgreSQL connection
│   ├── app/models.py    Tables: users, projects, logs, incidents
│   ├── app/schemas.py   Shapes of API requests and replies
│   ├── app/routes/      API endpoints, one file per feature (logs, incidents, monitoring, projects, datasets)
│   ├── app/services/    Logic used by the routes (parser, formats, incident detector, monitor, datasets, replay)
│   ├── datasets/        Real-world log files from Loghub
│   └── tests/           Pytest tests
├── demo-services/       A three-program demo shop that BugSense monitors
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

**If port 8000 is busy** (another app is using it), run the backend on 8001
and tell the frontend:

```bash
uvicorn app.main:app --reload --port 8001          # in backend/
VITE_API_URL=http://localhost:8001 npm run dev     # in frontend/
```

## Environment variables

| Variable       | Used by  | Default                 |
| -------------- | -------- | ----------------------- |
| `FRONTEND_URL` | backend  | `http://localhost:5173` |
| `VITE_API_URL` | frontend | `http://localhost:8000` |
| `DATABASE_URL` | backend  | `postgresql+psycopg://localhost:5432/bugsense` |

## API overview

| Method | Path      | Description              |
| ------ | --------- | ------------------------ |
| GET    | `/health` | Checks the backend and database are up |
| POST   | `/logs` | Stores one structured JSON log |
| POST   | `/logs/text` | Parses and stores pasted log text |
| POST   | `/logs/upload` | Parses and stores logs from a `.log`, `.txt`, `.json` or `.jsonl` file (max 2 MB) |
| GET    | `/logs` | Lists newest logs. Filters: `search`, `severity`, `service`, `project_id`, `limit` |
| GET    | `/logs/stats` | Counts by severity, top error types, busiest services |
| GET    | `/logs/timeline` | Log counts in equal time slots (`minutes=5` for live view) |
| DELETE | `/logs/{id}` | Deletes one log |
| DELETE | `/logs` | Deletes all logs (of one project with `project_id`) |
| GET    | `/incidents` | Incidents, most serious first (`project_id`, `status` = OPEN, RESOLVED or ALL) |
| GET    | `/incidents/summary` | Open incident counts by severity |
| GET    | `/incidents/{id}` | One incident: reasons for its severity, services, error types, its logs in time order |
| PATCH  | `/incidents/{id}` | Changes the status to `OPEN` or `RESOLVED` |
| POST   | `/incidents/detect` | Runs incident detection again (one project or all) |
| GET    | `/monitor` | Status, health, restarts and events of the demo services |
| POST   | `/monitor/start-all` / `/monitor/stop-all` | Starts or stops the whole demo shop |
| POST   | `/monitor/services/{name}/{action}` | `start`, `stop` or `restart` one demo service |
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

Interactive API docs: http://localhost:8000/docs

## Testing

```bash
cd backend
source venv/bin/activate
python -m pytest
```
