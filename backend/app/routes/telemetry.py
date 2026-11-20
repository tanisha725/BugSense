"""Telemetry: the OpenTelemetry receiver and what the Telemetry page asks for.

POST /v1/traces, /v1/metrics, /v1/logs   the standard OTLP/HTTP paths, so any
                                         OpenTelemetry SDK or Collector can send here
GET  /telemetry/...                      services, metric series, traces
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import otlp, telemetry

receiver = APIRouter(tags=["telemetry"])
router = APIRouter(prefix="/telemetry", tags=["telemetry"])

MAX_BODY = 8 * 1024 * 1024  # 8 MB per export

Window = Annotated[int, Query(ge=1, le=1440, description="How many minutes back to look")]
ProjectId = Annotated[int | None, Query(ge=1)]


def aware(moment):
    """Times sent without a time zone are read as the computer's local time."""
    return moment.astimezone() if moment and moment.tzinfo is None else moment


def store(signal, message, db):
    counts = otlp.STORE[signal](db, message)
    for project_id in counts:
        if signal == "traces":
            # New spans can start or end an alert; an alert is a log, so detection runs
            if telemetry.check_alerts(db, project_id):
                otlp.detect_soon(db, project_id)
        elif signal == "logs":
            otlp.detect_soon(db, project_id)


async def receive(signal, request, db):
    try:
        body = await request.body()
    except ClientDisconnect:
        # The sender went away mid-message (for example a service being stopped)
        return Response(status_code=400)
    if len(body) > MAX_BODY:
        raise HTTPException(status_code=413, detail="OTLP message is too large (limit is 8 MB)")
    content_type = request.headers.get("content-type", "")
    try:
        message = otlp.decode(signal, body, content_type, request.headers.get("content-encoding"))
    except otlp.OtlpError as problem:
        raise HTTPException(status_code=400, detail=str(problem)) from problem

    # Database work blocks, so it runs in a worker thread, not in the event loop
    await run_in_threadpool(store, signal, message, db)
    content, media_type = otlp.encode_response(signal, content_type)
    return Response(content=content, media_type=media_type)


@receiver.post("/v1/traces")
async def receive_traces(request: Request, db: Session = Depends(get_db)):
    """OTLP/HTTP trace export (protobuf or JSON)."""
    return await receive("traces", request, db)


@receiver.post("/v1/metrics")
async def receive_metrics(request: Request, db: Session = Depends(get_db)):
    """OTLP/HTTP metrics export (protobuf or JSON)."""
    return await receive("metrics", request, db)


@receiver.post("/v1/logs")
async def receive_logs(request: Request, db: Session = Depends(get_db)):
    """OTLP/HTTP logs export (protobuf or JSON)."""
    return await receive("logs", request, db)


@router.get("/services")
def services(
    project_id: ProjectId = None,
    service: str | None = None,
    window_minutes: Window = 5,
    until: datetime | None = None,
    db: Session = Depends(get_db),
):
    """Requests, error rate, latency percentiles, CPU and memory of every service."""
    return telemetry.service_overview(db, project_id, window_minutes, service, aware(until))


@router.get("/metrics")
def metric_names(project_id: ProjectId = None, service: str | None = None, db: Session = Depends(get_db)):
    """The metric names that can be charted."""
    return telemetry.metric_names(db, project_id, service)


@router.get("/series")
def metric_series(
    metric: str,
    project_id: ProjectId = None,
    service: str | None = None,
    window_minutes: Window = 15,
    step_seconds: Annotated[int, Query(ge=5, le=3600)] = 60,
    aggregation: Literal[telemetry.AGGREGATIONS] = "avg",  # type: ignore[valid-type]
    until: datetime | None = None,
    db: Session = Depends(get_db),
):
    """One metric over time, for a chart."""
    return telemetry.metric_series(
        db, project_id, service, metric, window_minutes, step_seconds, aggregation, aware(until)
    )


@router.get("/traces")
def traces(
    project_id: ProjectId = None,
    service: str | None = None,
    status: Literal["ANY", "ERROR", "OK"] = "ANY",
    min_duration_ms: Annotated[float | None, Query(ge=0)] = None,
    window_minutes: Window = 15,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
    until: datetime | None = None,
    db: Session = Depends(get_db),
):
    """Recent requests, newest first."""
    return telemetry.search_traces(
        db, project_id, service, status, min_duration_ms, window_minutes, limit, aware(until)
    )


@router.get("/traces/{trace_id}")
def trace_detail(
    trace_id: Annotated[str, Path(pattern=r"^[0-9a-fA-F]{32}$")],
    include_logs: bool = True,
    db: Session = Depends(get_db),
):
    """One request as a tree of spans, with the logs written during it."""
    trace = telemetry.get_trace(db, trace_id.lower(), include_logs)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace
