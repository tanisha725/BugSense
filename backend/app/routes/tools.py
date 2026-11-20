"""Investigation tools over HTTP: the same tools the AI agent uses."""

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import diagnosis, tools

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
def list_tools():
    """Every tool with its parameters as JSON Schema."""
    return tools.definitions()


@router.get("/config")
def ai_config():
    """Whether an AI model is set up, and which one (the key is never shown)."""
    return diagnosis.config()


@router.post("/{name}")
def run_tool(name: str, parameters: dict = Body(default_factory=dict), db: Session = Depends(get_db)):
    """Runs one tool. The body is its parameters as a JSON object."""
    try:
        return tools.run_tool(db, name, parameters)
    except tools.ToolError as problem:
        raise HTTPException(status_code=problem.status, detail=str(problem)) from problem
