"""Per-tier rate limiting helpers.

SlowAPI-лимиты реализованы через ДВА декоратора на каждый эндпоинт:
  @limiter.limit("10/minute", key_func=chart_free_key)   # считает только free-запросы
  @limiter.limit("60/minute", key_func=chart_pro_key)    # считает только pro/premium

Ключи строятся так:
  free:    "chart:free:token:<...>" или "chart:free:ip:<...>"
  pro:     "chart:pro:token:<...>"  или "chart:pro:ip:<...>"

Поскольку ключи разные — счётчики независимы.
Free-пользователь попадает под лимит 10/min (ключ chart:free:...).
Pro-пользователь попадает под лимит 60/min (ключ chart:pro:...).
TierMiddleware кладёт tier в request.state.user_tier до декораторов.
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import HTTPException, Request, status

from backend.limiter import client_ip
from backend.config import get_settings
from backend.models import User

settings = get_settings()


# ═══════════════════════════════════════════════════════════
# TIER FLAGS
# ═══════════════════════════════════════════════════════════

TIER_FLAGS: dict[str, dict] = {
    "free": {
        "interpretation_word_limit": 500,
        "interpretations_per_month": 0,        # только превью (блюр)
        "first_interpretation_free": True,     # 3.3: одна полная интерпретация навсегда
        "charts_per_day": None,
        "transits_months": 0,
        "transits_ai": False,
        "transits_ai_per_month": 0,
        "profiles_limit": 2,    # 19.08.2026: было 1 — «Карты» на /pricing, единственный источник этого числа
        "lunar_months": 1,                     # текущий месяц
        "planner_months": 0,
        "synastry": False,
        "pdf_export": False,   # 19.08.2026: было безлимитно — новая сетка PDF только с Веги
        "pdf_per_month": 0,
        "ai_engine": settings.deepseek_model_pro,
    },
    "lite": {
        "interpretation_word_limit": 800,
        "interpretations_per_month": 5,        # 3.4a: было 3; = числу карт (19.08.2026)
        "charts_per_day": None,
        "transits_months": 1,                  # 19.08.2026: было 12 — решение владельца
        "transits_ai": False,                  # полный AI-доступ — нет
        "transits_ai_per_month": 3,            # 3.4a: тизер Pro — 3 AI-транзита/мес
        "profiles_limit": 5,    # 19.08.2026: было 1 — «Карты» на /pricing, единственный источник этого числа
        "lunar_months": 12,                    # на год
        "planner_months": 3,                   # 3.4a: было 1
        "synastry": False,
        "pdf_export": True,
        "pdf_per_month": 5,     # 19.08.2026: было безлимитно — новая сетка
        "ai_engine": settings.deepseek_model_pro,
    },
    "pro": {
        "interpretation_word_limit": 2500,
        "interpretations_per_month": 15,       # = числу карт (19.08.2026)
        "charts_per_day": None,
        "transits_months": 3,                  # 19.08.2026: было 12 — решение владельца
        "transits_ai": True,
        "transits_ai_per_month": None,         # безлимит
        "profiles_limit": 15,   # 19.08.2026: было 5 — «Карты» на /pricing, единственный источник этого числа
        "lunar_months": 12,
        "planner_months": 12,
        "synastry": False,
        "pdf_export": True,
        "pdf_per_month": 15,    # 19.08.2026: было 5 — новая сетка
        "ai_engine": settings.deepseek_model_pro,
    },
    "premium": {
        "interpretation_word_limit": 5000,
        "interpretations_per_month": None,  # 19.08.2026: было 100 — новая сетка, «безлимит»
        "charts_per_day": None,
        "transits_months": 24,                 # 3.2: было 12 — дифференциатор над Pro
        "transits_ai": True,
        "transits_ai_per_month": None,         # безлимит
        "profiles_limit": None,
        "lunar_months": None,   # 19.08.2026: было 12 — «безлимит» по новой сетке (12 = как у Pro, не дифференциатор)
        "planner_months": 12,
        "synastry": True,
        "pdf_export": True,
        "pdf_per_month": None,  # 19.08.2026: было 50 — новая сетка, «безлимит»
        "ai_engine": settings.deepseek_model_pro,
    },
}


# 20.08.2026: раньше здесь было отдельное поле charts_per_month на тариф,
# вручную синхронизированное с profiles_limit — два независимых числа,
# обязанных совпадать, рано или поздно расходились (уже случалось с
# pdf_per_month, см. TestTierMonotonicity). Слотовая модель (вариант А,
# решение владельца) отменяет саму идею «лимита создания в месяц» как
# тарифной фичи — на витрине только profiles_limit.
#
# Но месячный COUNT(*) в chart/calculate — не только тарифная витрина, это
# ещё и единственная защита от скрипта, который создаёт карты по кругу
# (30/минуту по IP — burst-лимит, не помеха ровному потоку раз в несколько
# секунд). Для free/lite/pro это по-прежнему не имеет значения: profiles_limit
# (2/5/15) блокирует раньше, чем скрипт успел бы дойти хоть до какого-то
# порога. Но у Orion profiles_limit = None (безлимит слотов) — там раньше
# не было вообще никакой защиты от такого скрипта. CRM создаёт карты
# клиентам отдельным путём (crm/router.py), под этот лимит не подпадает —
# число ниже не мешает даже активной практике астролога.
#
# Плоское число, одно на все тарифы — это больше не тарифная фича, а
# бэкстоп от ботов, поэтому на витрине не описывается нигде (ни в оферте,
# ни в интерфейсе).
CHART_CREATION_ABUSE_LIMIT = 100


def get_feature_flags(user: Optional[User]) -> dict:
    tier = user.tier if user else "free"
    flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
    return {
        "tier": tier,
        **flags,
        "transits": flags["transits_months"] > 0,
        "transits_ai": flags["transits_ai"],
        # частичный AI-доступ к транзитам (Lite): есть месячная квота > 0
        "transits_ai_limited": (not flags["transits_ai"])
            and bool(flags.get("transits_ai_per_month")),
        # 3.3: показывать фронту, доступна ли ещё бесплатная интерпретация Free
        "first_interpretation_available": (
            tier == "free"
            and flags.get("first_interpretation_free", False)
            and (user is not None)
            and (not getattr(user, "free_interpretation_used", False))
        ),
        # pro и premium считаются "безлимитными" относительно free/lite
        "unlimited_interpretations": tier in ("pro", "premium"),
        "unlimited_charts": flags["profiles_limit"] is None and flags.get("charts_per_day") is None,
        "pdf_reports": flags["pdf_export"],
        "google_calendar": tier != "free",
        "rag_chat": tier in ("pro", "premium"),
        "crm": tier == "premium",
    }


# ═══════════════════════════════════════════════════════════
# SLOWAPI — базовый ключ и tier-specific ключи
# ═══════════════════════════════════════════════════════════

def _base_id(request: Request) -> str:
    """Возвращает токен (первые 60 символов) или IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return f"token:{auth[7:67]}"
    return f"ip:{client_ip(request)}"


