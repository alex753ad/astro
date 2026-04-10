"""Database engine, session factory, and declarative base."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from backend.config import get_settings

settings = get_settings()

# Отладка
print(f"DEBUG APP_DB_URL from env: {os.environ.get('APP_DB_URL', 'NOT_FOUND')}")
print(f"DEBUG db_connection_url: {settings.db_connection_url}")

engine = create_engine(
    settings.db_connection_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session, auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
