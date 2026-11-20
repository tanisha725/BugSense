"""Database tables, written as Python classes (SQLAlchemy models).

Relationships:
    User     1 --- many  Project
    Project  1 --- many  Log
    Project  1 --- many  Incident
    Incident 1 --- many  Log   (a log may belong to no incident)
    Project  1 --- many  Span        (OpenTelemetry traces)
    Project  1 --- many  MetricPoint (OpenTelemetry metrics)
    Project  1 --- many  Diagnosis   (AI or rule-based diagnosis of an incident)
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    projects: Mapped[list["Project"]] = relationship(back_populates="owner")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    owner: Mapped["User"] = relationship(back_populates="projects")
    logs: Mapped[list["Log"]] = relationship(back_populates="project")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="project")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    # INFO, LOW, MEDIUM, HIGH or CRITICAL
    severity: Mapped[str] = mapped_column(String(20), default="LOW")
    # OPEN or RESOLVED
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    affected_service: Mapped[str | None] = mapped_column(String(100))
    error_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    project: Mapped["Project"] = relationship(back_populates="incidents")
    logs: Mapped[list["Log"]] = relationship(back_populates="incident")


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    # Empty until Phase 5 groups this log into an incident
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), index=True)

    # The log line exactly as it was received
    raw: Mapped[str] = mapped_column(Text)

    # Filled in by the log parser (Phase 4), so they can be empty
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    severity: Mapped[str | None] = mapped_column(String(20))
    service: Mapped[str | None] = mapped_column(String(100))
    error_type: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(100))
    # OpenTelemetry trace ID (32 hex characters), links the log to a trace
    trace_id: Mapped[str | None] = mapped_column(String(32), index=True)
    stack_trace: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped["Project"] = relationship(back_populates="logs")
    incident: Mapped["Incident | None"] = relationship(back_populates="logs")


class Span(Base):
    """One step of a request, received over OpenTelemetry (OTLP).

    All spans with the same trace_id belong to one request. parent_span_id
    shows which step called which, so the request can be drawn as a tree.
    """

    __tablename__ = "spans"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    span_id: Mapped[str] = mapped_column(String(16))
    parent_span_id: Mapped[str | None] = mapped_column(String(16))
    service: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255))
    # SERVER, CLIENT, INTERNAL, PRODUCER or CONSUMER
    kind: Mapped[str] = mapped_column(String(20))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float] = mapped_column(Float)
    # UNSET, OK or ERROR
    status: Mapped[str] = mapped_column(String(10), default="UNSET")
    status_message: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)


class MetricPoint(Base):
    """One measurement of one metric, received over OpenTelemetry (OTLP).

    gauge      a value at a moment (memory in use)
    sum        a counter; with DELTA temporality each point is the increase
               since the previous point, with CUMULATIVE the total so far
    histogram  how many measurements fell into each bucket (request durations)
    """

    __tablename__ = "metric_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    service: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    unit: Mapped[str | None] = mapped_column(String(50))
    # DELTA or CUMULATIVE (only for sums and histograms)
    temporality: Mapped[str | None] = mapped_column(String(12))
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # gauge or sum: the value. histogram: the sum of all measurements
    value: Mapped[float] = mapped_column(Float, default=0)
    # histogram only: how many measurements, and the buckets
    count: Mapped[int | None] = mapped_column()
    bounds: Mapped[list | None] = mapped_column(JSON)
    bucket_counts: Mapped[list | None] = mapped_column(JSON)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)


class Diagnosis(Base):
    """The probable cause of an incident, found by the AI or by the rules.

    Incidents are rebuilt whenever detection runs, so their id can change.
    anchor_log_id (the first log of the incident) does not, so a diagnosis is
    found again through it.
    """

    __tablename__ = "diagnoses"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    incident_id: Mapped[int] = mapped_column()
    anchor_log_id: Mapped[int] = mapped_column(index=True)
    incident_title: Mapped[str] = mapped_column(String(255))
    # "rules", or "llm" when an AI model was used
    engine: Mapped[str] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(100))
    probable_cause: Mapped[str] = mapped_column(Text)
    root_service: Mapped[str | None] = mapped_column(String(100))
    # low, medium or high
    confidence: Mapped[str] = mapped_column(String(10))
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    suggested_fixes: Mapped[list] = mapped_column(JSON, default=list)
    limitations: Mapped[str | None] = mapped_column(Text)
    # Every tool call: name, parameters, a short result and how long it took
    steps: Mapped[list] = mapped_column(JSON, default=list)
    # Cost facts: tokens used, time taken, and how much the evidence was reduced
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)
    duration_ms: Mapped[int] = mapped_column(default=0)
    raw_chars: Mapped[int] = mapped_column(default=0)
    evidence_chars: Mapped[int] = mapped_column(default=0)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