# /chart/calculate — два ключа, два декоратора в main.py
def chart_free_key(request: Request) -> str:
    return f"chart:free:{_base_id(request)}"

def chart_pro_key(request: Request) -> str:
    return f"chart:pro:{_base_id(request)}"

def chart_premium_key(request: Request) -> str:
    return f"chart:premium:{_base_id(request)}"


# /interpret — два ключа, два декоратора в main.py
def interpret_free_key(request: Request) -> str:
    return f"interp:free:{_base_id(request)}"

def interpret_pro_key(request: Request) -> str:
    return f"interp:pro:{_base_id(request)}"

def interpret_premium_key(request: Request) -> str:
    return f"interp:premium:{_base_id(request)}"


# /rag-chat — счёт по владельцу токена, а не по IP: эндпоинт платный (Pro+),
# и лимит должен ограничивать аккаунт, а не офис за общим NAT.
def rag_chat_key(request: Request) -> str:
    return f"rag:{_base_id(request)}"


# Регистрация: троттлинг по email закрывает повторную отправку на один адрес, но
# не мешает гнать письма на тысячи разных. Ключ по IP закрывает именно это.
def register_send_key(request: Request) -> str:
    return f"reg:ip:{client_ip(request)}"


# Публичные share-картинки: рендер PNG + генерация подписи через LLM.
def share_card_key(request: Request) -> str:
    return f"share:ip:{client_ip(request)}"


