"""Флаги функций — режим до публикации (CLAUDE.md п.9, docs/flags.md).

Новая функция прячется за флагом, пока владелец не скажет включить. Флаг
включается в админке (/admin → «Флаги»), без деплоя и без новой сборки APK:
сервер читает таблицу feature_flags, сайт и приложение — GET /api/v1/flags.

Режимы: off — выключен; all — для всех, включая гостей; users — только для
перечисленных аккаунтов (владелец проверяет на проде на себе).

⚠️ Флаг, которого нет в FLAGS, считается несуществующим: flag_on падает с
KeyError, а строка в таблице с таким ключом игнорируется. Опечатка в ключе
должна ломать тест, а не тихо держать функцию выключенной навсегда.

Кэш — в памяти процесса на CACHE_SECONDS. У api несколько процессов, и
запись в админке сбрасывает кэш только своего: остальные подхватят флаг
через ≤30 с, клиент перезапрашивает флаги не чаще раза в 30 с — итого
включение доходит до минуты (так согласовано владельцем 30.09.2026).
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user_optional
from backend.database import get_db
from backend.models import FeatureFlag, User

# Ключ → что включает. Имя: область_что, латиницей (feed_week_view).
# Флаг убирается отсюда вместе с проверками в коде, когда владелец сказал
# «включаем навсегда».
FLAGS: dict[str, str] = {
    "test_flag": "Проверочный: ничего не включает, только виден в /auth/me и /flags",
    "push_day_event": "Утренний пуш каждый день с главным событием дня, лимит 2 пуша в сутки",
    "first_week": "Первая неделя: карточка «Сегодня: …» в ленте приложения, вечерний пуш дней 2–7, итог недели",
    "push_return": "Не заходил 5 дней — утренний пуш называет главное событие следующих 7 дней",
}

MODES = ("off", "all", "users")
CACHE_SECONDS = 30

_cache: dict[str, tuple[str, frozenset[str]]] = {}
_loaded_at = 0.0


def reset_cache() -> None:
    global _loaded_at
    _cache.clear()
    _loaded_at = 0.0


def _rows(db: Session) -> dict[str, tuple[str, frozenset[str]]]:
    global _loaded_at
    if time.monotonic() - _loaded_at > CACHE_SECONDS:
        _cache.clear()
        for row in db.query(FeatureFlag).all():
            if row.key in FLAGS:
                _cache[row.key] = (row.mode, frozenset(row.user_ids or []))
        _loaded_at = time.monotonic()
    return _cache


def flag_on(db: Session, key: str, user: User | str | None) -> bool:
    """Включён ли флаг для человека. user — User, его id или None (гость).

    Пуши и письма из фоновых задач зовут это на каждого получателя.
    """
    if key not in FLAGS:
        raise KeyError(f"Неизвестный флаг {key!r} — добавь в backend/flags.py FLAGS")
    mode, user_ids = _rows(db).get(key, ("off", frozenset()))
    if mode == "all":
        return True
    if mode == "users" and user is not None:
        return (user if isinstance(user, str) else user.id) in user_ids
    return False


def enabled_flags(db: Session, user: User | None) -> list[str]:
    return sorted(k for k in FLAGS if flag_on(db, k, user))


router = APIRouter(prefix="/api/v1", tags=["flags"])


@router.get("/flags", summary="Флаги, включённые для этого человека (или гостя)")
async def my_flags(
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Сайт и приложение спрашивают это при запуске и при возврате на
    вкладку / в приложение (frontend/src/lib/flags.js)."""
    return {"flags": enabled_flags(db, user)}
