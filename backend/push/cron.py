"""Планировщик уведомлений: отбор событий и их отправка.

⚠️ Кто это запускает. Тик крутит ВНУТРЕННИЙ планировщик приложения —
`_scheduler_loop` в `backend/main.py`, раз в 15 минут, в том же процессе, что
держит HTTP-сервер. Ручка `POST /api/v1/internal/push-tick` существует как
запасной вход (за `require_internal_secret`), но ни один cron её сегодня не
дёргает: в `deploy/opt-astro/09-internal-cron.sh` перечислены только
только `pilot-tick` (`onboarding-emails` снят 23.09.2026, письма перешли в Beat).

(До 10.09.2026 здесь было написано «Вызывается Railway Cron каждые ~15 минут».
Railway в проекте нет и не было ни одного дня этой кодовой базы; строка
пережила переезд и вводила в заблуждение ровно в том месте, куда идут искать
источник расписания.)

Для каждого пользователя с активной подпиской, по его ГЛАВНОЙ карте
(primary_chart_id), в его локальное время (tz главной карты) собираются
шесть видов событий — `_collect_candidates`:
  1) `daily`            — ежедневный прогноз;
  2) `planner`          — период планеты начинается сегодня;
  3) `planner_week` / `planner_month` — упреждение за 7 и за 30 дней;
  4) `transit`          — значимый транзит вошёл в орб сегодня;
  5) `transit_approach` / `cusp_approach` — медленная планета за 4° на сближении;
  6) `triple`           — точное касание с номером захода (директ→ретро→директ);
  7) `moon`             — новолуние или полнолуние завтра.

Отправляются они в окне пользователя между `push_daily_time` и
`push_quiet_from` (см. `in_send_window` — обе границы там, второй копии
правила нет) и дедуплицируются через `push_sent_log`: одно событие — один пуш.

⚠️ **`push_daily_time` — это «НЕ РАНЬШЕ», а не «в это время».** Правильное
поведение здесь выглядит как баг, поэтому записано отдельно.

Тик крутится раз в 15 минут, и сетка тиков привязана к МОМЕНТУ СТАРТА
процесса `api`, а не к часам: `_scheduler_loop` (`main.py`) делает
`sleep(60)` после подъёма, дальше `sleep(15 * 60)` ПОСЛЕ каждого тика — то
есть шаг плывёт на длительность самого тика, а любой деплой
(`docker compose up -d api`) переставляет сетку заново. Отсюда три следствия,
и все три — норма, а не отказ:

1. уведомление уходит ПЕРВЫМ тиком после наступления `push_daily_time`, то
   есть с запаздыванием до ~15 минут;
2. минута отправки НЕ повторяется изо дня в день и после деплоя сдвигается;
3. поэтому нигде — ни в интерфейсе, ни в письмах — нельзя обещать «в
   выбранное время». Честная формулировка «начиная с выбранного времени»;
   ровно так и подписан экран уведомлений в приложении
   (`MoreNotificationsView.jsx`, `MoreDeviceChannel.jsx`).

Это та же оговорка, что уже действует для локальных уведомлений на устройстве
(CLAUDE.md: «нигде нельзя обещать показ „через N минут“ — только „не
раньше“»), но причина у неё ДРУГАЯ: там неточный будильник Android, здесь —
привязка тика к старту процесса. Чинится это отдельной задачей (TASKS.md,
«Рассылка уведомлений привязана к старту процесса»), и до тех пор менять
формулировки на точные нельзя.

Тот же `_collect_candidates` обслуживает `collect_upcoming` — выдачу будущих
событий мобильному клиенту (`GET /api/v1/push/upcoming`). Отбор и тексты
существуют в одном экземпляре намеренно, см. докстринг той функции.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, date as date_type, timedelta
from backend.time_utils import utcnow

import pytz
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.authz import require_internal_secret
from backend.database import get_db
from backend.models import User, NatalChart, PushSubscription, PushSentLog
from backend.push.sender import send_to_user
from backend.chart_utils import get_primary_chart
from backend.ephemeris.ru_names import PLANET_RU

logger = logging.getLogger("astro.push.cron")

# Секрет проверяется на уровне роутера — см. backend/authz.require_internal_secret.
router = APIRouter(
    prefix="/api/v1/internal",
    tags=["internal"],
    dependencies=[Depends(require_internal_secret)],
)

DEFAULT_TZ = "Europe/Moscow"

FAST_PLANETS = ("Sun", "Mercury", "Venus", "Mars")
SLOW_PLANETS = ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")
MEDIUM_PLANETS = ("Mercury", "Venus", "Mars")

# E5/E6 — мягкие пуши (шум): ограничиваются потолком 1/48ч, вливаются в событийный.
SOFT_KINDS = {"daily", "moon"}
SOFT_CAP_HOURS = 48
ADVANCE_MONTH_DAYS = 30   # упреждение «большого периода» (медленные планеты)
ADVANCE_WEEK_DAYS = 7     # упреждение среднего периода (Венера/Марс/Меркурий)


# ── Окно отправки ──
# Нижняя граница — push_daily_time, верхняя — push_quiet_from. Обе читаются
# ЗДЕСЬ и больше нигде: правило одно на планировщик веб-пушей
# (_process_user) и на выдачу будущих событий мобильному клиенту
# (collect_upcoming). Вторая реализация этой проверки — тот класс дефекта,
# из-за которого в проекте уже расходились письма с флагами тарифов.
DEFAULT_DAILY_TIME = "08:00"
DEFAULT_QUIET_FROM = "22:00"


def _parse_hm(value, fallback: tuple[int, int]) -> tuple[int, int]:
    """"HH:MM" -> (h, m). Мусор и None дают fallback, а не исключение:
    настройка приходит из БД, и кривое значение не должно ронять тик для
    всех остальных пользователей."""
    try:
        h_s, m_s = str(value).split(":")
        h, m = int(h_s), int(m_s)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except Exception:
        pass
    return fallback


def _daily_time_of(user) -> str:
    return str(getattr(user, "push_daily_time", DEFAULT_DAILY_TIME) or DEFAULT_DAILY_TIME)


def _quiet_from_of(user) -> str:
    return str(getattr(user, "push_quiet_from", DEFAULT_QUIET_FROM) or DEFAULT_QUIET_FROM)


def in_send_window(moment_local: datetime, daily_time, quiet_from) -> bool:
    """Попадает ли локальный момент в окно, когда человека можно беспокоить.

    ⚠️ До 10.09.2026 верхней границы не существовало: проверялось только
    «локальное время уже наступило». Тик в 23:45 это условие проходил.
    Ночью не будило лишь потому, что дневное событие к тому моменту обычно
    уже отправлено и отсеяно дедупом, — то есть держалось на побочном
    эффекте, а не на правиле. Подписавшийся вечером получал пуш сразу.

    ⚠️ Бессмысленная пара (верх не позже низа) трактуется как «верхней
    границы нет», а не как пустое окно. Пустое окно означало бы, что кривая
    настройка молча выключает уведомления совсем, и снаружи это неотличимо
    от сломанного планировщика. Поздний пуш заметен и лечится, тишина —
    нет. Ввод при этом проверяется на входе (PATCH /push/settings), так что
    состояние это аварийное, а не рабочее.
    """
    start = _parse_hm(daily_time, _parse_hm(DEFAULT_DAILY_TIME, (8, 0)))
    end = _parse_hm(quiet_from, _parse_hm(DEFAULT_QUIET_FROM, (22, 0)))
    hm = (moment_local.hour, moment_local.minute)
    if hm < start:
        return False
    if end <= start:
        return True
    return hm < end


# ── Дедупликация ──
def _already_sent(db: Session, user_id: str, kind: str, ref_key: str) -> bool:
    return db.query(PushSentLog).filter(
        PushSentLog.user_id == user_id,
        PushSentLog.kind == kind,
        PushSentLog.ref_key == ref_key,
    ).first() is not None


def _mark_sent(db: Session, user_id: str, kind: str, ref_key: str) -> None:
    db.add(PushSentLog(user_id=user_id, kind=kind, ref_key=ref_key[:128]))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # уже отмечено параллельным тиком


def _soft_capped(db: Session, user_id: str, now_utc: datetime) -> bool:
    """True, если мягкий пуш уже был за последние SOFT_CAP_HOURS (потолок шума)."""
    last = (
        db.query(PushSentLog)
        .filter(PushSentLog.user_id == user_id, PushSentLog.kind.in_(list(SOFT_KINDS)))
        .order_by(PushSentLog.sent_at.desc())
        .first()
    )
    if last and last.sent_at and (now_utc - last.sent_at) < timedelta(hours=SOFT_CAP_HOURS):
        return True
    return False


def _period_starts_on(planet: str, cusps: list[float], target: date_type) -> list[int]:
    """Номера домов, в которые планета входит именно в дату `target`."""
    from backend.transit.house_passages import calculate_house_passages
    win_start = datetime(target.year, target.month, target.day) - timedelta(days=1)
    win_end = datetime(target.year, target.month, target.day) + timedelta(days=1, hours=23)
    out = []
    for p in calculate_house_passages(planet, cusps, win_start, win_end):
        if p["start_dt"].date() == target:
            out.append(p["house"])
    return out


# ── Фаза 2: транзит «за 4° applying» ──
PERSONAL_NATAL = ("Sun", "Moon", "Mercury", "Venus", "Mars")
APPLYING_ORB = 4.0


def _lon_on(planet: str, d: date_type) -> float:
    from backend.transit.engine import PLANETS, _calc_planet_position, _datetime_to_jd
    jd = _datetime_to_jd(datetime(d.year, d.month, d.day, 12, 0))
    lon, _, _, _ = _calc_planet_position(PLANETS[planet], round(jd, 6))
    return lon


def _four_degree_candidates(chart: NatalChart, today: date_type, planner_url: str) -> list[dict]:
    """Медленная планета подходит на 4° (applying) к аспекту с личной планетой
    ИЛИ к куспиду дома. Срабатывает один раз — в день пересечения порога 4°.
    """
    from backend.transit.engine import ASPECTS, _angular_distance, NATAL_SPHERE
    from backend.transit.forecast_prompt import HOUSE_SPHERE_MAP
    from backend.transit.house_passages import _extract_cusps

    yday = today - timedelta(days=1)
    natal = {p["name"]: p["longitude"] for p in (chart.planets or []) if p.get("name") in PERSONAL_NATAL}
    cusps = _extract_cusps({"houses": chart.houses})
    has_houses = not all(c == 0.0 for c in cusps)

    out: list[dict] = []
    for tp in SLOW_PLANETS:
        try:
            lt_t = _lon_on(tp, today)
            lt_y = _lon_on(tp, yday)
        except Exception:
            continue
        pr = PLANET_RU.get(tp, tp)

        # аспект к личной планете
        for npl, nlon in natal.items():
            nr = PLANET_RU.get(npl, npl)
            for aspect, exact in ASPECTS.items():
                orb_t = abs(_angular_distance(lt_t, nlon) - exact)
                orb_y = abs(_angular_distance(lt_y, nlon) - exact)
                if orb_t <= APPLYING_ORB < orb_y:  # пересёк 4° на сближении
                    sphere = _sphere_short(NATAL_SPHERE.get((tp, npl)))
                    if sphere:
                        frag = f"{pr} → {sphere}"
                        body = f"{pr} подходит к теме «{sphere}» — на горизонте важное движение. Понаблюдайте, что откликается."
                    else:
                        frag = f"{pr} подходит к {nr}"
                        body = f"{pr} подходит к вашему {nr} — на горизонте важное движение. Понаблюдайте, что откликается."
                    out.append({
                        "kind": "transit_approach",
                        "ref": f"4deg:{tp}:{npl}:{aspect}:{today.isoformat()}",
                        "priority": "significant", "weight": 95,
                        "frag": frag,
                        "title": "✦ Открывается окно",
                        "body": body,
                        "url": _with_topic(planner_url, _topic_key("approach", planet=tp, aspect=aspect, natal=npl)),
                    })

        # приближение к куспиду дома (вход в новую сферу)
        if has_houses:
            for idx, cusp in enumerate(cusps):
                house = idx + 1
                d_t = _angular_distance(lt_t, cusp)
                d_y = _angular_distance(lt_y, cusp)
                if d_t <= APPLYING_ORB < d_y:
                    sphere_name = HOUSE_SPHERE_MAP.get(house, {}).get("name")
                    if sphere_name:
                        frag = f"{pr} → {sphere_name}"
                        body = f"{pr} приближается к дому «{sphere_name}» — скоро откроется эта сфера жизни. Стоит присмотреться заранее."
                    else:
                        frag = f"{pr} готовит перемены"
                        body = f"{pr} приближается к важному порогу — скоро откроется новая сфера жизни."
                    out.append({
                        "kind": "cusp_approach",
                        "ref": f"4deg_cusp:{tp}:{house}:{today.isoformat()}",
                        "priority": "significant", "weight": 95,
                        "frag": frag,
                        "title": "✦ Новая сфера открывается",
                        "body": body,
                        "url": _with_topic(planner_url, _topic_key("cusp_approach", planet=tp, house=house)),
                    })
    return out


# ── Фаза 3: троичное касание ретро (директ → ретро → директ) ──
EXACT_TOUCH_ORB = 0.3     # порог «точного» касания в градусах
TRIPLE_SCAN_DAYS = 300    # окно назад для подсчёта номера захода

# {sphere} подставляется из NATAL_SPHERE (engine.py), если пара
# (transit_planet, natal_planet) там есть — иначе берётся _TRIPLE_MSG_FALLBACK
# с тем же смыслом, но без названия сферы.
_TRIPLE_MSG = {
    1: ("✦ Ваша тема открывается", "открывается {sphere} — эта тема ещё вернётся к вам"),
    2: ("✦ Тема возвращается", "{sphere} возвращается — время пересмотреть то, что начали"),
    3: ("✦ Тема закрывается", "{sphere} закрывается и закрепляется — время подвести итог"),
}
_TRIPLE_MSG_FALLBACK = {
    1: "открывается тема, которая ещё вернётся к вам",
    2: "тема возвращается — время пересмотреть то, что начали",
    3: "тема закрывается и закрепляется — время подвести итог",
}


def _count_touches_until(tp: str, nlon: float, exact_angle: float, today: date_type) -> int:
    """Сколько раз аспект точно совпал за окно [today-300, today] включительно."""
    from backend.transit.engine import _angular_distance
    prev_sign = None
    crossings = 0
    d = today - timedelta(days=TRIPLE_SCAN_DAYS)
    end = today + timedelta(days=1)
    while d <= end:
        try:
            diff = _angular_distance(_lon_on(tp, d), nlon) - exact_angle
        except Exception:
            d += timedelta(days=2)
            continue
        sign = 1 if diff >= 0 else -1
        if prev_sign is not None and sign != prev_sign:
            crossings += 1
        prev_sign = sign
        d += timedelta(days=2)
    return max(1, min(crossings, 3))


def _triple_touch_candidates(chart: NatalChart, today: date_type, planner_url: str) -> list[dict]:
    """Точное касание медленной планетой аспекта к личной планете сегодня —
    с номером захода (1/2/3) для сценария директ→ретро→директ.
    """
    from backend.transit.engine import ASPECTS, _angular_distance, NATAL_SPHERE

    yday = today - timedelta(days=1)
    tmrw = today + timedelta(days=1)
    natal = {p["name"]: p["longitude"] for p in (chart.planets or []) if p.get("name") in PERSONAL_NATAL}

    out: list[dict] = []
    for tp in SLOW_PLANETS:
        try:
            lt_y = _lon_on(tp, yday)
            lt_t = _lon_on(tp, today)
            lt_m = _lon_on(tp, tmrw)
        except Exception:
            continue
        pr = PLANET_RU.get(tp, tp)
        for npl, nlon in natal.items():
            nr = PLANET_RU.get(npl, npl)
            for aspect, exact in ASPECTS.items():
                orb_y = abs(_angular_distance(lt_y, nlon) - exact)
                orb_t = abs(_angular_distance(lt_t, nlon) - exact)
                orb_m = abs(_angular_distance(lt_m, nlon) - exact)
                # точное касание сегодня = локальный минимум ниже порога
                if orb_t <= EXACT_TOUCH_ORB and orb_t <= orb_y and orb_t <= orb_m:
                    phase = _count_touches_until(tp, nlon, exact, today)
                    title, tail_template = _TRIPLE_MSG.get(phase, _TRIPLE_MSG[1])
                    sphere = _sphere_short(NATAL_SPHERE.get((tp, npl)))
                    tail = tail_template.format(sphere=sphere) if sphere else _TRIPLE_MSG_FALLBACK.get(phase, _TRIPLE_MSG_FALLBACK[1])
                    out.append({
                        "kind": "triple",
                        "ref": f"triple:{tp}:{npl}:{aspect}:{today.isoformat()}",
                        "priority": "significant", "weight": 98,
                        "frag": f"{pr} и {nr}: {tail}",
                        "title": title,
                        "body": f"{pr} и ваш {nr} — {tail}.",
                        "url": _with_topic(planner_url, _topic_key(f"triple{phase}", planet=tp, aspect=aspect, natal=npl)),
                    })
    return out


# ── Тексты ──
def _daily_body(chart: NatalChart, today: date_type) -> str:
    """Короткий тизер прогноза на день из активных транзитов (без жаргона).

    На «ты» — как и сам прогноз в приложении (решение владельца 23.09.2026).
    Текст прогноза сюда НЕ кладётся: он генерируется при первом открытии
    карточки «Сегодня» (backend/forecast/), а уведомление только зовёт к ней.
    """
    try:
        from backend.transit.engine import calculate_transits
        events = calculate_transits(
            natal_planets=chart.planets, from_date=today, to_date=today
        )
        best = None
        for e in events:
            if e.aspect_type in ("trine", "sextile", "conjunction"):
                best = e
                break
        best = best or (events[0] if events else None)
        if best:
            if best.aspect_type in ("trine", "sextile", "conjunction"):
                return "Сегодня многое складывается чуть легче обычного. Загляни в прогноз."
            return "Сегодня активный день — его стоит прожить осознанно. Загляни в прогноз."
    except Exception as e:
        logger.warning("daily body build failed: %s", e)
    return "Твой прогноз на сегодня готов."


def _sphere_short(sphere: str | None) -> str | None:
    """Первая смысловая часть значения NATAL_SPHERE (engine.py) — коротко для
    пуша, та же обрезка, что в engine._build_transit_alert_subject."""
    if not sphere:
        return None
    return sphere.split(" — ")[0].split(",")[0]


# Текст «важного транзита» по тону аспекта (ASPECT_TONE в engine.py) — со
# сферой, если пара (transit_planet, natal_planet) есть в NATAL_SPHERE, иначе
# фолбэк без названия сферы. Короче email-версии (DESCRIPTION_TEMPLATES) —
# те же данные (сфера/тон), не те же предложения, пуш не должен быть длиннее.
_TRANSIT_TONE_TITLE = {
    "harmonious": "✦ Окно открылось",
    "tense":      "✦ Проверка на прочность",
    "new_cycle":  "✦ Новый цикл",
}
_TRANSIT_TONE_BODY = {
    "harmonious": "{planet} поддерживает тему «{sphere}» — хороший момент сделать конкретный шаг именно здесь.",
    "tense":      "{planet} создаёт напряжение в теме «{sphere}» — не время торопиться, но стоит обратить внимание.",
    "new_cycle":  "{planet} запускает новый цикл в теме «{sphere}» — то, что начнёте сейчас, определит эту сферу надолго.",
}
_TRANSIT_TONE_FALLBACK = {
    "harmonious": "{planet} активирует один из благоприятных периодов в вашей карте — момент сделать шаг в важной для вас сфере.",
    "tense":      "{planet} требует осознанности и терпения — не время торопиться, лучше укрепить то, что важно.",
    "new_cycle":  "{planet} запускает новый цикл в вашей карте — обратите внимание, что начинается сейчас.",
}


def _transit_entry_candidates(chart: NatalChart, today: date_type, planner_url: str) -> list[dict]:
    """Значимый транзит ВОШЁЛ в орб сегодня: вчера орб был больше предела,
    сегодня — не больше.

    ⚠️ Здесь нельзя спрашивать у движка дату начала транзита, и это главное,
    что надо знать про этот блок. `calculate_transits` ОБРЕЗАЕТ `start_date`
    окном запроса: скан начинается с `from_date`, и уже открытое к этому
    моменту окно получает `start_date == from_date`. Проверено исполнением
    10.09.2026 — Сатурн в квадрате к Нептуну отдаёт `start=2026-09-11` в окне
    того дня и `start=2026-09-12` в окне следующего, будучи одним и тем же
    транзитом.

    До 10.09.2026 отбор был устроен как `e.start_date == today.isoformat()`,
    поэтому под условие «начался сегодня» попадал ЛЮБОЙ идущий транзит.
    Дата внутри ключа дедупа при этом менялась каждый день, `push_sent_log`
    его не гасил — и человек получал одно и то же уведомление КАЖДОЕ УТРО всё
    время действия транзита. У медленных планет это недели и месяцы.

    ⚠️ Расширить окно запроса вместо этого нельзя: глубина должна покрывать
    всю длительность транзита, а коридор орба в 4° (`TRANSIT_ORBS`, 2° на
    соединение) Нептун проходит примерно за два года. Замер 10.09.2026: окно
    в один день — 0.05 с, окно в год — 5.18 с, при том что тик крутится каждые
    15 минут по всем подписанным. Годового окна Нептуну всё равно мало.

    Сравнение двух дней и дешевле нынешнего скана (восемь обращений к
    эфемеридам против сканирования четырёх суток шагом 4 часа), и даёт
    НАСТОЯЩУЮ дату входа — а значит устойчивый ключ дедупа. Приём не новый:
    ровно так устроены `_four_degree_candidates` и `_triple_touch_candidates`
    ниже, это распространение существующего решения на четвёртый блок.

    ⚠️ Ретроградность даёт законные повторные входы: планета выходит из орба
    и возвращается — будет второе уведомление за период. Это верно по сути
    (транзит действительно возобновился) и согласуется с отдельным видом
    `triple`, который считает заходы явно.

    Тексты, вес и формат `ref` не менялись — только момент срабатывания.
    """
    from backend.transit.engine import (
        ASPECTS, TRANSIT_ORBS, ALERT_PLANETS, ASPECT_TONE, NATAL_SPHERE,
        _angular_distance,
    )

    yday = today - timedelta(days=1)
    natal = {
        p["name"]: p["longitude"]
        for p in (chart.planets or [])
        if p.get("name") and p.get("longitude") is not None
    }

    # Не больше одного кандидата на транзитную планету в день — иначе
    # несколько аспектов одной планеты дают несколько одинаковых фрагментов
    # в склейке («Юпитер · Юпитер · Юпитер»). Из группы берём самый точный
    # орб — самое значимое событие. Правило перенесено из прежнего блока
    # без изменений.
    best: dict[str, tuple[float, str, str]] = {}

    for tp in sorted(ALERT_PLANETS):
        try:
            lon_t = _lon_on(tp, today)
            lon_y = _lon_on(tp, yday)
        except Exception:
            continue
        for npl, nlon in natal.items():
            for aspect, exact in ASPECTS.items():
                limit = TRANSIT_ORBS[aspect]
                orb_t = abs(_angular_distance(lon_t, nlon) - exact)
                orb_y = abs(_angular_distance(lon_y, nlon) - exact)
                if orb_t <= limit < orb_y:  # вошёл в орб именно сегодня
                    cur = best.get(tp)
                    if cur is None or orb_t < cur[0]:
                        best[tp] = (orb_t, npl, aspect)

    out: list[dict] = []
    for tp, (_orb, npl, aspect) in best.items():
        pr = PLANET_RU.get(tp, tp)
        tone = ASPECT_TONE.get(aspect, "tense")
        sphere = _sphere_short(NATAL_SPHERE.get((tp, npl)))
        if sphere:
            frag = f"{pr}: {sphere}"
            body = _TRANSIT_TONE_BODY[tone].format(planet=pr, sphere=sphere)
        else:
            frag = f"{pr} активен в карте"
            body = _TRANSIT_TONE_FALLBACK[tone].format(planet=pr)
        out.append({
            "kind": "transit",
            "ref": f"{tp}:{npl}:{aspect}:{today.isoformat()}",
            "priority": "significant", "weight": 90, "frag": frag,
            "title": _TRANSIT_TONE_TITLE[tone],
            "body": body,
            "url": _with_topic(planner_url, _topic_key("transit", planet=tp, aspect=aspect, natal=npl)),
        })
    return out


# ── Слой 3: тема для проактивного чата ──
# Компактный ключ темы, который прокидывается в URL пуша как ?astrea=<topic>.
# ChartPage/PlannerPage читают его и просят RagChat начать разговор первой репликой.
def _topic_key(kind: str, planet: str | None = None, house: int | None = None,
               aspect: str | None = None, natal: str | None = None) -> str:
    parts = [kind]
    if planet: parts.append(planet.lower().replace(" ", "_"))
    if aspect: parts.append(aspect)
    if natal:  parts.append(natal.lower().replace(" ", "_"))
    if house:  parts.append(f"h{house}")
    return "-".join(parts)


def _with_topic(url: str, topic: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}astrea={topic}"


# ── Сбор кандидатов на пуш (без отправки) ──
def _collect_candidates(db: Session, user: User, chart: NatalChart, today: date_type) -> list[dict]:
    """Список событий-кандидатов на сегодня. Каждый:
      {kind, ref, priority(soft/significant), weight, frag, title, body, url}
    frag — короткий фрагмент для агрегированного пуша; weight — порядок значимости.
    """
    cands: list[dict] = []
    planner_url = f"/planner/{chart.id}"

    # 1) Ежедневный прогноз (soft)
    if getattr(user, "push_daily_forecast", True):
        cands.append({
            "kind": "daily", "ref": today.isoformat(),
            "priority": "soft", "weight": 10, "frag": "прогноз на день",
            "title": "✦ Твой день сегодня", "body": _daily_body(chart, today),
            # url — для веб-пуша, его не трогаем (веб в этой задаче не
            # меняется). Приложение ведёт по target: открыть ленту и
            # развернуть карточку «Сегодня» (решение владельца 23.09.2026).
            "url": _with_topic(f"/chart/{chart.id}", _topic_key("daily")),
            "target": "feed_today",
        })

    # Планер (significant): старт сегодня + упреждение неделя/месяц
    if getattr(user, "push_planner", True):
        try:
            from backend.transit.forecast_prompt import HOUSE_SPHERE_MAP
            from backend.transit.house_passages import _extract_cusps
            cusps = _extract_cusps({"houses": chart.houses})
            if not all(c == 0.0 for c in cusps):
                # 2) старт периода быстрой планеты сегодня
                for planet in FAST_PLANETS:
                    for house in _period_starts_on(planet, cusps, today):
                        pr = PLANET_RU.get(planet, planet)
                        sphere_name = HOUSE_SPHERE_MAP.get(house, {}).get("name")
                        if sphere_name:
                            frag = f"{pr}: {sphere_name}"
                            body = f"{pr} открывает новый период — в фокусе {sphere_name.lower()}. Загляните в планер, чтобы понять, что делать дальше."
                        else:
                            frag = f"новый период {pr}"
                            body = f"{pr} открывает новый период в вашем плане — загляните, что это значит."
                        cands.append({
                            "kind": "planner", "ref": f"{planet}:{house}:{today.isoformat()}",
                            "priority": "significant", "weight": 60, "frag": frag,
                            "title": "✦ Начался ваш период",
                            "body": body,
                            "url": _with_topic(planner_url, _topic_key("planner_start", planet=planet, house=house)),
                        })
                # 3) за неделю — средние планеты (Венера/Марс/Меркурий)
                wk = today + timedelta(days=ADVANCE_WEEK_DAYS)
                for planet in MEDIUM_PLANETS:
                    for house in _period_starts_on(planet, cusps, wk):
                        pr = PLANET_RU.get(planet, planet)
                        sphere_name = HOUSE_SPHERE_MAP.get(house, {}).get("name")
                        if sphere_name:
                            frag = f"через неделю: {sphere_name}"
                            body = f"Через неделю открывается период в сфере «{sphere_name}» — {pr} задаёт тон. Есть время подготовиться заранее."
                        else:
                            frag = f"скоро период {pr}"
                            body = f"Через неделю начнётся заметный период — {pr} задаёт тон. Загляните в планер заранее."
                        cands.append({
                            "kind": "planner_week", "ref": f"{planet}:{house}:{wk.isoformat()}",
                            "priority": "significant", "weight": 70, "frag": frag,
                            "title": "✦ Через неделю — новое окно",
                            "body": body,
                            "url": _with_topic(planner_url, _topic_key("planner_week", planet=planet, house=house)),
                        })
                # 4) за месяц — медленные планеты (большой период)
                mo = today + timedelta(days=ADVANCE_MONTH_DAYS)
                for planet in SLOW_PLANETS:
                    for house in _period_starts_on(planet, cusps, mo):
                        pr = PLANET_RU.get(planet, planet)
                        sphere_name = HOUSE_SPHERE_MAP.get(house, {}).get("name")
                        if sphere_name:
                            frag = f"через месяц: {sphere_name}"
                            body = f"Через месяц открывается долгий период в сфере «{sphere_name}» — {pr} задаёт тон на годы вперёд. Стоит спланировать заранее."
                        else:
                            frag = f"скоро большой период {pr}"
                            body = f"Через месяц открывается долгий период под влиянием {pr} — стоит спланировать заранее."
                        cands.append({
                            "kind": "planner_month", "ref": f"{planet}:{house}:{mo.isoformat()}",
                            "priority": "significant", "weight": 100, "frag": frag,
                            "title": "✦ Через месяц — важный период",
                            "body": body,
                            "url": _with_topic(planner_url, _topic_key("planner_month", planet=planet, house=house)),
                        })
        except Exception as e:
            logger.warning("planner candidates failed user=%s: %s", user.id, e)

    # 5) Важные транзиты — вход значимого транзита в орб сегодня (significant)
    if getattr(user, "push_key_transits", True):
        try:
            cands.extend(_transit_entry_candidates(chart, today, planner_url))
        except Exception as e:
            logger.warning("transit candidates failed user=%s: %s", user.id, e)

        # Фаза 2: медленная планета «за 4° applying» к аспекту/куспиду
        try:
            cands.extend(_four_degree_candidates(chart, today, planner_url))
        except Exception as e:
            logger.warning("4deg candidates failed user=%s: %s", user.id, e)

        # Фаза 3: точное касание с номером захода (директ→ретро→директ)
        try:
            cands.extend(_triple_touch_candidates(chart, today, planner_url))
        except Exception as e:
            logger.warning("triple-touch candidates failed user=%s: %s", user.id, e)

    # 6) Новолуние/полнолуние — за день (soft)
    if getattr(user, "push_moon_phases", False):
        try:
            from backend.calendar.lunar_engine import get_moon_phases
            tomorrow = today + timedelta(days=1)
            for phase in get_moon_phases(tomorrow.year, tomorrow.month):
                if phase.date != tomorrow.isoformat():
                    continue
                label = "🌑 Новолуние" if phase.type == "new_moon" else "🌕 Полнолуние"
                cands.append({
                    "kind": "moon", "ref": f"moon:{phase.type}:{phase.date}",
                    "priority": "soft", "weight": 30, "frag": f"{label} завтра",
                    "title": f"{label} завтра",
                    "body": "Хорошее время заметить, что вы на самом деле чувствуете. Загляните в лунный календарь.",
                    "url": _with_topic("/lunar", _topic_key("moon", planet=phase.type)),
                })
        except Exception as e:
            logger.warning("moon candidates failed user=%s: %s", user.id, e)

    return cands


# ── Основная логика по одному пользователю ──
def _process_user(db: Session, user: User) -> int:
    chart = get_primary_chart(db, user)
    if not chart:
        logger.info("push skip user=%s: no primary chart", user.id)
        return 0  # без главной карты уведомлять не по чему

    tzname = getattr(chart, "timezone", None) or DEFAULT_TZ
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone(DEFAULT_TZ)

    now_local = datetime.now(pytz.utc).astimezone(tz)
    today = now_local.date()

    # Окно отправки целиком — обе границы считает in_send_window (см. её
    # докстринг: до 10.09.2026 верхней границы не было вовсе).
    if not in_send_window(now_local, _daily_time_of(user), _quiet_from_of(user)):
        logger.info(
            "push skip user=%s: вне окна %s-%s (локально %s)",
            user.id, _daily_time_of(user), _quiet_from_of(user),
            now_local.strftime("%H:%M"),
        )
        return 0

    # Сбор + отсев уже отправленного
    cands = [
        c for c in _collect_candidates(db, user, chart, today)
        if not _already_sent(db, user.id, c["kind"], c["ref"])
    ]
    if not cands:
        logger.info("push skip user=%s: no candidates", user.id)
        return 0

    significant = [c for c in cands if c["priority"] != "soft"]
    soft = [c for c in cands if c["priority"] == "soft"]

    # Приоритет + потолок: значимые идут всегда (мягкие вливаются);
    # если значимых нет — мягкие подчиняются потолку 1/48ч.
    if significant:
        to_send = significant + soft
    else:
        if _soft_capped(db, user.id, utcnow()):
            logger.info("push skip user=%s: soft capped", user.id)
            return 0
        to_send = soft

    # Порядок по убыванию значимости (медленные планеты первыми)
    to_send.sort(key=lambda c: c["weight"], reverse=True)

    # Ключи событий, из которых собран пуш. Доезжают до приложения в `data`
    # и нужны ему, чтобы погасить СВОЁ локальное уведомление о том же событии
    # (дедуп между каналами, решение владельца 13.09.2026). Ключ тот же самый
    # `kind:ref`, по которому дедуплицирует сервер и который отдаёт
    # `/push/upcoming`, — поэтому сопоставление точное, а не по тексту.
    #
    # ⚠️ Это ДАННЫЕ, а не новая логика: пара уже посчитана выше, здесь она
    # только перекладывается. Отбор, тексты, склейка и `push_sent_log` не
    # затронуты ничем.
    keys = [f"{c['kind']}:{c['ref']}" for c in to_send]

    # Агрегация совпавших за день в один пуш
    if len(to_send) == 1:
        payload = {
            "title": to_send[0]["title"],
            "body": to_send[0]["body"],
            "url": to_send[0]["url"],
            "target": to_send[0].get("target"),
            "keys": keys,
        }
    else:
        # Страховка: дедуп по планете в блоке 5 убирает основной источник
        # повторов, но если где-то ещё совпадёт текст фрагмента — не
        # показываем дубли в склейке.
        seen_frags: set[str] = set()
        frags = []
        for c in to_send:
            if c["frag"] not in seen_frags:
                seen_frags.add(c["frag"])
                frags.append(c["frag"])
        payload = {
            "title": "✦ Ваше окно сегодня",
            "body": " · ".join(frags),
            "url": to_send[0]["url"],
            "keys": keys,
        }

    n = send_to_user(db, user.id, payload)
    if n:
        for c in to_send:
            _mark_sent(db, user.id, c["kind"], c["ref"])
        logger.info("push send user=%s kinds=%s n=%d", user.id, [c["kind"] for c in to_send], n)
        return n
    logger.info("push skip user=%s: send_to_user delivered 0 (no active subscriptions or all sends failed)", user.id)
    return 0


# ── Будущие события для локальных уведомлений на устройстве ──
UPCOMING_DEFAULT_DAYS = 7
UPCOMING_MAX_DAYS = 14


def collect_upcoming(db: Session, user: User, days: int) -> dict:
    """События ближайших `days` дней, уже с готовым текстом уведомления.

    Зачем ручка вообще. Локальные уведомления в мобильном приложении
    планируются НА УСТРОЙСТВЕ заранее — планировщик в main.py до него не
    достаёт (телефон может быть офлайн, приложение выгружено). Значит клиенту
    нужен список будущих событий. Единственное, чего делать нельзя, — считать
    их на клиенте: отбор (какое событие достойно уведомления) и формулировки
    существуют в одном экземпляре, здесь.

    Поэтому функция НЕ содержит ни одного собственного критерия отбора и ни
    одной своей строки текста: она вызывает тот же `_collect_candidates`,
    что и планировщик, по одному разу на каждый день окна, и отдаёт его
    `title`/`body`/`url` как есть.

    Что здесь СОЗНАТЕЛЬНО не переиспользуется:

    * `push_sent_log` — дедуп отправленного. Он про прошлое («этот пуш уже
      ушёл с сервера»), а тут будущее: сервер ничего не отправлял и отмечать
      ему нечего. Различать уже показанное — задача клиента, для этого в
      ответе есть `key` (см. ниже).
    * склейка нескольких событий одного дня в один пуш (`_process_user`) и
      потолок мягких 1/48ч. Оба зависят от состояния сервера: склейка — от
      того, что события совпали в ОДНОМ тике, потолок — от истории
      отправок. Для прогноза на неделю вперёд ни того, ни другого нет.
      Практическое следствие, которое надо знать: день с тремя событиями
      даст клиенту ТРИ записи, тогда как веб отправил бы один пуш. Как их
      показать — решает клиент; собирать из них свой текст он не должен.

    `key` — это `kind:ref`, ровно та пара, по которой сервер дедуплицирует
    отправленное (`push_sent_log`, уникальный индекс `user_id, kind,
    ref_key`). Взят именно он, а не порядковый номер и не хеш текста:
    - он устойчив между запросами — собран из планеты, дома, аспекта и ДАТЫ
      САМОГО СОБЫТИЯ, а не даты запроса; тот же транзит в понедельник и в
      среду даёт один и тот же `key`;
    - он устойчив к правке формулировок — перепишем шаблон, клиент не
      покажет событие заново;
    - он совпадает с серверным, поэтому если однажды понадобится гасить на
      сервере уже показанное на устройстве, сопоставлять будет по чему.

    ⚠️ Гейта по тарифу здесь нет намеренно (решение владельца 10.09.2026:
    уведомления доступны всем тарифам). В веб-пушах его тоже нет ни в одном
    месте — не «забыли», а так решено; добавлять сюда, не трогая веб,
    означало бы два разных ответа на один вопрос.
    """
    days = max(1, min(int(days), UPCOMING_MAX_DAYS))

    chart = get_primary_chart(db, user)
    if not chart:
        # Тот же критерий, что у планировщика: без главной карты уведомлять
        # не по чему. Отдаём пустой список, а не 404 — «пока нечего
        # планировать» это нормальное состояние, а не ошибка запроса.
        return {"timezone": DEFAULT_TZ, "days": days, "events": []}

    tzname = getattr(chart, "timezone", None) or DEFAULT_TZ
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone(DEFAULT_TZ)
        tzname = DEFAULT_TZ

    now_local = datetime.now(pytz.utc).astimezone(tz)
    daily_time = _daily_time_of(user)
    quiet_from = _quiet_from_of(user)
    th, tm = _parse_hm(daily_time, (8, 0))

    events: list[dict] = []
    seen_keys: set[str] = set()

    for offset in range(days):
        day = now_local.date() + timedelta(days=offset)
        # Время показа — то же, что у веб-пуша: начало окна в день события.
        naive = datetime(day.year, day.month, day.day, th, tm)
        at = tz.localize(naive) if hasattr(tz, "localize") else naive.replace(tzinfo=tz)

        # Прошедшее не планируют: сегодняшнее окно могло уже закрыться.
        if at <= now_local:
            continue
        # Та же граница тишины, что у планировщика. Сегодня отсечь тут может
        # только заведомо кривую пару настроек (нижняя граница позже верхней),
        # потому что `at` и есть нижняя граница окна, — но правило одно на оба
        # пути намеренно: разъехаться им негде.
        if not in_send_window(at, daily_time, quiet_from):
            continue

        for cand in _collect_candidates(db, user, chart, day):
            key = f"{cand['kind']}:{cand['ref']}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            events.append({
                "key": key,
                "kind": cand["kind"],
                "at": at.isoformat(),
                "title": cand["title"],
                "body": cand["body"],
                "url": cand["url"],
                "target": cand.get("target"),
            })

    return {"timezone": tzname, "days": days, "events": events}


async def run_push_tick(db: Session) -> dict:
    """Основная логика тика — переиспользуется HTTP-эндпоинтом ниже и
    внутренним планировщиком в main.py (см. lifespan).

    20.08.2026: _process_user — синхронная цепочка (расчёт транзитов/домов
    через Swiss Ephemeris + отправка push), и раньше вызывалась напрямую
    внутри этого async-цикла. main.py — один процесс, один event loop на все
    запросы разом (см. CLAUDE.md); этот тик срабатывает каждые 15 минут для
    ВСЕХ подписанных пользователей — самый частый и самый широкий по блокировке
    источник синхронной нагрузки в приложении. asyncio.to_thread на каждого
    пользователя не ускоряет сам тик, но отдаёт event loop между итерациями —
    остальные запросы больше не встают в очередь на всё время тика.
    """
    # Только пользователи с хотя бы одной подпиской
    user_ids = [row[0] for row in db.query(PushSubscription.user_id).distinct().all()]
    if not user_ids:
        return {"users": 0, "delivered": 0}

    total = 0
    processed = 0
    for user in db.query(User).filter(User.id.in_(user_ids)).all():
        try:
            total += await asyncio.to_thread(_process_user, db, user)
            processed += 1
        except Exception as e:
            logger.warning("push-tick user=%s failed: %s", user.id, e)
            db.rollback()

    return {"users": processed, "delivered": total}


@router.post("/push-tick")
async def push_tick(
    db: Session = Depends(get_db),
):
    return await run_push_tick(db)
