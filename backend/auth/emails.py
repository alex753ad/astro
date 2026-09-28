"""Почта без учёта регистра и пробелов по краям (решение владельца 28.09.2026).

Приёмка: в приложении клавиатура или автозаполнение подставляли почту с
заглавной буквы («Lion_e@bk.ru»), а сервер искал точным совпадением — «Invalid
credentials» при верном пароле, хотя на сайте вход был.

⚠️ Хранится почта как есть (старые записи могли попасть в базу в любом
регистре — данные не трогаем без отдельного решения), сравнивается —
`lower(email)`. Если в базе окажутся два аккаунта, отличающихся только
регистром, `find_user_by_email` берёт точное совпадение, а при его отсутствии
не выбирает наугад: None и ошибка в лог (scripts/check_email_case.sh).
"""
import logging

from sqlalchemy import func

from backend.models import User

logger = logging.getLogger("astro.auth.emails")


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def find_user_by_email(db, email: str | None):
    e = normalize_email(email)
    if not e:
        return None
    rows = db.query(User).filter(func.lower(User.email) == e).limit(3).all()
    if len(rows) <= 1:
        return rows[0] if rows else None
    raw = (email or "").strip()
    exact = next((u for u in rows if u.email == raw), None)
    logger.error("Аккаунты, отличающиеся только регистром почты: %d шт. (id %s)",
                 len(rows), ", ".join(str(u.id) for u in rows))
    return exact
