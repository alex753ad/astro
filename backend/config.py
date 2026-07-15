"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Database ──
    database_url: str = "postgresql://astro:astro@localhost:5432/astro_db"

    # ── AI providers ──
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    ai_daily_budget_usd: float = 10.0
    ai_max_retries: int = 3  # retry per engine; set to 1 in tests

    # ── JWT ──
    jwt_secret: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_secret_prev: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # ── Rate limiting ──
    rate_limit_anon: str = "30/minute"
    rate_limit_auth: str = "100/minute"
    rate_limit_free_charts_per_day: int = 5
    rate_limit_free_interpretations_per_day: int = 2

    # ── Ephemeris ──
    ephe_path: str = "data/ephe"

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"

    # ── Stripe (legacy webhook support) ──
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # ── Robokassa ──
    robokassa_merchant_login: str = ""
    robokassa_password1: str = ""
    robokassa_password2: str = ""
    robokassa_is_test: bool = True  # False на проде

    # ── Google OAuth ──
    google_client_id: str = ""
    google_client_secret: str = ""

    # ── Email (Resend) ──
    resend_api_key: str = ""
    from_email: str = "onboarding@resend.dev"

    # ── App ──
    app_url: str = "http://localhost:8000"
    frontend_url: str = "https://www.astreatime.ru"
    debug: bool = False
    testing: bool = False
    # Прод-безопасный дефолт. Для локальной разработки добавьте localhost через
    # переменную окружения ALLOWED_ORIGINS (comma-separated).
    cors_origins: str = "https://www.astreatime.ru,https://astreatime.ru"  # env: ALLOWED_ORIGINS

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def cors_origins_list(self) -> list[str]:
        if isinstance(self.cors_origins, list):
            return self.cors_origins
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
