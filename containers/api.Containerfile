# BugSense backend (FastAPI). It also runs the demo shop (shop-db, shop-api,
# shop-web) as child processes, which send live OpenTelemetry to this API.
# Build from the repository root:  podman build -f containers/api.Containerfile .
FROM docker.io/library/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# Same layout as the repository: the monitor finds ../demo-services
COPY backend/app ./app
COPY backend/datasets ./datasets
COPY demo-services /srv/demo-services
COPY containers/wait_for_db.py /srv/wait_for_db.py

# Run as an ordinary user, not root
RUN useradd --create-home bugsense && chown -R bugsense /srv
USER bugsense

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

# Wait for PostgreSQL, then start the API
CMD ["sh", "-c", "python /srv/wait_for_db.py && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
