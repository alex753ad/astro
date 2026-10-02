"""Виджет «День» на главном экране Android (флаг `widget`).

Решения владельца 02.10.2026 (docs/widget_plan.md, ветка wip/tariffs-pdf):
виджет в сеть не ходит — приложение при открытии забирает запас на DAYS
дней (`GET /api/v1/widget`) и кладёт его виджету (frontend/plugins/widget).
Почему так: виджету для запроса нужен токен, а refresh одноразовый — виджет,
обновивший сессию в фоне, выбил бы приложение из аккаунта.

Событие дня — `day_event.main_event`, своего отбора нет (так требует
докстринг day_event.py: пуш и виджет обязаны говорить одно). Заголовок и
совет — те же `title()` и `advice()`, что у утреннего пуша; время события
на виджете оставлено решением владельца 02.10.2026 (на карточке для сторис
его нет — та уходит в соцсети).

Синхронный модуль (Swiss Ephemeris): из async-ручки — через asyncio.to_thread.
"""
from __future__ import annotations

from datetime import date, timedelta

from backend import day_event, story_card

FLAG = "widget"
DAYS = 14

# День без главного события: заголовок — фаза, строка — совет фазы.
# Согласовано владельцем таблицей (docs/widget_phase_texts.md, ветка
# wip/tariffs-pdf): «ты», без рода, без предсказаний, до 60 знаков — как
# советы пуша. Фразы карточки для сторис сюда не годятся: они от первого лица.
PHASE_ADVICE = {
    "new_moon": "Тихий день: подумай, что хочешь начать.",
    "waxing_crescent": "Сделай первый маленький шаг к задуманному.",
    "first_quarter": "Не бросай начатое на первой трудности.",
    "waxing_gibbous": "Доведи до ума то, что уже в работе.",
    "full_moon": "Посмотри, что уже получилось, и порадуйся этому.",
    "waning_gibbous": "Поделись тем, что знаешь, с тем, кому это пригодится.",
    "last_quarter": "Убери одно лишнее: вещь, дело или обещание.",
    "waning_crescent": "Отдохни и не бери на себя новых дел.",
}


def _cap(s: str) -> str:
    # Не str.capitalize(): та опустила бы «Луна» в «растущая луна».
    return s[:1].upper() + s[1:]


def day(chart, local_date: date, tzname: str, daily_time, quiet_from) -> dict:
    ev = day_event.main_event(chart, local_date, tzname, daily_time, quiet_from)
    phase = story_card.moon_phase(local_date, tzname)
    if ev is not None and ev.natal is None:
        phase = ev.transit  # день новолуния/полнолуния называется так весь (как story_card.card)
    return {
        "date": local_date.isoformat(),
        "day": f"{local_date.day} {day_event._MONTHS_GEN[local_date.month]}",
        "phase": story_card.PHASES[phase][0],
        "elong": round(story_card.elongation(local_date, tzname), 1),
        "title": day_event.title(ev) if ev else _cap(story_card.PHASES[phase][0]),
        "advice": day_event.advice(ev) if ev else PHASE_ADVICE[phase],
    }


def days(user, chart, today: date) -> list[dict]:
    """DAYS дней с `today` (местная дата человека)."""
    from backend.week_ahead import _ctx

    ctx = _ctx(user, chart)
    return [day(chart, today + timedelta(days=i), *ctx) for i in range(DAYS)]
