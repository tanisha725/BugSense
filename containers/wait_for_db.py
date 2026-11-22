"""Waits until PostgreSQL accepts connections (at most 60 seconds), so the API
does not crash when its container starts a little before the database's."""

import os
import sys
import time

import psycopg

url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
for attempt in range(60):
    try:
        psycopg.connect(url, connect_timeout=2).close()
        print("Database is ready", flush=True)
        sys.exit(0)
    except psycopg.OperationalError:
        print(f"Waiting for the database ({attempt + 1}/60)...", flush=True)
        time.sleep(1)
sys.exit("The database did not start in 60 seconds")
