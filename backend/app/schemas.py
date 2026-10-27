"""Shapes of the data that goes in and out of the API (Pydantic schemas)."""

from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class LogCreate(BaseModel):
    """One structured log sent as JSON."""

    # Many tools say "msg", "level" and "time", so those names are accepted too
    message: str = Field(
        min_length=1, max_length=10_000, validation_alias=AliasChoices("message", "msg")
    )
    severity: str | None = Field(
        None, max_length=20, validation_alias=AliasChoices("severity", "level")
    )
    timestamp: datetime | None = Field(
        None, validation_alias=AliasChoices("timestamp", "time")
    )
    service: str | None = Field(None, max_length=100)
    error_type: str | None = Field(None, max_length=100)
    request_id: str | None = Field(None, max_length=100)
    stack_trace: str | None = None
    project_id: int | None = None

    @field_validator("severity")
    @classmethod
    def severity_to_upper_case(cls, value):
        return value.upper() if value else value


class LogText(BaseModel):
    """Raw log text pasted by the user. It can contain many lines."""

    text: str = Field(min_length=1, max_length=2_000_000)
    project_id: int | None = None


class LogOut(BaseModel):
    """A log as it is returned to the frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    incident_id: int | None
    raw: str
    timestamp: datetime | None
    severity: str | None
    service: str | None
    error_type: str | None
    message: str | None
    request_id: str | None
    stack_trace: str | None
    created_at: datetime


class LogsCreated(BaseModel):
    """Summary returned after logs are stored."""

    created: int
    skipped: int = 0
