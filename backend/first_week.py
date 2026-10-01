"""Первая неделя по сценарию — флаг first_week (решение владельца 01.10.2026).

В первые 7 местных дней после регистрации каждый день подсвечивается одна
вещь. Ничего не прячется: всё доступно сразу, подсвечивается «новое на
сегодня». Только приложение (на сайте подсветки нет — решение владельца).

* День — по поясу человека (тот же user_timezone, что у пушей), от даты
  регистрации: день регистрации — день 1.
* «Открыл» — отметка с устройства (`first_week_marks`, 073), POST /seen.
  Сервер не пытается угадать по журналам разборов и чата: отметка одна на
  все шесть функций, и для прогноза, карты и периодов других следов нет.
* Карточка — самое раннее неоткрытое из уже наступивших дней; вперёд не
  забегаем. В день 7 первым идёт итог недели, если его ещё не смотрели.
* Вечерний пуш дней 2–7 — вместо «Прогноза на завтра» (push/cron.py), и
  только если функция ИМЕННО этого дня ещё не открыта. В день 1 пуша нет:
  человек только что зарегистрировался. Ведёт в ленту (target feed_today),
  где стоит карточка.
* Письма: день 2 не уходит тем, у кого есть приложение; день 7 — итог недели
  вместо «Разбери свои транзиты» (lifecycle_emails.py).

Тексты согласованы владельцем таблицей 01.10.2026; день 5 — «Периоды»
(ведёт на то, что открыто на бесплатном: период Солнца и Луна по домам).
⚠️ «Два разбора — на пробу» и «Три сообщения — на пробу» — только у
бесплатного тарифа; числа — из TIER_FLAGS, не руками.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytz
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import FirstWeekMark, User, UserActivityDay

FLAG = "first_week"
DAYS = 7
PUSH_KIND = "first_week"

# key, заголовок карточки, текст карточки, заголовок пуша, текст пуша
STEPS = (
    ("chart", "Сегодня: твоя карта", "Начни с карты рождения: круг, дома и аспекты.", None, None),
    ("forecast", "Сегодня: прогноз дня",
     "Каждое утро здесь прогноз по твоей карте. Разверни карточку «Сегодня».",
     "Прогноз дня", "Прогноз дня уже в ленте — разверни карточку «Сегодня»."),
    ("interpret", "Сегодня: разбор карты", "Прочитай разбор своей карты — около 450 слов о тебе.",
     "Разбор карты", "Около 450 слов о тебе — по твоей карте рождения."),
    ("transit", "Сегодня: разбор транзитов", "Коснись события в ленте и открой его разбор.",
     "Разбор транзитов", "Что значат события твоей ленты — открой разбор одного."),
    ("periods", "Сегодня: периоды", "Периоды твоей карты: что идёт сейчас и что впереди.",
     "Периоды", "Периоды твоей карты: что идёт сейчас и что впереди."),
    ("chat", "Сегодня: чат с Аристеей", "Спроси о своей карте своими словами.",
     "Чат с Аристеей", "Спроси о карте своими словами — три сообщения на пробу."),
    ("summary", "Твоя первая неделя", "Что было за неделю и что ждёт дальше.",
     "Итог недели", "Неделя с картой: что было и что ждёт дальше."),
)
KEYS = tuple(s[0] for s in STEPS)
TRIED_KEYS = KEYS[:-1]  # шесть функций, без итога


def _trial_tail(key: str, tier: str) -> str:
    """Хвост «на пробу» к тексту карточки — только бесплатному тарифу."""
    if tier != "free" or key not in ("transit", "chat"):
        return ""
    from backend.auth.rate_limits import TIER_FLAGS
    n = TIER_FLAGS["free"]["transits_ai_trial" if key == "transit" else "chat_trial"]
    word = {2: "Два", 3: "Три", 4: "Четыре"}.get(n, str(n))
    noun = "разбора" if key == "transit" else "сообщения"
    return f" {word} {noun} — на пробу."


def _push_text(key: str, tier: str, text: str) -> str:
    # Пуш чата называет пробные сообщения — платному без хвоста.
    if key == "chat" and tier != "free":
        return "Спроси о своей карте своими словами."
    return text


def local_today(user: User, chart) -> date:
    from backend.push.cron import user_timezone
    return datetime.now(pytz.utc).astimezone(pytz.timezone(user_timezone(user, chart))).date()


def day_number(user: User, chart, today: date) -> int | None:
    """1…7 — день первой недели для местной даты `today`, иначе None."""
    if not user.created_at:
        return None
    from backend.push.cron import user_timezone
    tz = pytz.timezone(user_timezone(user, chart))
    reg = pytz.utc.localize(user.created_at).astimezone(tz).date()
    n = (today - reg).days + 1
    return n if 1 <= n <= DAYS else None


def marks(db: Session, user: User) -> set[str]:
    return {r[0] for r in db.query(FirstWeekMark.key).filter(FirstWeekMark.user_id == user.id).all()}


def mark(db: Session, user: User, key: str) -> None:
    if key not in KEYS:
        raise ValueError(key)
    if not db.get(FirstWeekMark, (user.id, key)):
        db.add(FirstWeekMark(user_id=user.id, key=key))
        db.commit()


def card_key(day: int, done: set[str]) -> str | None:
    """Ключ карточки на день `day` при отметках `done` (правило — в шапке)."""
    if day == DAYS and "summary" not in done:
        return "summary"
    for key in KEYS[:min(day, DAYS - 1)]:
        if key not in done:
            return key
    return None


def card(db: Session, user: User, chart) -> dict | None:
    day = day_number(user, chart, local_today(user, chart))
    if day is None:
        return None
    key = card_key(day, marks(db, user))
    if key is None:
        return None
    _, title, text, _, _ = STEPS[KEYS.index(key)]
    out = {"day": day, "key": key, "title": title, "text": text + _trial_tail(key, user.tier or "free")}
    if key == "summary":
        out["summary"] = summary(db, user, chart)
    return out


def evening_candidate(db: Session, user: User, chart, today: date) -> dict | None:
    """Вечерний пуш первой недели на местную дату `today` или None."""
    day = day_number(user, chart, today)
    if day is None or day < 2:
        return None
    key, _, _, title, text = STEPS[day - 1]
    if key in marks(db, user):
        return None
    return {
        "kind": PUSH_KIND, "ref": f"{key}:{today.isoformat()}",
        "title": title, "body": _push_text(key, user.tier or "free", text),
        "url": f"/chart/{chart.id}", "target": "feed_today",
    }


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def summary(db: Session, user: User, chart) -> dict:
    """Итог недели: заходы, главное прошедшее событие, что опробовано, что впереди.

    Заходы — дни в user_activity_days (по Москве, как сама таблица) с даты
    регистрации. Формулировка без рода: «7 дней — 5 заходов» (решение
    владельца), а не «ты заходил(а)».
    """
    from backend.day_event import main_event, return_title, title, week_top
    from backend.push.cron import _daily_time_of, _quiet_from_of, user_timezone

    reg_msk = pytz.utc.localize(user.created_at).astimezone(pytz.timezone("Europe/Moscow")).date()
    visits = db.query(func.count(func.distinct(UserActivityDay.day))).filter(
        UserActivityDay.user_id == user.id,
        UserActivityDay.day >= reg_msk, UserActivityDay.day < reg_msk + timedelta(days=DAYS),
    ).scalar() or 0

    tz, lo, hi = user_timezone(user, chart), _daily_time_of(user), _quiet_from_of(user)
    today = local_today(user, chart)
    past = None
    for i in range(1, DAYS):
        ev = main_event(chart, today - timedelta(days=i), tz, lo, hi)
        if ev and (past is None or ev.score > past.score):
            past = ev
    ahead = week_top(chart, today, tz, lo, hi)
    done = marks(db, user)
    return {
        "visits": f"7 дней — {visits} {_plural(visits, 'заход', 'захода', 'заходов')}",
        "past": return_title(past) if past else None,
        "tried": [{"key": k, "title": STEPS[KEYS.index(k)][3] or "Карта", "done": k in done}
                  for k in TRIED_KEYS],
        "ahead": return_title(ahead) if ahead else None,
        "free": (user.tier or "free") == "free",
    }
