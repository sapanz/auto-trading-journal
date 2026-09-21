import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

_database_url = os.environ.get("DATABASE_URL")

if _database_url:
    # Render/Neon/Heroku-style URLs use the "postgres://" scheme;
    # SQLAlchemy 2.0 requires "postgresql://".
    if _database_url.startswith("postgres://"):
        _database_url = _database_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URL = _database_url
    engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
else:
    # Local/dev default: a SQLite file. Not suitable for hosts with an
    # ephemeral filesystem (e.g. Render's free tier) — set DATABASE_URL to
    # a persistent Postgres instance (e.g. a free Neon database) there.
    DB_PATH = os.environ.get(
        "JOURNAL_DB_PATH", str(Path(__file__).resolve().parent.parent / "journal.db")
    )
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
