"""Карточка дня для сторис — данные для картинки (флаг `story_card`).

Решение владельца 01.10.2026. Картинку рисует приложение на устройстве
(`frontend/src/mobile/lib/storyCard.js`), сервер отдаёт только то, что на ней
написано, и фигуру колеса. Событие дня — `day_event.main_event`, своего
отбора нет (так требует докстринг day_event.py).

Что на картинке НЕ бывает, и почему (решения владельца 01.10.2026):
  * время события и градусы: «15:01 · Луна к Луне» выдаёт градус натальной
    Луны до сотых, а с днём рождения из соцсети — и время рождения;
  * событие к Асценденту и MC: касание к ним выдаёт время рождения даже без
    названного времени. В такой день — фраза события, но вместо строки
    «Луна × …» только фаза Луны;
  * колесо с домами, знаками и планетами. Фигура аспектов — без подписей и
    повёрнута на угол, постоянный для карты и не связанный ни с Овном, ни с
    Асцендентом. ⚠️ Углы МЕЖДУ вершинами настоящие: перебором дат по ним
    дату рождения теоретически найти можно. Владелец принял это 01.10.2026,
    выбрав колесо «с фигурой»; убирать поворот нельзя — с ним фигура
    перестаёт читаться как положения в знаках.

Фразы согласованы владельцем таблицей (`docs/story_card_phrases.md`, ветка
wip/tariffs-pdf): первое лицо, без рода, до 32 знаков. Менять — только через
него; длину и повторы держит test_story_card.py.

Синхронный модуль (Swiss Ephemeris): из async-ручки — через asyncio.to_thread.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from backend import day_event
from backend.ephemeris.ru_names import PLANET_RU

FLAG = "story_card"
VARIANTS = ("chart", "photo")

# Натальная точка → (гармония, напряжение, начало). Тон — ASPECT_TONE движка,
# как у day_event.advice: трин/секстиль, квадрат/оппозиция, соединение.
STORY_PHRASE = {
    "Sun": ("Сегодня я делаю что-то для себя", "Я берегу силы для главного", "Я начинаю что-то своё"),
    "Moon": ("Сегодня мне уютно", "Я даю чувствам улечься", "Я слушаю, чего мне хочется"),
    "Mercury": ("Сегодня я на связи", "Я сначала думаю, потом пишу", "Я записываю свежие мысли"),
    "Venus": ("Сегодня я радую себя", "Я радуюсь без лишних трат", "Я окружаю себя красивым"),
    "Mars": ("Сегодня я действую", "Я выдыхаю, прежде чем ответить", "Я делаю первый шаг"),
    "Jupiter": ("Сегодня я говорю «да» новому", "Я не беру на себя лишнего", "Я расту шаг за шагом"),
    "Saturn": ("Сегодня я довожу дела до конца", "Я делаю по шагу и не тороплюсь", "Я закладываю прочный фундамент"),
    "Uranus": ("Сегодня я пробую по-новому", "Я меняю планы спокойно", "Я разрешаю себе перемены"),
    "Neptune": ("Сегодня я даю волю воображению", "Я проверяю, а не додумываю", "Я позволяю себе мечтать"),
    "Pluto": ("Сегодня я отпускаю старое", "Я не борюсь за контроль", "Я начинаю с чистого листа"),
    "Ascendant": ("Сегодня меня видно", "Я остаюсь собой", "Я пробую новый образ"),
    "Midheaven": ("Сегодня я иду к своей цели", "Я держу курс без спешки", "Я ставлю новую цель"),
}
# Ось узлов (таблица владельца 05.10.2026): к узлам только соединение и
# оппозиция, поэтому тонов два (day_event.NODE_ADVICE).
NODE_PHRASE = {"new_cycle": "Я иду туда, где расту", "tense": "Я отпускаю старые привычки"}
LUNATION_PHRASE = {
    "new_moon": "Я выбираю, с чего начать",
    "full_moon": "Я завершаю начатое",
}
# Фаза Луны: ключ → (подпись на картинке, фраза дня без события).
PHASES = {
    "new_moon": ("новолуние", "Я задумываю новое"),
    "waxing_crescent": ("растущий серп", "Я берусь за задуманное"),
    "first_quarter": ("первая четверть", "Я не сворачиваю с пути"),
    "waxing_gibbous": ("растущая Луна", "Я набираю силу"),
    "full_moon": ("полнолуние", "Я вижу, что получилось"),
    "waning_gibbous": ("убывающая Луна", "Я делюсь теплом"),
    "last_quarter": ("последняя четверть", "Я убираю лишнее"),
    "waning_crescent": ("убывающий серп", "Я отдыхаю и набираюсь сил"),
}
_TONE_INDEX = {"harmonious": 0, "tense": 1, "new_cycle": 2}
# Асцендент и MC выдают время рождения — на картинке их не называем.
_HIDDEN_NATAL = {"Ascendant", "Midheaven"}

# Фигура колеса: те же аспекты и орбы, что на наброске, согласованном владельцем.
_FIGURE_ASPECTS = {60: 5, 90: 6, 120: 6, 180: 7}
_FIGURE_PLANETS = ("Sun", "Moon", "Mercury", "Venus", "Mars",
                   "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")


# После точной фазы до следующей — промежуточная.
_AFTER = {"new_moon": "waxing_crescent", "first_quarter": "waxing_gibbous",
          "full_moon": "waning_gibbous", "last_quarter": "waning_crescent"}
_EXACT = tuple(_AFTER)


def moon_phase(local_date: date, tzname: str) -> str:
    """Фаза дня — ключ PHASES (решение владельца 04.10.2026, шаг 6 аудита).

    Точная фаза (новолуние, четверти, полнолуние) — только в МЕСТНЫЙ день её
    точного момента (lunar_engine.lunations), в остальные дни — промежуточная
    после последней точной. До этого — 8 секторов элонгации в полдень:
    «новолуние» стояло 3–4 дня подряд и расходилось с лентой и календарём
    (проверка c5 прогона согласованности). Виджет, сторис и
    `/calendar/lunar` `daily_signs[].phase` берут фазу только отсюда.
    """
    from backend.calendar.lunar_engine import lunations, lunations_local
    from backend.time_utils import local_day

    today = lunations_local(local_date, local_date, tzname, types=_EXACT)
    if today:
        return today[0].type
    start = local_day(local_date, tzname)[0]
    # Между точными фазами ≤ 8 суток — 9 хватает.
    prev = lunations(start - timedelta(days=9), start, types=_EXACT)
    return _AFTER[prev[-1].type]


def elongation(local_date: date, tzname: str) -> float:
    """Элонгация Луны от Солнца в местный полдень, 0…360 (0 — новолуние).
    Виджет рисует по ней картинку фазы (backend/widget.py)."""
    from backend.calendar.lunar_engine import _jd, _lon

    noon = datetime.combine(local_date, time(12), ZoneInfo(tzname)).astimezone(timezone.utc)
    jd = _jd(noon.date(), noon.hour + noon.minute / 60)
    return (_lon(jd, "Moon") - _lon(jd, "Sun")) % 360


def phrase(ev: day_event.DayEvent | None, phase: str) -> str:
    if ev is None:
        return PHASES[phase][1]
    if ev.natal is None:
        return LUNATION_PHRASE[ev.transit]
    from backend.transit.engine import ASPECT_TONE
    tone = ASPECT_TONE.get(ev.aspect, "tense")
    if ev.natal == day_event.NODE:
        return NODE_PHRASE[tone]
    return STORY_PHRASE[ev.natal][_TONE_INDEX[tone]]


# Планета касается самой себя — «Луна × моя Луна» (решение владельца
# 02.10.2026): «Луна × Луна» читалось как опечатка. Род — по слову.
_MY = {
    "Sun": "моё Солнце", "Moon": "моя Луна", "Mercury": "мой Меркурий",
    "Venus": "моя Венера", "Mars": "мой Марс", "Jupiter": "мой Юпитер",
    "Saturn": "мой Сатурн", "Uranus": "мой Уран", "Neptune": "мой Нептун",
    "Pluto": "мой Плутон",
}


def event_label(ev: day_event.DayEvent | None) -> str | None:
    """«Луна × Венера» — без времени и без «твоей»; к самой себе — «Луна ×
    моя Луна». Новолуние/полнолуние, Асцендент и MC — None: первое и так
    назовёт фаза, вторые не называются."""
    if ev is None or ev.natal is None or ev.natal in _HIDDEN_NATAL:
        return None
    if ev.natal == day_event.NODE:
        return f"{PLANET_RU[ev.transit]} × ось узлов"
    natal = _MY[ev.natal] if ev.natal == ev.transit else PLANET_RU[ev.natal]
    return f"{PLANET_RU[ev.transit]} × {natal}"


def figure(chart) -> dict:
    """Вершины фигуры аспектов (углы, градусы) и линии (пары индексов).

    Поворот постоянен для карты — картинка не «пляшет» изо дня в день — и
    выводится из её id, а не из Асцендента или Овна. Карта без времени — без
    Луны, как в day_event._targets: её положение сдвинуто до ±6°.
    """
    # usedforsecurity=False: хеш здесь — только устойчивое число из id, не защита
    # (bandit B324 иначе валит job security).
    rot = int(hashlib.sha1(str(chart.id).encode(), usedforsecurity=False).hexdigest()[:8], 16) % 360
    from backend.chart_points import planets
    lon = {p["name"]: p["longitude"] for p in planets(chart) if p["name"] in _FIGURE_PLANETS}
    names = [n for n in _FIGURE_PLANETS if n in lon]
    pairs = []
    for i, a in enumerate(names):
        for j in range(i + 1, len(names)):
            d = abs(lon[a] - lon[names[j]]) % 360
            d = min(d, 360 - d)
            if any(abs(d - asp) <= orb for asp, orb in _FIGURE_ASPECTS.items()):
                pairs.append((i, j))
    used = sorted({k for p in pairs for k in p})
    index = {old: new for new, old in enumerate(used)}
    return {
        "points": [round((lon[names[k]] + rot) % 360, 1) for k in used],
        "lines": [[index[i], index[j]] for i, j in pairs],
    }


def card(user, chart, local_date: date) -> dict:
    from backend.week_ahead import _ctx

    tzname, daily_time, quiet_from = _ctx(user, chart)
    ev = day_event.main_event(chart, local_date, tzname, daily_time, quiet_from)
    phase = moon_phase(local_date, tzname)
    if ev is not None and ev.natal is None:
        phase = ev.transit  # день новолуния/полнолуния называется так, даже если в полдень уже «серп»
    return {
        "date": local_date.isoformat(),
        "phrase": phrase(ev, phase),
        "event": event_label(ev),
        "phase": PHASES[phase][0],
        "figure": figure(chart),
    }
