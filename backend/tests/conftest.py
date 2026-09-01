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
        # payments_router больше не ходит в Redis: идемпотентность вебхука
        # переехала в таблицу payment_events (миграция 041).
        "backend.interpretation.rag_router.get_redis",
    ]
    with contextlib.ExitStack() as stack:
        for target in targets:
            stack.enter_context(patch(target, return_value=client))
        # auth/router.py держит собственный клиент (OTP-регистрация), мимо
        # backend.redis_client — его геттер асинхронный.
        stack.enter_context(
            patch("backend.auth.router._get_redis", AsyncMock(return_value=client))
        )
        yield client


# ── Сеть наружу: запрещена во всех тестах ────────────────
# Класс исключения живёт в отдельном модуле, а не здесь — см. netguard.py:
# conftest импортируется pytest'ом под собственным именем, и тест, сделавший
# `from backend.tests.conftest import ...`, получил бы ДРУГОЙ объект класса.
from backend.tests.netguard import OutboundNetworkBlocked


@pytest.fixture(autouse=True)
def no_outbound_network(request):
    """Рвать любое обращение наружу вместо реального сетевого вызова.

    Зачем. До 31.08.2026 `mock_geo` патчил не все привязки `geocode_place`, и
    /chart/calculate ходил в живой Nominatim. Прогон CI 31.08.2026 упал на 19
    тестах, не связанных ни с геокодингом, ни друг с другом (тарифы, прогнозы,
    платежи): чужой сервис отдал 429, фикстура карты рассыпалась, каскад
    накрыл всё, что её использует. Лечилось перезапуском до зелёного — то
    есть зелёный прогон перестал что-либо доказывать, а привычка
    перезапускать однажды пропустит настоящую поломку.

    Заглушка ниже любого HTTP-клиента: ловит httpx, requests, urllib и всё
    остальное разом, включая новый код, который завтра позовёт наружу мимо
    существующих моков. Именно поэтому это autouse-фикстура, а не «мок в
    нужных тестах» — незамоканный вызов должен падать сразу и громко, а не
    втихую уходить в интернет.

    ⚠️ Одного `socket.socket.connect` НЕ хватает, хотя выглядит достаточным:
    на Windows asyncio крутит ProactorEventLoop, который соединяется через
    overlapped-вызов `ConnectEx` мимо метода сокета, и АСИНХРОННЫЙ запрос
    (весь наш httpx.AsyncClient) проходил сквозь такую заглушку насквозь.
    Проверено: синхронный httpx.get блокировался, `await client.get(...)` —
    нет. Поэтому основная точка — `socket.getaddrinfo`: резолв имени
    предшествует соединению у всех клиентов и на всех платформах, а
    `connect`/`connect_ex` оставлены вторым слоем на случай уже готового
    IP-адреса.

    Loopback разрешён: TestClient работает в процессе, SQLite — в памяти,
    fakeredis — тоже, но локальный сокет нужен настоящему Redis в CI
    (RedisCache подключается на импорте) и не является обращением наружу.

    Тесты, которым внешний вызов нужен по существу (проверяют саму интеграцию
    с Nominatim), помечены маркером `external` и в обычный прогон не попадают
    (см. addopts в pytest.ini); при явном запуске фикстура их пропускает.
    """
    import socket

    if request.node.get_closest_marker("external"):
        yield
        return

    _real_getaddrinfo = socket.getaddrinfo
    _real_connect = socket.socket.connect
    _real_connect_ex = socket.socket.connect_ex

    _LOCAL = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}

    def _norm(host) -> str:
        # asyncio передаёт хост байтами (getaddrinfo(b'example.com', ...)) —
        # без декодирования `str(b'127.0.0.1')` дал бы "b'127.0.0.1'" и
        # заблокировал бы локальный Redis в CI.
        if isinstance(host, (bytes, bytearray)):
            return host.decode("ascii", "replace")
        return "" if host is None else str(host)

    def _blocked(host) -> OutboundNetworkBlocked:
        return OutboundNetworkBlocked(
            f"Тест пытался обратиться наружу: {host}. "
            "Замокайте вызов (см. mock_geo в conftest.py и "
            "test_geocoding_offline.py) или пометьте тест маркером "
            "@pytest.mark.external, если он про саму интеграцию с внешним "
            "сервисом."
        )

    def _guard_getaddrinfo(host, *args, **kwargs):
        if _norm(host) not in _LOCAL:
            raise _blocked(host)
        return _real_getaddrinfo(host, *args, **kwargs)

    def _host_of(address):
        if isinstance(address, tuple) and address:
            return _norm(address[0])
        return None  # unix-сокеты и прочее — не наш случай

    def _guard_connect(self, address, *args, **kwargs):
        host = _host_of(address)
        if host is not None and host not in _LOCAL:
            raise _blocked(address)
        return _real_connect(self, address, *args, **kwargs)

    def _guard_connect_ex(self, address, *args, **kwargs):
        host = _host_of(address)
        if host is not None and host not in _LOCAL:
            raise _blocked(address)
        return _real_connect_ex(self, address, *args, **kwargs)

    socket.getaddrinfo = _guard_getaddrinfo
    socket.socket.connect = _guard_connect
    socket.socket.connect_ex = _guard_connect_ex
    try:
        yield
    finally:
        socket.getaddrinfo = _real_getaddrinfo
        socket.socket.connect = _real_connect
        socket.socket.connect_ex = _real_connect_ex


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
# Все модули, которые связали имя `geocode_place` у себя на импорте.
# `from backend.ephemeris.geo import geocode_place` копирует ссылку в
# пространство имён импортирующего модуля — патч исходного модуля такую копию
# НЕ трогает (та же причина, по которой fake_redis выше патчит семь целей, а
# не одну). Из-за этого mock_geo патчил только backend.ephemeris.geo, а
# /chart/calculate звал живой Nominatim: 4 минуты на два теста локально и 429
# с каскадом из 19 упавших тестов в CI 31.08.2026.
#
# crm/router.py импортирует geocode_place ВНУТРИ функции — там имя
# разрешается в момент вызова, и патч исходного модуля работает; отдельной
# цели не нужно.
_GEOCODE_PATCH_TARGETS = (
    "backend.ephemeris.geo.geocode_place",
    "backend.main.geocode_place",
    "backend.advanced_charts_router.geocode_place",
)


