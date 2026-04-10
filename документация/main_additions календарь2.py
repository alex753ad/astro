"""
ДОБАВИТЬ В backend/main.py
===========================

1. Импорт (после строки 67 — после settings_router):
────────────────────────────────────────────────────
from backend.calendar.engine import get_monthly_calendar

2. Три новых эндпоинта — вставить ПОСЛЕ строки 824 (конец get_monthly_forecast):
──────────────────────────────────────────────────────────────────────────────────
"""

# ════════════════════════════════════════════════════════════
# GENERAL CALENDAR — бесплатный, без натальной карты
# ════════════════════════════════════════════════════════════

# @app.get(
#     "/api/v1/calendar/monthly",
#     tags=["calendar"],
#     summary="General astro calendar for a month (free tier)",
# )
# @limiter.limit(settings.rate_limit_anon)
# async def get_general_calendar(
#     request: Request,
#     month: str,           # формат: "2025-12"
# ):
#     """Общий астро-календарь — новолуния, полнолуния, ингрессы, аспекты.
#     Не требует натальной карты. Бесплатный уровень.
#     Возвращает: список событий + AI-обзор месяца.
#     """
#     import httpx, os
#     from backend.transit.forecast_prompt import build_general_calendar_prompt, parse_forecast_response
#
#     try:
#         year, mon = map(int, month.split("-"))
#     except ValueError:
#         raise HTTPException(status_code=422, detail="Формат: YYYY-MM (напр. 2025-12)")
#
#     # 1. Вычислить события месяца
#     key_events = get_monthly_calendar(year, mon)
#
#     # 2. Сформировать обзор через AI
#     from calendar import month_name
#     month_names_ru = {
#         1:"Январь",2:"Февраль",3:"Март",4:"Апрель",5:"Май",6:"Июнь",
#         7:"Июль",8:"Август",9:"Сентябрь",10:"Октябрь",11:"Ноябрь",12:"Декабрь",
#     }
#     month_label = f"{month_names_ru[mon]} {year}"
#     prompt = build_general_calendar_prompt(month_label=month_label, key_events=key_events)
#
#     raw = ""
#     if os.getenv("ANTHROPIC_API_KEY"):
#         try:
#             async with httpx.AsyncClient(timeout=90) as client:
#                 resp = await client.post(
#                     "https://api.anthropic.com/v1/messages",
#                     headers={
#                         "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
#                         "anthropic-version": "2023-06-01",
#                         "content-type": "application/json",
#                     },
#                     json={
#                         "model": "claude-sonnet-4-20250514",
#                         "max_tokens": 3000,
#                         "messages": [{"role": "user", "content": prompt}],
#                     }
#                 )
#                 data = resp.json()
#                 raw = data["content"][0]["text"]
#         except Exception as e:
#             logger.warning(f"General calendar AI failed: {e}")
#
#     overview = None
#     if raw:
#         try:
#             overview = parse_forecast_response(raw)
#         except Exception as e:
#             logger.warning(f"Failed to parse calendar overview: {e}")
#
#     return {
#         "month": month,
#         "events": key_events,
#         "overview": overview,
#     }


# ════════════════════════════════════════════════════════════
# WEEKLY FORECAST — индивидуальный, платный
# ════════════════════════════════════════════════════════════

# @app.get(
#     "/api/v1/chart/{chart_id}/forecast/weekly",
#     tags=["forecast"],
#     summary="Weekly personal forecast (Pro)",
# )
# @limiter.limit(settings.rate_limit_anon)
# async def get_weekly_forecast(
#     request: Request,
#     chart_id: str,
#     week_start: str,    # YYYY-MM-DD (понедельник)
#     db: Session = Depends(get_db),
# ):
#     """Персональный прогноз на неделю с подсветкой жизненных сфер.
#     Требует натальной карты. Pro-уровень.
#     """
#     from datetime import date as date_type, timedelta
#     from backend.transit.engine import calculate_transits, get_active_transits
#     from backend.transit.forecast_prompt import build_weekly_forecast_prompt, parse_forecast_response
#     import httpx, os
#
#     chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
#     if not chart:
#         raise HTTPException(status_code=404, detail="Chart not found")
#
#     try:
#         start = date_type.fromisoformat(week_start)
#     except ValueError:
#         raise HTTPException(status_code=422, detail="Формат: YYYY-MM-DD")
#
#     end = start + timedelta(days=6)
#     events = calculate_transits(natal_planets=chart.planets, from_date=start, to_date=end)
#     events_dicts = [
#         {
#             "transit_planet": e.transit_planet, "natal_planet": e.natal_planet,
#             "aspect_type": e.aspect_type, "transit_sign": e.transit_sign,
#             "peak_date": e.peak_date, "start_date": e.start_date, "end_date": e.end_date,
#         }
#         for e in events
#     ]
#     natal_profile = {
#         "planets": chart.planets, "houses": chart.houses,
#         "ascendant": chart.ascendant, "midheaven": chart.midheaven,
#     }
#     prompt = build_weekly_forecast_prompt(
#         week_start=week_start, week_end=str(end),
#         transit_events=events_dicts, natal_profile=natal_profile,
#     )
#
#     raw = ""
#     if os.getenv("ANTHROPIC_API_KEY"):
#         try:
#             async with httpx.AsyncClient(timeout=60) as client:
#                 resp = await client.post(
#                     "https://api.anthropic.com/v1/messages",
#                     headers={
#                         "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
#                         "anthropic-version": "2023-06-01",
#                         "content-type": "application/json",
#                     },
#                     json={
#                         "model": "claude-sonnet-4-20250514",
#                         "max_tokens": 2500,
#                         "messages": [{"role": "user", "content": prompt}],
#                     }
#                 )
#                 data = resp.json()
#                 raw = data["content"][0]["text"]
#         except Exception as e:
#             logger.warning(f"Weekly forecast AI failed: {e}")
#
#     if not raw:
#         raise HTTPException(status_code=503, detail="AI forecast unavailable.")
#
#     try:
#         forecast = parse_forecast_response(raw)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Parse error: {e}")
#
#     return {"week_start": week_start, "week_end": str(end), "forecast": forecast}
