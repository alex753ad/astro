"""
ВСТАВИТЬ В backend/main.py
==========================
Место: после функции get_monthly_forecast (после строки 824 — конец файла)
Это закрывает 404 на /api/v1/chart/{id}/forecast/weekly
"""


@app.get(
    "/api/v1/chart/{chart_id}/forecast/weekly",
    tags=["forecast"],
    summary="Weekly personal forecast",
)
@limiter.limit(settings.rate_limit_anon)
async def get_weekly_forecast(
    request: Request,
    chart_id: str,
    week_start: str,   # YYYY-MM-DD
    week_end: str,     # YYYY-MM-DD
    db: Session = Depends(get_db),
):
    from datetime import date as date_type
    from backend.transit.engine import calculate_transits
    from backend.transit.forecast_prompt import build_weekly_forecast_prompt, parse_forecast_response
    import httpx, os

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    try:
        from_dt = date_type.fromisoformat(week_start)
        to_dt   = date_type.fromisoformat(week_end)
    except ValueError:
        raise HTTPException(status_code=422, detail="Формат даты: YYYY-MM-DD")

    events = calculate_transits(natal_planets=chart.planets, from_date=from_dt, to_date=to_dt)
    events_dicts = [
        {
            "transit_planet": e.transit_planet,
            "natal_planet":   e.natal_planet,
            "aspect_type":    e.aspect_type,
            "transit_sign":   e.transit_sign,
            "peak_date":      e.peak_date,
            "start_date":     e.start_date,
            "end_date":       e.end_date,
            "peak_orb":       e.peak_orb,
        }
        for e in events
    ]

    natal_profile = {
        "planets":    chart.planets,
        "houses":     chart.houses,
        "ascendant":  chart.ascendant,
        "midheaven":  chart.midheaven,
        "time_unknown": chart.time_unknown,
    }

    prompt = build_weekly_forecast_prompt(
        week_start=week_start,
        week_end=week_end,
        transit_events=events_dicts,
        natal_profile=natal_profile,
    )

    raw = ""
    openai_key = os.getenv("OPENAI_API_KEY", "")

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 2500,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                )
                data = resp.json()
                raw  = data["content"][0]["text"]
        except Exception as e:
            logger.warning(f"Anthropic weekly forecast failed: {e}")

    if not raw and openai_key:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2500,
                        "response_format": {"type": "json_object"},
                    }
                )
                data = resp.json()
                raw  = data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"OpenAI weekly forecast failed: {e}")

    if not raw:
        raise HTTPException(status_code=503, detail="AI forecast unavailable.")

    try:
        forecast = parse_forecast_response(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse error: {e}")

    return {"week_start": week_start, "week_end": week_end, "forecast": forecast}
