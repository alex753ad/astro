"""Первая неделя по сценарию — флаг first_week (решение владельца 01.10.2026).

В первые 7 местных дней после регистрации каждый день подсвечивается одна
вещь. Ничего не прячется: всё доступно сразу, подсвечивается «новое на
сегодня». Только приложение (на сайте подсветки нет — решение владельца).

* День — по поясу человека (тот же time_utils.user_tz, что у всех разделов), от даты
  регистрации: день регистрации — день 1.
* «Открыл» — отметка с устройства (`first_week_marks`, 073), POST /seen.
  Сервер не пытается угадать по журналам разборов и чата: отметка одна на
  все функции, и для прогноза, карты и периодов других следов нет.
* Карточка — самое раннее неоткрытое из уже наступивших дней; вперёд не
  забегаем. В день 7 первым идёт итог недели, если его ещё не смотрели.
* Вечерний пуш дней 2–7 — вместо «Прогноза на завтра» (push/cron.py), и
  только если функция ИМЕННО этого дня ещё не открыта. В день 1 пуша нет:
  человек только что зарегистрировался. Ведёт в ленту (target feed_today),
  где стоит карточка.
* Письма: день 2 не уходит тем, у кого есть приложение; день 7 — итог недели
  вместо «Разбери свои транзиты» (lifecycle_emails.py).

Тексты согласованы владельцем таблицей 01.10.2026; «Периоды» ведут на то,
что открыто на бесплатном: период Солнца и Луна по домам.

Восемь пунктов в семи днях (решение владельца 02.10.2026,
docs/first_week_widget_day.md): день 3 — виджет «День» (кнопка — системный
запрос закрепления), разбор транзитов и периоды — вместе в день 5: карточки
по-прежнему по одной, пуш дня — про разбор транзитов. Пункт «виджет»
пропускается, если флаг widget выключен или клиент его не умеет (старый APK
без `?widget=1`: иначе карточка без кнопки закрыла бы следующие дни);
лаунчер без закрепления и уже стоящий виджет приложение отмечает само.
⚠️ «Два разбора — на пробу» и «Три сообщения — на пробу» — только у
бесплатного тарифа; числа — из TIER_FLAGS, не руками.
"""
from __future__ import annotations

from datetime import date, timedelta

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
    ("widget", "Сегодня: твой день на главном экране",
     "Фаза Луны и главное событие дня — без входа в приложение.",
     "Твой день на главном экране", "Фаза Луны и событие дня — прямо на главном экране."),
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
TRIED_KEYS = KEYS[:-1]  # всё, кроме итога
DAY_KEYS = {1: ("chart",), 2: ("forecast",), 3: ("widget",), 4: ("interpret",),
            5: ("transit", "periods"), 6: ("chat",), 7: ("summary",)}
WIDGET = "widget"
TRIED_TITLE = {"chart": "Карта", "widget": "Виджет"}  # остальные — заголовок пуша


def widget_skipped(db: Session, user: User, widget_client: bool = True) -> bool:
    """Пункт «виджет» не показывается и не ждёт отметки (правило — в шапке)."""
    from backend.flags import flag_on
    return not widget_client or not flag_on(db, "widget", user)


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
    from backend.time_utils import local_today, user_tz
    return local_today(user_tz(None, user, chart))


def day_number(user: User, chart, today: date) -> int | None:
    """1…7 — день первой недели для местной даты `today`, иначе None."""
    if not user.created_at:
        return None
    from backend.time_utils import user_tz
    tz = pytz.timezone(user_tz(None, user, chart))
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
    for d in range(1, min(day, DAYS - 1) + 1):
        for key in DAY_KEYS[d]:
            if key not in done:
                return key
    return None


def card(db: Session, user: User, chart, widget_client: bool = False) -> dict | None:
    day = day_number(user, chart, local_today(user, chart))
    if day is None:
        return None
    done = marks(db, user)
    if widget_skipped(db, user, widget_client):
        done |= {WIDGET}
    key = card_key(day, done)
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
    key = DAY_KEYS[day][0]
    _, _, _, title, text = STEPS[KEYS.index(key)]
    if key in marks(db, user) or (key == WIDGET and widget_skipped(db, user)):
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
    from backend.push.cron import _daily_time_of, _quiet_from_of
    from backend.time_utils import user_tz

    reg_msk = pytz.utc.localize(user.created_at).astimezone(pytz.timezone("Europe/Moscow")).date()
    visits = db.query(func.count(func.distinct(UserActivityDay.day))).filter(
        UserActivityDay.user_id == user.id,
        UserActivityDay.day >= reg_msk, UserActivityDay.day < reg_msk + timedelta(days=DAYS),
    ).scalar() or 0

    tz, lo, hi = user_tz(None, user, chart), _daily_time_of(user), _quiet_from_of(user)
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
        "tried": [{"key": k, "title": TRIED_TITLE.get(k) or STEPS[KEYS.index(k)][3], "done": k in done}
                  for k in TRIED_KEYS if not (k == WIDGET and widget_skipped(db, user))],
        "ahead": return_title(ahead) if ahead else None,
        "free": (user.tier or "free") == "free",
    }
