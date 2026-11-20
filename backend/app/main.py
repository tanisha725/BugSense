"""BugSense backend - the entry point of the FastAPI application."""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app import models  # noqa: F401 - importing registers the tables on Base
from app.database import Base, engine
from app.routes import datasets, incidents, logs, monitoring, projects, telemetry, tools
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
    columns = {column["name"] for column in inspect(engine).get_columns("logs")}
    if "trace_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE logs ADD COLUMN trace_id VARCHAR(32)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_logs_trace_id ON logs (trace_id)"))


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


app = FastAPI(title="BugSense API", version="0.8.0", lifespan=lifespan)

# The React app runs on a different port (5173) than this API (8000).
# Browsers block such cross-origin requests unless the API allows them (CORS).
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Each feature keeps its endpoints in its own file inside app/routes/
app.include_router(logs.router)
app.include_router(projects.router)
app.include_router(datasets.router)
app.include_router(incidents.router)
app.include_router(monitoring.router)
app.include_router(telemetry.receiver)
app.include_router(telemetry.router)
app.include_router(tools.router)


@app.get("/health")
def health():
    """Simple check that tells the frontend the backend and database are alive."""
    return {
        "status": "ok",
        "service": "bugsense-backend",
        "database": "connected" if is_database_connected() else "unavailable",
        "time": datetime.now(timezone.utc).isoformat(),
    }