# Экспорт данных (152-ФЗ) — тяжёлый запрос (все карты, интерпретации,
# платежи), счёт по владельцу токена, чтобы не ограничивать общий NAT/офис.
def export_key(request: Request) -> str:
    return f"export:{_base_id(request)}"




# ═══════════════════════════════════════════════════════════
# DAILY INTERPRETATION COUNTER
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
# PERSISTENT MONTHLY USAGE COUNTERS (usage_counters table)
# ═══════════════════════════════════════════════════════════

def _current_period_ym() -> str:
    """Текущий календарный месяц в формате 'YYYY-MM' (UTC)."""
    return time.strftime("%Y-%m", time.gmtime())


def get_monthly_usage(db, user_id: str, kind: str) -> int:
    """Сколько единиц `kind` израсходовано пользователем в текущем месяце."""
    from backend.models import UsageCounter
    row = (
        db.query(UsageCounter)
        .filter(
            UsageCounter.user_id == user_id,
            UsageCounter.kind == kind,
            UsageCounter.period_ym == _current_period_ym(),
        )
        .first()
    )
    return row.count if row else 0


def increment_monthly_usage(db, user_id: str, kind: str) -> int:
    """Атомарно +1 к счётчику текущего месяца. Возвращает новое значение."""
    from backend.models import UsageCounter
    period = _current_period_ym()
    row = (
        db.query(UsageCounter)
        .filter(
            UsageCounter.user_id == user_id,
            UsageCounter.kind == kind,
            UsageCounter.period_ym == period,
        )
        .with_for_update(nowait=False)
        .first()
    )
    if row is None:
        row = UsageCounter(user_id=user_id, kind=kind, period_ym=period, count=1)
        db.add(row)
    else:
        row.count += 1
    db.commit()
    return row.count


# ═══════════════════════════════════════════════════════════
# TIER RATE LIMITER
# ═══════════════════════════════════════════════════════════

