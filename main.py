"""Astro SPA — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import Depends
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.database import get_db, engine, Base
from backend.schemas import HealthResponse
from backend.limiter import limiter

from routers.chart     import router as chart_router
from routers.transits  import router as transits_router
from routers.planner   import router as planner_router
from routers.calendar  import router as calendar_router
from routers.auth      import router as auth_router
from routers.billing   import router as billing_router
from routers.profile   import router as profile_router

from backend.onboarding_router import router as onboarding_router

logger   = logging.getLogger("astro")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Astro SPA API",
    version="0.1.0",
    description="Natal chart calculation, transits, AI interpretations",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(profile_router)
app.include_router(onboarding_router)
app.include_router(chart_router)
app.include_router(transits_router)
app.include_router(planner_router)
app.include_router(calendar_router)


# ── Health ──

@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health():
    return HealthResponse(status="ok", version="0.1.0", database="not_checked")


@app.get("/health/db", response_model=HealthResponse, tags=["health"])
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"
    return HealthResponse(status="ok", version="0.1.0", database=db_status)


@app.get("/health/ai", tags=["health"], summary="AI providers health")
async def health_ai():
    from backend.interpretation.router import get_router
    return {"status": "ok", "engines": await get_router().get_status()}


# ── Debug ──

@app.get("/api/v1/debug/moon", tags=["debug"])
async def debug_moon():
    import swisseph as swe, os
    swe.set_ephe_path(os.getenv("EPHE_PATH", "data/ephe"))

    def _moon_angle(jd):
        sun, _  = swe.calc_ut(jd, swe.SUN,  swe.FLG_SWIEPH)
        moon, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)
        return (moon[0] - sun[0]) % 360

    checks = []
    for label, y, mo, d, h in [
        ("30apr_17utc", 2026, 4, 30, 17.0),
        ("01may_00utc", 2026, 5,  1,  0.0),
        ("15may_20utc", 2026, 5, 15, 20.0),
        ("16may_06utc", 2026, 5, 16,  6.0),
        ("30may_08utc", 2026, 5, 30,  8.0),
        ("31may_08utc", 2026, 5, 31,  8.0),
    ]:
        jd = swe.julday(y, mo, d, h)
        checks.append({"label": label, "angle": round(_moon_angle(jd), 2)})
    return {"checks": checks}
