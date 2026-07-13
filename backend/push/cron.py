"""Push scheduler — internal cron endpoint.

Вызывается Railway Cron каждые ~15 минут:
  POST /api/v1/internal/push-tick   (header X-Internal-Secret)

Для каждого пользователя с активной подпиской, по его ГЛАВНОЙ карте
(primary_chart_id), в его локальное время (tz главной карты):
  1) Ежедневный прогноз — в выбранное пользователем время (push_daily_time).
  2) Планер — когда сегодня начинается новый период планеты (заход в дом).
  3) Важные транзиты — когда сегодня начинается значимый транзит.

Все три отправляются в утреннее «окно» пользователя (>= push_daily_time),
дедуплицируются через push_sent_log (одно событие — один пуш).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, date as date_type, timedelta

import pytz
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, NatalChart, PushSubscription, PushSentLog
from backend.push.sender import send_to_user

logger = logging.getLogger("astro.push.cron")

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])

DEFAULT_TZ = "Europe/Moscow"

PLANET_RU = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
    "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн",
    "Uranus": "Уран", "Neptune": "Нептун", "Pluto": "Плутон",
    "North Node": "Сев. узел", "Ascendant": "Асцендент", "Midheaven": "MC",
}
ASPECT_RU = {
    "conjunction": "соединение", "sextile": "секстиль",
    "square": "квадрат", "trine": "трин", "opposition": "оппозиция",
}
FAST_PLANETS = ("Sun", "Mercury", "Venus", "Mars")
SLOW_PLANETS = ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")
MEDIUM_PLANETS = ("Mercury", "Venus", "Mars")

# E5/E6 — мягкие пуши (шум): ограничиваются потолком 1/48ч, вливаются в событийный.
SOFT_KINDS = {"daily", "moon"}
SOFT_CAP_HOURS = 48
ADVANCE_MONTH_DAYS = 30   # упреждение «большого периода» (медленные планеты)
ADVANCE_WEEK_DAYS = 7     # упреждение среднего периода (Венера/Марс/Меркурий)


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
    from backend.transit.engine import ASPECTS, _angular_distance
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
                    ar = ASPECT_RU.get(aspect, aspect)
                    out.append({
                        "kind": "transit_approach",
                        "ref": f"4deg:{tp}:{npl}:{aspect}:{today.isoformat()}",
                        "priority": "significant", "weight": 95,
                        "frag": f"{pr} подходит к {nr}",
                        "title": "✦ Транзит на подходе",
                        "body": f"{pr} {ar} к вашему {nr} — транзит на подходе (~4°). Готовьтесь.",
                        "url": planner_url,
                    })

        # приближение к куспиду дома (вход в новую сферу)
        if has_houses:
            for idx, cusp in enumerate(cusps):
                house = idx + 1
                d_t = _angular_distance(lt_t, cusp)
                d_y = _angular_distance(lt_y, cusp)
                if d_t <= APPLYING_ORB < d_y:
                    out.append({
                        "kind": "cusp_approach",
                        "ref": f"4deg_cusp:{tp}:{house}:{today.isoformat()}",
                        "priority": "significant", "weight": 95,
                        "frag": f"{pr} входит в дом {house}",
                        "title": "✦ Смена сферы",
                        "body": f"{pr} приближается к дому {house} — скоро новая сфера жизни (~4°).",
                        "url": planner_url,
                    })
    return out


# ── Фаза 3: троичное касание ретро (директ → ретро → директ) ──
EXACT_TOUCH_ORB = 0.3     # порог «точного» касания в градусах
TRIPLE_SCAN_DAYS = 300    # окно назад для подсчёта номера захода

_TRIPLE_MSG = {
    1: ("✦ Тема открывается", "тема открывается — первый заход"),
    2: ("✦ Возврат темы", "тема возвращается для пересмотра (ретроград)"),
    3: ("✦ Тема закрывается", "третий заход — тема закрывается и закрепляется"),
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
    from backend.transit.engine import ASPECTS, _angular_distance

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
                    title, tail = _TRIPLE_MSG.get(phase, _TRIPLE_MSG[1])
                    ar = ASPECT_RU.get(aspect, aspect)
                    out.append({
                        "kind": "triple",
                        "ref": f"triple:{tp}:{npl}:{aspect}:{today.isoformat()}",
                        "priority": "significant", "weight": 98,
                        "frag": f"{pr} {ar} к {nr}: {tail}",
                        "title": title,
                        "body": f"{pr} {ar} к вашему {nr} — {tail}.",
                        "url": planner_url,
                    })
    return out


# ── Тексты ──
def _daily_body(chart: NatalChart, today: date_type) -> str:
    """Короткий тизер прогноза на день из активных транзитов (без AI)."""
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
            p = PLANET_RU.get(best.transit_planet, best.transit_planet)
            n = PLANET_RU.get(best.natal_planet, best.natal_planet)
            a = ASPECT_RU.get(best.aspect_type, best.aspect_type)
            return f"Сегодня {p} {a} к вашему {n}. Загляните в прогноз на день."
    except Exception as e:
        logger.warning("daily body build failed: %s", e)
    return "Ваш персональный прогноз на сегодня готов."


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
            "title": "✦ Прогноз на сегодня", "body": _daily_body(chart, today), "url": "/home",
        })

    # Планер (significant): старт сегодня + упреждение неделя/месяц
    if getattr(user, "push_planner", True):
        try:
            from backend.transit.house_passages import _extract_cusps
            cusps = _extract_cusps({"houses": chart.houses})
            if not all(c == 0.0 for c in cusps):
                # 2) старт периода быстрой планеты сегодня
                for planet in FAST_PLANETS:
                    for house in _period_starts_on(planet, cusps, today):
                        pr = PLANET_RU.get(planet, planet)
                        cands.append({
                            "kind": "planner", "ref": f"{planet}:{house}:{today.isoformat()}",
                            "priority": "significant", "weight": 60, "frag": f"период {pr}",
                            "title": "✦ Планер", "body": f"{pr}: начался новый период (дом {house}).",
                            "url": planner_url,
                        })
                # 3) за неделю — средние планеты (Венера/Марс/Меркурий)
                wk = today + timedelta(days=ADVANCE_WEEK_DAYS)
                for planet in MEDIUM_PLANETS:
                    for house in _period_starts_on(planet, cusps, wk):
                        pr = PLANET_RU.get(planet, planet)
                        cands.append({
                            "kind": "planner_week", "ref": f"{planet}:{house}:{wk.isoformat()}",
                            "priority": "significant", "weight": 70, "frag": f"через неделю период {pr}",
                            "title": "✦ Скоро период", "body": f"{pr}: через неделю начнётся период (дом {house}). Подготовьтесь.",
                            "url": planner_url,
                        })
                # 4) за месяц — медленные планеты (большой период)
                mo = today + timedelta(days=ADVANCE_MONTH_DAYS)
                for planet in SLOW_PLANETS:
                    for house in _period_starts_on(planet, cusps, mo):
                        pr = PLANET_RU.get(planet, planet)
                        cands.append({
                            "kind": "planner_month", "ref": f"{planet}:{house}:{mo.isoformat()}",
                            "priority": "significant", "weight": 100, "frag": f"скоро большой период: {pr}",
                            "title": "✦ Большой период впереди",
                            "body": f"{pr}: через месяц начнётся новый большой период (дом {house}). Готовьтесь заранее.",
                            "url": planner_url,
                        })
        except Exception as e:
            logger.warning("planner candidates failed user=%s: %s", user.id, e)

    # 5) Важные транзиты — старт значимого транзита сегодня (significant)
    if getattr(user, "push_key_transits", True):
        try:
            from backend.transit.engine import calculate_transits, ALERT_PLANETS
            events = calculate_transits(natal_planets=chart.planets, from_date=today, to_date=today)
            for e in events:
                if e.transit_planet not in ALERT_PLANETS:
                    continue
                if e.start_date != today.isoformat():
                    continue
                pr = PLANET_RU.get(e.transit_planet, e.transit_planet)
                nr = PLANET_RU.get(e.natal_planet, e.natal_planet)
                ar = ASPECT_RU.get(e.aspect_type, e.aspect_type)
                cands.append({
                    "kind": "transit",
                    "ref": f"{e.transit_planet}:{e.natal_planet}:{e.aspect_type}:{e.start_date}",
                    "priority": "significant", "weight": 90, "frag": f"{pr} {ar} к {nr}",
                    "title": "✦ Важный транзит",
                    "body": f"{pr} {ar} к вашему {nr} — начинается значимый транзит.",
                    "url": planner_url,
                })
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
                    "priority": "soft", "weight": 30, "frag": label,
                    "title": f"✦ {label} завтра",
                    "body": f"{label} в {phase.sign} — завтра. Подготовьтесь заранее.",
                    "url": "/lunar",
                })
        except Exception as e:
            logger.warning("moon candidates failed user=%s: %s", user.id, e)

    return cands


# ── Основная логика по одному пользователю ──
def _process_user(db: Session, user: User) -> int:
    chart = None
    if user.primary_chart_id:
        chart = db.query(NatalChart).filter(NatalChart.id == user.primary_chart_id).first()
    if not chart:
        return 0  # без главной карты уведомлять не по чему

    tzname = getattr(chart, "timezone", None) or DEFAULT_TZ
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone(DEFAULT_TZ)

    now_local = datetime.now(pytz.utc).astimezone(tz)
    today = now_local.date()

    target = str(getattr(user, "push_daily_time", "08:00") or "08:00")
    try:
        th, tm = (int(x) for x in target.split(":"))
    except Exception:
        th, tm = 8, 0
    # Утреннее окно: работаем только когда локальное время уже наступило.
    if (now_local.hour, now_local.minute) < (th, tm):
        return 0

    # Сбор + отсев уже отправленного
    cands = [
        c for c in _collect_candidates(db, user, chart, today)
        if not _already_sent(db, user.id, c["kind"], c["ref"])
    ]
    if not cands:
        return 0

    significant = [c for c in cands if c["priority"] != "soft"]
    soft = [c for c in cands if c["priority"] == "soft"]

    # Приоритет + потолок: значимые идут всегда (мягкие вливаются);
    # если значимых нет — мягкие подчиняются потолку 1/48ч.
    if significant:
        to_send = significant + soft
    else:
        if _soft_capped(db, user.id, datetime.utcnow()):
            return 0
        to_send = soft

    # Порядок по убыванию значимости (медленные планеты первыми)
    to_send.sort(key=lambda c: c["weight"], reverse=True)

    # Агрегация совпавших за день в один пуш
    if len(to_send) == 1:
        payload = {"title": to_send[0]["title"], "body": to_send[0]["body"], "url": to_send[0]["url"]}
    else:
        payload = {
            "title": "✦ Ваш Timeline на сегодня",
            "body": "Сегодня: " + " + ".join(c["frag"] for c in to_send),
            "url": to_send[0]["url"],
        }

    n = send_to_user(db, user.id, payload)
    if n:
        for c in to_send:
            _mark_sent(db, user.id, c["kind"], c["ref"])
        return n
    return 0


@router.post("/push-tick")
async def push_tick(
    x_internal_secret: str = Header(default=""),
    db: Session = Depends(get_db),
):
    secret = os.getenv("INTERNAL_SECRET", "")
    if secret and x_internal_secret != secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Только пользователи с хотя бы одной подпиской
    user_ids = [row[0] for row in db.query(PushSubscription.user_id).distinct().all()]
    if not user_ids:
        return {"users": 0, "delivered": 0}

    total = 0
    processed = 0
    for user in db.query(User).filter(User.id.in_(user_ids)).all():
        try:
            total += _process_user(db, user)
            processed += 1
        except Exception as e:
            logger.warning("push-tick user=%s failed: %s", user.id, e)
            db.rollback()

    return {"users": processed, "delivered": total}
