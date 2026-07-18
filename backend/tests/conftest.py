"""backend/tests/conftest.py — shared pytest fixtures."""

import os

# Тестовый режим должен быть виден ДО импорта backend.main: часть роутов
# (debug) регистрируется на этапе импорта в зависимости от флага.
os.environ.setdefault("TESTING", "true")

# Лимитер в проде считает в Redis; slowapi ходит туда синхронным клиентом,
# который не перехватывается фикстурой fake_redis. В тестах — in-memory.
os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, AsyncMock, MagicMock

from backend.database import Base, get_db
from backend.main import app, limiter

import backend.main
import backend.redis_client

# Legacy /register закрыт в проде, но нужен тестам — включаем тестовый режим.
from backend.config import get_settings
get_settings().testing = True

# ── In-memory SQLite for tests ────────────────────────────
# StaticPool + одно соединение: иначе каждая сессия получит свою пустую БД.
TEST_DATABASE_URL = "sqlite://"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# lifespan в main.py делает create_all на боевом engine (Postgres) — в тестах
# подменяем его на SQLite, иначе TestClient не стартует без живой БД.
backend.main.engine = engine


# ── Redis: in-memory заглушка вместо живого сервера ──────
@pytest.fixture(autouse=True)
def fake_redis():
    """Подменяем общий async-клиент Redis на fakeredis для всех тестов.

    Модули делают `from backend.redis_client import get_redis`, то есть имя
    связывается на импорте — патчить нужно каждый из них, а не только
    backend.redis_client.
    """
    import contextlib
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    targets = [
        "backend.redis_client.get_redis",
        "backend.auth.token_store.get_redis",
        "backend.auth.sse_tickets.get_redis",
        "backend.auth.login_guard.get_redis",
        "backend.share_router.get_redis",
        "backend.payments.payments_router.get_redis",
    ]
    with contextlib.ExitStack() as stack:
        for target in targets:
            stack.enter_context(patch(target, return_value=client))
        yield client


# ── Rate limiter: отключаем глобально для всех тестов ────
@pytest.fixture(autouse=True)
def disable_rate_limits():
    """Отключаем SlowAPI лимитер на время каждого теста."""
    from backend.main import limiter
    original = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = original


# ── DB ───────────────────────────────────────────────────
@pytest.fixture(scope="function")
def db():
    """Fresh DB session per test with rollback on teardown."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)


# ── HTTP client ──────────────────────────────────────────
@pytest.fixture(scope="function")
def client(db):
    """FastAPI TestClient with DB dependency overridden."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Users ────────────────────────────────────────────────
@pytest.fixture
def user_free(db):
    """Free-tier test user."""
    from backend.models import User
    from backend.auth.passwords import hash_password

    user = User(
        email="free@example.com",
        hashed_password=hash_password("Password123!"),
        name="Free User",
        tier="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def user_pro(db):
    """Pro-tier test user."""
    from backend.models import User
    from backend.auth.passwords import hash_password

    user = User(
        email="pro@example.com",
        hashed_password=hash_password("Password123!"),
        name="Pro User",
        tier="pro",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── Auth headers ─────────────────────────────────────────
@pytest.fixture
def auth_headers_free(user_free):
    """Authorization header for free user."""
    from backend.auth.jwt import create_access_token
    token = create_access_token(
        user_id=user_free.id,
        email=user_free.email,
        tier=user_free.tier,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_pro(user_pro):
    """Authorization header for pro user."""
    from backend.auth.jwt import create_access_token
    token = create_access_token(
        user_id=user_pro.id,
        email=user_pro.email,
        tier=user_pro.tier,
    )
    return {"Authorization": f"Bearer {token}"}


# ── Geo + calculator mocks (shared) ──────────────────────
@pytest.fixture
def mock_geo():
    """Mock geocode_place to avoid real HTTP calls."""
    from backend.ephemeris.geo import GeoResult
    geo_result = GeoResult(
        latitude=55.75,
        longitude=37.62,
        display_name="Moscow, Russia",
        timezone="Europe/Moscow",
    )
    with patch("backend.ephemeris.geo.geocode_place", new_callable=AsyncMock) as m:
        m.return_value = geo_result
        yield m


@pytest.fixture
def mock_calculator():
    """Mock calculate_full_chart — no ephemeris files needed."""
    with patch("backend.ephemeris.calculator.calculate_full_chart") as m:
        from backend.ephemeris.calculator import FullChart, PlanetResult, HouseResult, PointResult

        planets = []
        for i, name in enumerate([
            "Sun", "Moon", "Mercury", "Venus", "Mars",
            "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "North Node",
        ]):
            p = PlanetResult(
                name=name, longitude=float(i * 30), latitude=0.0,
                distance=1.0, speed=1.0, sign="Aries",
                degree_in_sign=float(i * 2), retrograde=False,
            )
            p.house = (i % 12) + 1
            planets.append(p)

        houses = [HouseResult(number=i + 1, sign="Aries", degree=float(i * 30)) for i in range(12)]
        asc = PointResult(sign="Aries", degree=5.0, longitude=5.0)
        mc = PointResult(sign="Capricorn", degree=10.0, longitude=280.0)
        chart = FullChart(planets=planets, houses=houses, ascendant=asc, midheaven=mc, warnings=[])
        m.return_value = (chart, [])
        yield m


# ── Created chart ────────────────────────────────────────
@pytest.fixture
def created_chart(client, mock_calculator, mock_geo, auth_headers_free):
    """Create a natal chart and return its ID."""
    resp = client.post(
        "/api/v1/chart/calculate",
        json={
            "birth_date": "1990-01-10",
            "birth_time": "12:00",
            "birth_place": "Moscow",
            "house_system": "placidus",
        },
        headers=auth_headers_free,
    )
    if resp.status_code != 200:
        return None
    return resp.json().get("id")