class TierRateLimiter:
    """Проверки доступа и месячных лимитов.

    Счётчики персистентные (таблица usage_counters), календарный месяц.
    Инкремент делается ПОСЛЕ успешной генерации — методы check_* только
    проверяют и не увеличивают счётчик, чтобы неудачная генерация не
    «съедала» лимит. Инкремент вызывается отдельно (commit_*).
    """

    def check_interpretation_limit(self, user: Optional[User], db=None) -> None:
        """Проверка лимита интерпретаций.

        Free: 0/мес по тарифу, НО одна бесплатная навсегда (3.3) —
              разрешается, если user.free_interpretation_used == False.
        Lite/Pro/Premium: месячный лимит из usage_counters.
        """
        if user is None:
            # анонимы — только превью, блокируется на уровне эндпоинта
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Войдите в аккаунт, чтобы получить интерпретацию.",
            )

        tier = user.tier
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
        limit = flags["interpretations_per_month"]

        # 3.3 — первая бесплатная интерпретация для Free
        if limit == 0 and flags.get("first_interpretation_free"):
            if not getattr(user, "free_interpretation_used", False):
                return  # разрешаем первую и единственную бесплатную
            from backend.email_service import TIER_NAMES
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Вы использовали бесплатную интерпретацию. "
                    f"Оформите {TIER_NAMES['lite']}, чтобы разбирать карты дальше."
                ),
            )

        if limit == 0:
            from backend.email_service import TIER_NAMES
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"AI-интерпретации недоступны на {TIER_NAMES['free']} плане. Оформите {TIER_NAMES['lite']}.",
            )

        if limit is None:
            return  # безлимит

        if db is None:
            # защита от неверного вызова — без db посчитать нельзя
            return
        used = get_monthly_usage(db, str(user.id), "interpretation")
        if used >= limit:
            from backend.email_service import TIER_NAMES
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Лимит {limit} интерпретаций в месяц исчерпан для тарифа "
                    f"{TIER_NAMES.get(tier, tier.capitalize())}. Оформите более высокий тариф."
                ),
            )

    def commit_interpretation(self, user: Optional[User], db) -> None:
        """Зафиксировать расход интерпретации ПОСЛЕ успешной генерации."""
        if user is None or db is None:
            return
        tier = user.tier
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
        limit = flags["interpretations_per_month"]

        # 3.3 — отметить, что бесплатная интерпретация Free израсходована
        if limit == 0 and flags.get("first_interpretation_free"):
            if not getattr(user, "free_interpretation_used", False):
                user.free_interpretation_used = True
                db.add(user)
                db.commit()
            return

        if limit is None or limit == 0:
            return
        increment_monthly_usage(db, str(user.id), "interpretation")

    def check_transit_access(self, user: Optional[User]) -> None:
        """Доступ к ПРОСМОТРУ транзитов (без AI)."""
        tier = user.tier if user else "free"
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
        if flags["transits_months"] == 0:
            from backend.email_service import TIER_NAMES
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Транзиты недоступны на {TIER_NAMES['free']} плане. Оформите {TIER_NAMES['lite']}.",
            )

    def check_transit_ai_limit(self, user: Optional[User], db=None) -> None:
        """Доступ к AI-расшифровке транзитов.

        Pro/Premium: безлимит (transits_ai=True).
        Lite (3.4a): частичный доступ — transits_ai_per_month штук в месяц.
        Free: запрещено.
        """
        tier = user.tier if user else "free"
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])

        if flags["transits_ai"]:
            return  # Pro / Premium — полный доступ

        quota = flags.get("transits_ai_per_month") or 0
        if quota <= 0:
            from backend.email_service import TIER_NAMES
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"AI-расшифровка транзитов доступна на {TIER_NAMES['pro']} и выше.",
            )

        # Lite — квота в месяц
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Войдите в аккаунт, чтобы получить AI-расшифровку транзита.",
            )
        if db is None:
            return
        used = get_monthly_usage(db, str(user.id), "transit_ai")
        if used >= quota:
            from backend.email_service import TIER_NAMES
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Использовано {quota} AI-расшифровок транзитов в этом месяце "
                    f"на тарифе {TIER_NAMES['lite']}. Перейдите на {TIER_NAMES['pro']} для безлимита."
                ),
            )

    def commit_transit_ai(self, user: Optional[User], db) -> None:
        """Зафиксировать расход AI-транзита ПОСЛЕ успешной генерации (только Lite)."""
        if user is None or db is None:
            return
        tier = user.tier
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
        if flags["transits_ai"]:
            return  # безлимитным тарифам счётчик не нужен
        quota = flags.get("transits_ai_per_month") or 0
        if quota <= 0:
            return
        increment_monthly_usage(db, str(user.id), "transit_ai")

    def check_premium_ip(self, user: Optional[User], request: Request) -> None:
        """Для Premium: сброс сессии при 3+ уникальных IP за 30 минут."""
        if user is None or user.tier != "premium":
            return
        from backend.cache import ip_monitor
        ip = client_ip(request)
        if ip_monitor.record_and_check(str(user.id), ip):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Обнаружен вход с нескольких устройств. Пожалуйста, войдите заново.",
                headers={"WWW-Authenticate": "Bearer"},
            )


tier_limiter = TierRateLimiter()

# Алиасы для совместимости с задачей 2
TIER_LIMITS = TIER_FLAGS

def get_tier_limits(tier: str) -> dict:
    return TIER_FLAGS.get(tier, TIER_FLAGS["free"])
