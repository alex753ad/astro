"""Calendar router — Calendar Engine endpoints."""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, Request
from datetime import date as date_type, datetime as dt_type

from backend.config import get_settings
from backend.limiter import limiter

logger = logging.getLogger("astro")
settings = get_settings()

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


@router.get("/monthly", summary="General astro calendar for a month (free tier)")
@limiter.limit(settings.rate_limit_anon)
async def get_general_calendar(
    request: Request,
    month: str,  # "YYYY-MM"
):
    from backend.calendar.lunar_engine import get_monthly_calendar
    from backend.transit.forecast_prompt import build_general_calendar_prompt, parse_forecast_response

    try:
        year, mon = map(int, month.split("-"))
    except ValueError:
        raise HTTPException(status_code=422, detail="Формат: YYYY-MM (напр. 2025-12)")

    key_events = get_monthly_calendar(year, mon)

    month_names_ru = {
        1:"Январь",2:"Февраль",3:"Март",4:"Апрель",5:"Май",6:"Июнь",
        7:"Июль",8:"Август",9:"Сентябрь",10:"Октябрь",11:"Ноябрь",12:"Декабрь",
    }
    month_label = f"{month_names_ru[mon]} {year}"
    prompt = build_general_calendar_prompt(month_label=month_label, key_events=key_events)

    raw = ""
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={"model": "claude-sonnet-4-20250514", "max_tokens": 3000, "messages": [{"role": "user", "content": prompt}]},
                )
                raw = resp.json()["content"][0]["text"]
        except Exception as e:
            logger.warning("General calendar AI failed: %s", e)

    overview = None
    if raw:
        try:
            from backend.transit.forecast_prompt import parse_forecast_response
            overview = parse_forecast_response(raw)
        except Exception as e:
            logger.warning("Failed to parse calendar overview: %s", e)

    return {"month": month, "events": key_events, "overview": overview}


@router.get("/lunar", summary="Lunar calendar: moon phases + moon sign per day")
@limiter.limit(settings.rate_limit_anon)
async def get_lunar_calendar(
    request: Request,
    year: int = None,
    month: int = None,
):
    import calendar as cal_mod
    import swisseph as swe
    from backend.calendar.lunar_engine import get_moon_phases, ZODIAC_SIGNS

    today = date_type.today()
    year  = year  or today.year
    month = month or today.month

    def _moon_angle(jd):
        sun, _  = swe.calc_ut(jd, swe.SUN,  swe.FLG_SWIEPH)
        moon, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)
        return (moon[0] - sun[0]) % 360

    jd_m0 = swe.julday(year, month, 1, 0)
    jd_m1 = swe.julday(year + 1, 1, 1, 0) if month == 12 else swe.julday(year, month + 1, 1, 0)
    phases = []

    for target, etype, emoji, label in [
        (0,   "new_moon",  "🌑", "Новолуние"),
        (180, "full_moon", "🌕", "Полнолуние"),
    ]:
        jd = jd_m0 - 32
        prev = None
        while jd < jd_m1 + 2:
            val = (_moon_angle(jd) - target) % 360
            if val > 180: val -= 360
            if prev is not None and prev * val < 0:
                lo, hi = jd - 1.0, jd
                val_lo = prev
                for _ in range(60):
                    mid = (lo + hi) / 2
                    v = (_moon_angle(mid) - target) % 360
                    if v > 180: v -= 360
                    if val_lo * v > 0:
                        lo = mid; val_lo = v
                    else:
                        hi = mid
                exact = (lo + hi) / 2
                real_angle = _moon_angle(exact)
                if abs((real_angle - target + 180) % 360 - 180) > 10:
                    prev = val; jd += 1.0; continue
                y2, mo2, d2, h2 = swe.revjul(exact)
                h2_gmt3 = h2 + 3; d2_gmt3 = int(d2); mo2_gmt3 = int(mo2); y2_gmt3 = int(y2)
                if h2_gmt3 >= 24:
                    h2_gmt3 -= 24; d2_gmt3 += 1
                    _, max_day = cal_mod.monthrange(y2_gmt3, mo2_gmt3)
                    if d2_gmt3 > max_day:
                        d2_gmt3 = 1; mo2_gmt3 += 1
                        if mo2_gmt3 > 12: mo2_gmt3 = 1; y2_gmt3 += 1
                hh, mm = int(h2_gmt3), int((h2_gmt3 % 1) * 60)
                moon_lon, _ = swe.calc_ut(exact, swe.MOON, swe.FLG_SWIEPH)
                sign = ZODIAC_SIGNS[int(moon_lon[0] // 30) % 12]
                phases.append({
                    "date": f"{y2_gmt3:04d}-{mo2_gmt3:02d}-{d2_gmt3:02d}",
                    "time": f"{hh:02d}:{mm:02d} GMT+3",
                    "type": etype, "planet": "Moon", "sign": sign, "emoji": emoji,
                    "description": f"{label} в {sign}",
                })
            prev = val; jd += 1.0

    month_prefix = f"{year:04d}-{month:02d}-"
    phases = sorted([p for p in phases if p["date"].startswith(month_prefix)], key=lambda x: x["date"])

    _, days_in_month = cal_mod.monthrange(year, month)
    daily_signs = []
    for day in range(1, days_in_month + 1):
        d = date_type(year, month, day)
        jd = swe.julday(d.year, d.month, d.day, 12.0)
        lon, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)
        daily_signs.append({"date": d.isoformat(), "sign": ZODIAC_SIGNS[int(lon[0] // 30) % 12], "longitude": round(lon[0], 2)})

    now = dt_type.utcnow()
    jd_now = swe.julday(now.year, now.month, now.day, now.hour + now.minute / 60)
    lon_now, _ = swe.calc_ut(jd_now, swe.MOON, swe.FLG_SWIEPH)

    return {
        "year": year, "month": month,
        "current_moon": {"sign": ZODIAC_SIGNS[int(lon_now[0] // 30) % 12], "degree": round(lon_now[0] % 30, 1)},
        "phases": phases,
        "daily_signs": daily_signs,
    }
