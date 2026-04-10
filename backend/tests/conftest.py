"""Pytest fixtures for Astro SPA tests."""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test_astro.db"

from backend.database import Base, get_db
from backend.main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(
        "sqlite:///./test_astro.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        if os.path.exists("test_astro.db"):
            os.remove("test_astro.db")
    except PermissionError:
        pass


@pytest.fixture
def db(test_engine):
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


# Алиас для обратной совместимости
@pytest.fixture
def db_session(db):
    return db


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
