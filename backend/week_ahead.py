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

import logging
from datetime import date, datetime, timedelta

import pytz
from sqlalchemy.orm import Session

from backend.models import DeviceToken, User

logger = logging.getLogger("astro.week_ahead")

FLAG = "week_ahead"
PUSH_KIND = "week_ahead"
SUNDAY = 6
CALM_TEXT = "Сильных событий нет — неделя для своих дел."
_WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def _ctx(user: User, chart):
    from backend.push.cron import _daily_time_of, _quiet_from_of
    from backend.time_utils import user_tz
    return user_tz(None, user, chart), _daily_time_of(user), _quiet_from_of(user)


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


def sunday_of(now_local: datetime, monday_until: int = 24) -> date | None:
    """Воскресенье, чью неделю показывать сейчас, или None: с воскресенья
    TOMORROW_OPEN_HOUR до понедельника `monday_until` часов (местных)."""
    from backend.forecast.router import TOMORROW_OPEN_HOUR
    today = now_local.date()
    if today.weekday() == SUNDAY and now_local.hour >= TOMORROW_OPEN_HOUR:
        return today
    if today.weekday() == 0 and now_local.hour < monday_until:
        return today - timedelta(days=1)
    return None


def week_data(user: User, chart, sunday: date) -> dict:
    """Содержание недели — одно на карточку и письмо."""
    from backend.day_event import is_strong, week_events
    events = week_events(chart, sunday, *_ctx(user, chart))
    calm = not any(is_strong(e) for e in events)
    subject, preview = push_texts(events) if events else ("", "")
    return {
        "title": "Неделя вперёд",
        "range": range_text(sunday + timedelta(days=1)),
        "calm": calm,
        "calm_text": CALM_TEXT,
        "events": [_row(e) for e in events],
        # Тема и превью письма — заголовок и текст пуша (вариант А).
        "subject": subject, "preview": preview,
    }


def card(db: Session, user: User, chart, now_local: datetime | None = None) -> dict | None:
    """Карточка на сейчас или None (правило показа — в шапке модуля)."""
    if now_local is None:
        now_local = datetime.now(pytz.utc).astimezone(pytz.timezone(_ctx(user, chart)[0]))
    sunday = sunday_of(now_local)
    if sunday is None or in_first_week(db, user, chart, sunday):
        return None
    return week_data(user, chart, sunday)


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


# ── Письмо (решение владельца 01.10.2026) ──
# Тем, у кого нет приложения, на любом тарифе, кроме Лиры и Ориона: у них
# полный недельный дайджест (email_service.send_weekly_digest), второе письмо
# про ту же неделю не шлём. Окно — воскресенье TOMORROW_OPEN_HOUR …
# понедельник EMAIL_MONDAY_UNTIL местного времени: позже это уже не «вперёд».
# Нет сильного события — письма нет, как и пуша. Журнал — email_sent_log
# (kind week_ahead, ref — дата понедельника): повтор прогона ничего не шлёт.
# Beat — ежечасно по вс и пн UTC (celery_app.py): этим покрыт вечер
# воскресенья в любом поясе, а прежний почасовой прогон писем (06–18 UTC)
# западнее UTC до 19:00 воскресенья не доживает.
EMAIL_KIND = "week_ahead"
EMAIL_MONDAY_UNTIL = 12
DIGEST_TIERS = ("pro", "premium")
# TODO(TASKS.md): после публикации в RuStore — строка «В приложении — прогноз
# каждое утро» со ссылкой на установку.


def _email_candidates(db: Session) -> list[User]:
    from sqlalchemy import exists, or_
    return db.query(User).filter(
        User.email.isnot(None),
        User.email_opt_out.is_(False),
        or_(User.tier.is_(None), User.tier.notin_(DIGEST_TIERS)),
        ~exists().where(DeviceToken.user_id == User.id),
    ).all()


def run_emails(db: Session, now_utc: datetime | None = None) -> int:
    """Один прогон рассылки. Идемпотентен."""
    from backend import email_service
    from backend.chart_utils import get_primary_chart
    from backend.email_service import APP_URL
    from backend.flags import flag_on
    from backend.lifecycle_emails import email_window_open, send_once
    from backend.models import EmailSentLog
    from backend.profile.email_unsubscribe import unsubscribe_url

    now_utc = now_utc or datetime.now(pytz.utc)
    sent = 0
    for user in _email_candidates(db):
        if not flag_on(db, FLAG, user):
            continue
        chart = get_primary_chart(db, user)
        if not chart:
            continue
        sunday = sunday_of(now_utc.astimezone(pytz.timezone(_ctx(user, chart)[0])), EMAIL_MONDAY_UNTIL)
        if sunday is None or in_first_week(db, user, chart, sunday):
            continue
        # Окно писем 09–21 местного (lifecycle_emails.email_window_open): из
        # «вс 19:00 … пн 12:00» остаются вс 19–21 и пн 09–12.
        if not email_window_open(user, chart, now_utc):
            continue
        ref = (sunday + timedelta(days=1)).isoformat()
        # Журнал — до эфемерид: прогон идёт каждый час окна.
        if db.query(EmailSentLog.id).filter(EmailSentLog.user_id == user.id, EmailSentLog.kind == EMAIL_KIND,
                                            EmailSentLog.ref == ref).first():
            continue
        unsub = unsubscribe_url(user)
        if not unsub:
            continue
        try:
            data = week_data(user, chart, sunday)
        except Exception as e:
            logger.warning("week_ahead email user=%s: %s", user.id, e)
            continue
        if data["calm"]:
            continue
        email, planner = user.email, f"{APP_URL}/planner/{chart.id}"
        if send_once(db, user.id, EMAIL_KIND, ref,
                     lambda: email_service.send_week_ahead(email, data, planner, unsubscribe_url=unsub)):
            sent += 1
    return sent
