"""Гонка при активации пилотного токена — находка 2.4 аудита 23.08.2026.

Два одновременных POST /pilot/claim с ОДНИМ токеном читали `used` до того,
как любой из них его записал: оба видели False, оба проходили проверку и оба
выдавали premium. Лечится блокировкой строки токена (`with_for_update()`) в
той же транзакции, что и запись `used=True`.

⚠️ ТЕСТ ТРЕБУЕТ POSTGRES И НА SQLITE ПРОПУСКАЕТСЯ — это не лень и не
временная мера. Диалект SQLite в SQLAlchemy FOR UPDATE не поддерживает и
молча не выдаёт его в SQL, то есть проверяемая защита там ОТСУТСТВУЕТ.
Прогнанный на SQLite тест был бы зелёным ровно в том окружении, где дефект
живой, — то есть проверял бы не код, а собственную формулировку.

Своё подключение, а не фикстуры conftest: conftest заводит in-memory SQLite
для всего прогона (`TEST_DATABASE_URL = "sqlite://"`) независимо от
DATABASE_URL. В CI DATABASE_URL указывает на живой postgres:18 (сервис в
ci.yml), поэтому здесь тест исполняется по-настоящему; локально без Postgres
он пропускается с явной причиной.

Маркера `integration` намеренно НЕТ: CI гоняет тесты с
`-m "not integration and not load and not external"`, и под маркером этот
тест не исполнялся бы там, где только и может быть исполнен.
"""

import os
import threading
import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _postgres_reachable() -> str:
    """Пустая строка — Postgres есть; иначе причина пропуска.

    ⚠️ Проверяется СОЕДИНЕНИЕ, а не вид строки подключения. На машине
    разработчика `.env` задаёт localhost:5432, которого может не быть
    запущено: проверка по префиксу "postgresql://" признала бы такое
    окружение годным, и тест падал бы с ошибкой подключения вместо
    честного пропуска.
    """
    if not DATABASE_URL.startswith(("postgresql://", "postgresql+", "postgres://")):
        return f"DATABASE_URL не Postgres ({DATABASE_URL!r})"
    try:
        create_engine(DATABASE_URL, connect_args={"connect_timeout": 3}).connect().close()
    except Exception as e:  # noqa: BLE001
        return f"Postgres по DATABASE_URL недоступен: {type(e).__name__}"
    return ""


_SKIP_REASON = _postgres_reachable()

requires_postgres = pytest.mark.skipif(
    bool(_SKIP_REASON),
    reason=(
        "нужен живой Postgres: на SQLite FOR UPDATE не выдаётся вовсе, "
        f"и тест был бы зелёным при живом дефекте — {_SKIP_REASON}"
    ),
)


class TestLockIsRequested:
    """Блокировка ЗАПРОШЕНА — проверяется где угодно, включая SQLite.

    Эта проверка не заменяет гонку ниже и не притворяется ею: она не может
    показать, что блокировка РАБОТАЕТ (на SQLite её нет), но ловит самый
    вероятный способ сломать защиту — удалить `.with_for_update()` при
    правке соседних строк. Такая правка прошла бы мимо всех остальных
    тестов проекта: на SQLite поведение claim_pilot без блокировки
    неотличимо от поведения с ней.
    """

    def test_claim_asks_to_lock_the_token_row(self, db, user_free, monkeypatch):
        import asyncio
        from datetime import timedelta as _td

        from sqlalchemy.orm import Query

        from backend.models import PilotToken
        from backend.pilot.router import ClaimIn, claim_pilot
        from backend.time_utils import utcnow as _utcnow

        db.add(PilotToken(token="lock-check", tg_user_id="tg-lock",
                          expires_at=_utcnow() + _td(minutes=30)))
        db.commit()

        locked = []
        original = Query.with_for_update

        def spy(self, *a, **kw):
            locked.append(self.column_descriptions[0]["type"])
            return original(self, *a, **kw)

        monkeypatch.setattr(Query, "with_for_update", spy)
        asyncio.run(claim_pilot(ClaimIn(token="lock-check"), user_free, db))

        assert PilotToken in locked, (
            "claim_pilot читает строку токена без with_for_update() — "
            "защита от гонки 2.4 снята"
        )


@pytest.fixture
def pg():
    """Движок и схема на живом Postgres. Созданные строки убираются за собой."""
    from backend.models import Base

    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


def _make_user(Session, email: str):
    from backend.models import User

    uid = str(uuid.uuid4())
    with Session() as s:
        s.add(User(id=uid, email=email, hashed_password="x", tier="free"))
        s.commit()
    return uid


@requires_postgres
def test_two_concurrent_claims_give_premium_to_exactly_one(pg):
    import asyncio

    from backend.models import PilotToken, User
    from backend.pilot.router import ClaimIn, claim_pilot
    from backend.time_utils import utcnow

    token = f"race-{uuid.uuid4().hex[:16]}"
    tg_id = f"tg{uuid.uuid4().hex[:10]}"
    with pg() as s:
        s.add(PilotToken(token=token, tg_user_id=tg_id,
                         expires_at=utcnow() + timedelta(minutes=30)))
        s.commit()

    user_a = _make_user(pg, f"a-{uuid.uuid4().hex[:8]}@example.com")
    user_b = _make_user(pg, f"b-{uuid.uuid4().hex[:8]}@example.com")

    # Барьер выравнивает старт: без него второй поток может успеть прочитать
    # токен уже после чужого коммита, и гонки не случится вовсе — тест стал бы
    # проверять последовательный сценарий под видом параллельного.
    start = threading.Barrier(2)
    results: dict[str, object] = {}

    def claim(uid: str):
        with pg() as s:
            user = s.query(User).filter(User.id == uid).one()
            start.wait(timeout=10)
            try:
                results[uid] = asyncio.run(claim_pilot(ClaimIn(token=token), user, s))
            except HTTPException as e:
                results[uid] = e

    threads = [threading.Thread(target=claim, args=(u,)) for u in (user_a, user_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    ok = [r for r in results.values() if isinstance(r, dict)]
    refused = [r for r in results.values() if isinstance(r, HTTPException)]
    assert len(ok) == 1, f"premium выдан {len(ok)} раз(а), ожидался ровно один: {results}"
    assert len(refused) == 1 and refused[0].status_code == 409, f"отказ не тот: {results}"

    with pg() as s:
        tiers = [s.query(User).filter(User.id == u).one().tier for u in (user_a, user_b)]
        assert sorted(tiers) == ["free", "premium"], f"тарифы в БД: {tiers}"
        row = s.query(PilotToken).filter(PilotToken.token == token).one()
        assert row.used is True and row.used_by_user_id in (user_a, user_b)