@pytest.fixture
def mock_geo():
    """Mock geocode_place to avoid real HTTP calls.

    Мок стоит на границе с ЧУЖИМ сервисом (Nominatim), а не на нашем коде:
    разбор ответа, кэш и ветки ошибок в `geo.geocode_place` мок не подменяет
    собой молча — они покрыты отдельно в test_geocoding_offline.py, где
    подменяется httpx-транспорт, а наш код исполняется по-настоящему.
    """
    import contextlib
    from backend.ephemeris.geo import GeoResult
    geo_result = GeoResult(
        latitude=55.75,
        longitude=37.62,
        display_name="Moscow, Russia",
        timezone="Europe/Moscow",
    )
    with contextlib.ExitStack() as stack:
        mocks = [
            stack.enter_context(patch(t, new_callable=AsyncMock))
            for t in _GEOCODE_PATCH_TARGETS
        ]
        for m in mocks:
            m.return_value = geo_result
        yield mocks[0]


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
    # Не `if ...: return None`. Провал подготовки карты возвращал None, тест
    # шёл дальше и звал /api/v1/chart/None/... — сервер отвечал 404, тест падал
    # с «404 != 403» и уводил разбор к правам доступа, хотя ломалось создание
    # карты. Так уже теряли время на разборе прогона CI 31.08.2026 (реальный
    # Nominatim отдал 429, посыпались 19 несвязанных тестов). Ассерт с телом
    # ответа роняет тест ровно там, где сломалось, и показывает причину.
    assert resp.status_code == 200, f"фикстура created_chart: {resp.status_code} {resp.text}"
    chart_id = resp.json().get("id")
    assert chart_id, f"фикстура created_chart: в ответе нет id — {resp.text}"
    return chart_id
