"""Database connection setup. Every other file gets its database access from here."""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Read variables from the .env file in the project root (if it exists).
# load_dotenv searches this folder and then each parent folder for it.
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://localhost:5432/bugsense"
)
# Hosts such as Render give "postgres://..." or "postgresql://...". SQLAlchemy
# needs to be told which driver to use: psycopg.
for prefix in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(prefix):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(prefix):]

# The engine is the actual connection to PostgreSQL
engine = create_engine(DATABASE_URL)

# A session is one "conversation" with the database
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    """All table models inherit from this class."""


def get_db():
    """Gives a route a database session and always closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
