"""Application configuration via environment variables."""

import json
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


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
    # Доверенные обратные прокси (IP или CIDR через запятую). Пусто = не верить
    # X-Forwarded-For вообще. Никогда не указывайте "*": любой клиент сможет
    # подделать свой IP и обойти лимиты.
    trusted_proxy_ips: str = ""
    # Хранилище счётчиков; пусто — берётся redis_url.
    rate_limit_storage_uri: str = ""
    # Блокировка аккаунта после серии неудачных входов.
    login_max_failures: int = 10
    login_lockout_seconds: int = 900

    rate_limit_anon: str = "30/minute"
    rate_limit_auth: str = "100/minute"
    # Страховочный потолок на ВСЕ маршруты (SlowAPIMiddleware). Намеренно
    # высокий: SPA делает по десятку запросов на экран, и низкий глобальный
    # лимит выбил бы обычных пользователей. Точечные лимиты на дорогих
    # эндпоинтах живут отдельными декораторами и срабатывают раньше.
    # Пусто — middleware не подключается (поведение как раньше).
    rate_limit_default: str = "300/minute"
    rate_limit_free_charts_per_day: int = 5
    rate_limit_free_interpretations_per_day: int = 2

    # ── SSE ──
    # Тикет живёт ровно столько, сколько нужно на открытие EventSource.
    sse_ticket_ttl_seconds: int = 60

    # ── Anonymous charts ──
    # Сколько живёт анонимная карта до привязки к аккаунту (cleanup-таска).
    anon_chart_ttl_days: int = 30

    # ── Ephemeris ──
    ephe_path: str = "data/ephe"

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"

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

    # ── Служебные (cron) эндпоинты ──
    # Пусто вне DEBUG/TESTING — приложение не стартует: /api/v1/internal/* иначе
    # остались бы открытыми. Проверка — backend/authz.require_internal_secret.
    internal_secret: str = ""

    # ── Host header ──
    # Разрешённые значения заголовка Host. Пусто = "*" (не проверять). Nginx уже
    # ограничивает server_name, это второй рубеж на случай прямого обращения к
    # 127.0.0.1:8000 в обход прокси.
    allowed_hosts: str = ""

    # ── Sentry ── пусто = SDK не инициализируется, поведение как раньше.
    sentry_dsn: str = ""
    # Прод-безопасный дефолт. Для локальной разработки добавьте localhost.
    # Читается из CORS_ORIGINS или ALLOWED_ORIGINS (второе имя раньше было
    # только в комментарии и по факту игнорировалось).
    cors_origins: str = Field(
        default="https://www.astreatime.ru,https://astreatime.ru",
        validation_alias=AliasChoices("CORS_ORIGINS", "ALLOWED_ORIGINS"),
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        # Поля с validation_alias иначе нельзя задать по имени в конструкторе.
        "populate_by_name": True,
    }

    @property
    def cors_origins_list(self) -> list[str]:
        """Origins из строки: поддерживаются JSON-массив и список через запятую.

        В .env значение записано JSON-массивом, а прежняя реализация просто
        резала строку по запятой — получались origins вида '["https://a.ru"'
        со скобками и кавычками, которые не совпадали ни с одним реальным
        заголовком Origin, то есть CORS молча не работал.
        """
        raw = self.cors_origins
        if isinstance(raw, list):
            return [str(o).strip() for o in raw if str(o).strip()]

        raw = (raw or "").strip()
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                return [str(o).strip() for o in parsed if str(o).strip()]
            except (json.JSONDecodeError, TypeError):
                pass  # не JSON — разбираем как обычный список

        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        """Список Host для TrustedHostMiddleware. Пусто → ['*'] (без проверки)."""
        hosts = [h.strip() for h in (self.allowed_hosts or "").split(",") if h.strip()]
        return hosts or ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
