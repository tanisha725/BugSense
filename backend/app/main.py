"""BugSense backend - the entry point of the FastAPI application."""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app import models  # noqa: F401 - importing registers the tables on Base
from app.database import Base, engine
from app.routes import auth, datasets, incidents, logs, monitoring, projects, telemetry, tools
from app.routes.auth import current_user, ingest_allowed
from app.services import monitor, replay


def is_database_connected():
    """Runs the smallest possible query to see if PostgreSQL answers."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


def add_new_columns():
    """create_all() makes new tables, but never changes a table that already
    exists. Columns added in later phases are added here by hand. (A real
    product would use a migration tool such as Alembic.)"""
    added = [
        ("logs", "trace_id", "VARCHAR(32)"),
        ("spans", "source", "VARCHAR(10) NOT NULL DEFAULT 'otel'"),
        ("metric_points", "source", "VARCHAR(10) NOT NULL DEFAULT 'otel'"),
    ]
    for table, column, kind in added:
        if column not in {item["name"] for item in inspect(engine).get_columns(table)}:
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {kind}"))
                connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table} ({column})"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts: create any tables that do not exist yet.
    try:
        Base.metadata.create_all(engine)
        add_new_columns()
    except SQLAlchemyError:
        print("WARNING: could not reach the database. Is PostgreSQL running?")
    yield
    # Runs once when the server stops: end the replay and stop the demo services
    replay.stop()
    monitor.stop_all()


app = FastAPI(title="BugSense API", version="0.9.0", lifespan=lifespan)


def frontend_origins():
    """The addresses of the React app that may call this API (CORS). Several
    can be given, separated by commas; a bare host name gets https://."""
    origins = []
    for value in os.getenv("FRONTEND_URL", "http://localhost:5173").split(","):
        value = value.strip().rstrip("/")
        if value:
            origins.append(value if "://" in value else f"https://{value}")
    return origins


# The React app runs on a different address than this API. Browsers block
# such cross-origin requests unless the API allows them (CORS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Each feature keeps its endpoints in its own file inside app/routes/.
# Every feature needs a signed-in user; sign-in itself and /health do not.
signed_in = [Depends(current_user)]
app.include_router(auth.router)
app.include_router(logs.router, dependencies=signed_in)
app.include_router(projects.router, dependencies=signed_in)
app.include_router(datasets.router, dependencies=signed_in)
app.include_router(incidents.router, dependencies=signed_in)
app.include_router(monitoring.router, dependencies=signed_in)
app.include_router(telemetry.router, dependencies=signed_in)
app.include_router(tools.router, dependencies=signed_in)
# OpenTelemetry senders are programs, not people: they use the ingest token
app.include_router(telemetry.receiver, dependencies=[Depends(ingest_allowed)])


@app.get("/health")
def health():
    """Simple check that tells the frontend the backend and database are alive."""
    return {
        "status": "ok",
        "service": "bugsense-backend",
        "database": "connected" if is_database_connected() else "unavailable",
        "time": datetime.now(timezone.utc).isoformat(),
    }
