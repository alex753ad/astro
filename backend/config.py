"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # ── Database ──
    database_url: str = "postgresql://astro:astro@localhost:5432/astro_db"

    # ── AI providers ──
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    anthropic_api_key: str = ""
    ai_daily_budget_usd: float = 10.0

    # ── JWT ──
    jwt_secret: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_secret_prev: Optional[str] = None   # для ротации без даунтайма
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # ── Rate limiting ──
    rate_limit_anon: str = "30/minute"
    rate_limit_auth: str = "100/minute"

    # ── Ephemeris ──
    ephe_path: str = "data/ephe"

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"

    # ── Stripe ──
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_pro: str = ""
    stripe_price_id_premium: str = ""

    # ── Google OAuth ──
    google_client_id: str = ""
    google_client_secret: str = ""

    # ── General ──
    debug: bool = False
    environment: str = "development"  # "production" | "development"

    # CORS: задаётся через ALLOWED_ORIGINS в .env
    # Пример: ALLOWED_ORIGINS=["https://astreatime.ru","http://localhost:5173"]
    allowed_origins: list[str] = ["http://localhost:5173"]

    # HTTPS: при HTTPS_ONLY=true приложение редиректит http → https
    https_only: bool = False

    # Email
    resend_api_key: str = ""
    from_email: str = "onboarding@resend.dev"
    app_url: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"

    # Sentry
    sentry_dsn: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
