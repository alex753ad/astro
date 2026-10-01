"""«Неделя вперёд» — флаг week_ahead (решение владельца 01.10.2026).

В воскресенье вечером — карточка в ленте приложения и пуш: главные события
следующей недели (пн–вс). Отбор — `day_event.week_events`, своего правила
здесь нет (docs/notifications.md, «Главное событие дня и лимит пушей»).

* Карточка — с воскресенья TOMORROW_OPEN_HOUR (19:00, тогда же открывается
  карточка «завтра») до конца понедельника, по поясу человека. Нет сильного
  события — карточка «спокойной недели» с добором, пуша нет.
* Пуш — вечерний слот вместо «Прогноза на завтра», в лимите 2. Порядок на
  вечер: first_week → planner_month → week_ahead → «Прогноз на завтра»
  (push/cron.py, `_send_evening`). planner_month важнее: в другой вечер он
  не переносится, а карточка «Недели вперёд» всё равно стоит в ленте.
  Тумблер — «Прогноз дня», тот же, что у слота, который пуш занимает.
* Только приложение (`device_tokens`), как первая неделя: на сайте карточки
  нет, веб-пуш вёл бы в пустоту.
* Первая неделя (флаг first_week) — «Недели вперёд» нет совсем, ни карточки,
  ни пуша: итог дня 7 уже называет «Что впереди» тем же week_top, вторая
  карточка повторяла бы его. Теряется не больше одного воскресенья.

Тексты согласованы владельцем 01.10.2026 (вариант А): заголовок пуша —
даты, текст — события; советы на карточке — те же, что в утреннем пуше.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytz
from sqlalchemy.orm import Session

from backend.models import DeviceToken, User

FLAG = "week_ahead"
PUSH_KIND = "week_ahead"
SUNDAY = 6
CALM_TEXT = "Сильных событий нет — неделя для своих дел."
_WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def _ctx(user: User, chart):
    from backend.push.cron import _daily_time_of, _quiet_from_of, user_timezone
    return user_timezone(user, chart), _daily_time_of(user), _quiet_from_of(user)


def in_first_week(db: Session, user: User, chart, sunday: date) -> bool:
    from backend import first_week
    from backend.flags import flag_on
    return flag_on(db, first_week.FLAG, user) and first_week.day_number(user, chart, sunday) is not None


def _day_month(d: date) -> str:
    from backend.day_event import _MONTHS_GEN
    return f"{d.day} {_MONTHS_GEN[d.month]}"


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} и {parts[-1]}"


def dates_text(days: list[date]) -> str:
    """«7, 8 и 10 октября»; на стыке месяцев — «30 сентября и 2 октября»."""
    if len({d.month for d in days}) == 1:
        return f"{_join([str(d.day) for d in days])} {_day_month(days[0]).split(' ', 1)[1]}"
    return _join([_day_month(d) for d in days])


def range_text(monday: date) -> str:
    """«5–11 октября» или «28 сентября – 4 октября»."""
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        return f"{monday.day}–{_day_month(sunday)}"
    return f"{_day_month(monday)} – {_day_month(sunday)}"


def push_texts(events) -> tuple[str, str]:
    """Заголовок и текст пуша (вариант А)."""
    from backend.day_event import _what
    title = f"Неделя вперёд: {dates_text([e.at_local.date() for e in events])}"
    if len(events) == 1:
        return title, f"{_what(events[0])} — главное на неделе."
    # Новолуние и полнолуние — с маленькой буквы, если не первые в строке.
    whats = [_what(e) if i == 0 or e.natal else _what(e).lower() for i, e in enumerate(events)]
    return title, f"{', '.join(whats)}."


def _row(ev) -> dict:
    from backend.day_event import _what, advice
    d = ev.at_local
    when = f"{_WEEKDAYS[d.weekday()]}, {_day_month(d.date())}"
    return {
        "date": d.date().isoformat(),
        "when": f"{when} · {d:%H:%M}" if ev.timed else when,
        "what": _what(ev), "advice": advice(ev),
        # Для поиска события в ленте по нажатию (FeedScreen).
        "transit": ev.transit, "natal": ev.natal, "aspect": ev.aspect,
    }


def card(db: Session, user: User, chart, now_local: datetime | None = None) -> dict | None:
    """Карточка на сейчас или None (правило показа — в шапке модуля)."""
    from backend.day_event import is_strong, week_events
    from backend.forecast.router import TOMORROW_OPEN_HOUR

    tz, lo, hi = _ctx(user, chart)
    now_local = now_local or datetime.now(pytz.utc).astimezone(pytz.timezone(tz))
    today = now_local.date()
    if today.weekday() == SUNDAY and now_local.hour >= TOMORROW_OPEN_HOUR:
        sunday = today
    elif today.weekday() == 0:
        sunday = today - timedelta(days=1)
    else:
        return None
    if in_first_week(db, user, chart, sunday):
        return None
    events = week_events(chart, sunday, tz, lo, hi)
    return {
        "title": "Неделя вперёд",
        "range": range_text(sunday + timedelta(days=1)),
        "calm": not any(is_strong(e) for e in events),
        "calm_text": CALM_TEXT,
        "events": [_row(e) for e in events],
    }


def evening_candidate(db: Session, user: User, chart, today: date) -> dict | None:
    """Вечерний пуш на местную дату `today` или None. Флаг и устройство
    проверяет вызывающий (push/cron.py, `_week_ahead_evening`)."""
    from backend.day_event import is_strong, week_events
    if today.weekday() != SUNDAY or not getattr(user, "push_daily_forecast", True):
        return None
    if in_first_week(db, user, chart, today):
        return None
    events = week_events(chart, today, *_ctx(user, chart))
    if not any(is_strong(e) for e in events):
        return None
    title, body = push_texts(events)
    return {
        "kind": PUSH_KIND, "ref": (today + timedelta(days=1)).isoformat(),
        "title": title, "body": body,
        "url": f"/chart/{chart.id}", "target": "feed_today",
    }


def has_device(db: Session, user: User) -> bool:
    return db.query(DeviceToken.id).filter(DeviceToken.user_id == user.id).first() is not None
