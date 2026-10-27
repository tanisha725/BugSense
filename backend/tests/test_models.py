from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Incident, Log, Project, User


def test_tables_and_relationships():
    # A throwaway in-memory database, so the test needs no PostgreSQL
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        user = User(name="Asha", email="asha@example.com", password_hash="x")
        project = Project(name="Shop API", owner=user)
        incident = Incident(project=project, title="Database down", severity="HIGH")
        log = Log(project=project, incident=incident, raw="ERROR db connection refused")
        db.add_all([user, project, incident, log])
        db.commit()

        assert user.projects == [project]
        assert project.logs == [log]
        assert incident.logs == [log]
        assert incident.status == "OPEN"
