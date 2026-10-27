"""Projects: each monitored application has its own logs."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Log, Project

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    """All projects, with how many logs and errors each one has."""
    error_count = func.count().filter(Log.severity.in_(["ERROR", "CRITICAL"]))
    counts = {
        project_id: (total, errors)
        for project_id, total, errors in db.execute(
            select(Log.project_id, func.count(), error_count).group_by(Log.project_id)
        )
    }
    projects = db.scalars(select(Project).order_by(Project.id)).all()
    return [
        {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "log_count": counts.get(project.id, (0, 0))[0],
            "error_count": counts.get(project.id, (0, 0))[1],
        }
        for project in projects
    ]
