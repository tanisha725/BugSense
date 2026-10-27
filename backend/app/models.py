"""Database tables, written as Python classes (SQLAlchemy models).

Relationships:
    User     1 --- many  Project
    Project  1 --- many  Log
    Project  1 --- many  Incident
    Incident 1 --- many  Log   (a log may belong to no incident)
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
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
    stack_trace: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped["Project"] = relationship(back_populates="logs")
    incident: Mapped["Incident | None"] = relationship(back_populates="logs")
