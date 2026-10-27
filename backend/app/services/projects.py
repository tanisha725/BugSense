"""Small helpers for finding and creating projects."""

from sqlalchemy import select

from app.models import Project, User


def demo_owner(db):
    """Login comes in a later phase. Until then every project belongs to one demo user."""
    owner = db.scalars(select(User).order_by(User.id)).first()
    if owner is None:
        owner = User(name="Demo User", email="demo@bugsense.local", password_hash="!")
        db.add(owner)
        db.flush()
    return owner


def find_or_create_project(db, name, description=None):
    project = db.scalars(select(Project).where(Project.name == name)).first()
    if project is None:
        project = Project(name=name, description=description, owner=demo_owner(db))
        db.add(project)
        db.flush()
    return project
