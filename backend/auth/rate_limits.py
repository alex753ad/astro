"""Per-tier rate limiting helpers.

20.08.2026: раньше здесь стояла схема из двух статичных slowapi-декораторов
(chart_free_key/chart_pro_key/chart_premium_key) поверх TierMiddleware,
кладущего tier в request.state.user_tier до вызова декораторов. У неё было
два независимых дефекта: TierMiddleware сняли ещё 27.05.2026 в том же
коммите, что добавил Prometheus/health-эндпоинты (сторонний рефакторинг,
не по злому умыслу — просто задели), и с тех пор все три ключа возвращали
СТАТИЧНОЕ имя тира прямо в строке (f"chart:free:...") независимо от
реального пользователя — то есть даже пока TierMiddleware ещё стоял, схема
уже не различала тарифы по-настоящему, просто вешала два счётчика на одну и
ту же связку request→id, и слабейший из двух декораторов (10/мин) всегда
выигрывал у более щедрого. Ключи не были подключены ни к одному эндпоинту с
27.05.2026, реальной защиты не давали ни дня.

Взамен — check_chart_rate_limit ниже: явная проверка внутри хендлера
(Redis-счётчик, фиксированное окно 60 сек), а не slowapi-декоратор. Тариф
читается из уже доступного в эндпоинте объекта User (Depends(
get_current_user_optional) уже декодирует JWT корректно) — отдельного
middleware для этого не требуется, FastAPI даёт правильный тариф и так.
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
        # 30.08.2026: один PDF в месяц. Решение владельца — человек должен
        # один раз увидеть файл, за который просят денег: описание на витрине
        # продаёт хуже открытого документа. До этого (с 19.08.2026) PDF был
        # закрыт для free целиком.
        "pdf_export": True,
        "pdf_per_month": 1,
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


# ── Горизонт транзитов: витрина free и бэкстоп по прошлому ──────────────────
#
# ⚠️ ЭТО РАЗМЕР ВИТРИНЫ, А НЕ ТАРИФНАЯ ФИЧА. Решение E2: список транзитов
# виден ВСЕМ тарифам, включая free, и монетизируется не он, а AI-разбор
# аспектов (у free открыт только топ-2, поле free_unlocked). Поэтому у free
# `transits_months = 0` — это ноль про AI-разбор, а НЕ про длину списка.
#
# Из-за этого free видит список ДАЛЬШЕ, чем Лира: 12 месяцев против 3.
# Выглядит как ошибка, ошибкой не является — под блюром должно быть что
# показать, иначе FreePlanBanner со счётчиком закрытых транзитов и
# PlanComparisonModal остаются без данных, и апселл не на чем строить.
# НЕ «чинить» приравниванием к transits_months: это выключит витрину.
#
# Мерить витрину тарифным флагом нельзя — это смешало бы в одном числе две
# разные вещи (что человек видит и за что платит), и следующая правка сетки
# молча сломала бы одну из них.
#
# ⚠️ Число обязано совпадать с литералом 12 в `TransitTimeline.jsx` (строка с
# `const maxMonths = isFree ? 12 : ...`) — там оно НЕ выводится из флага, это
# именно литерал. Расхождение = free запрашивает больше, чем разрешает
# сервер, и получает 403 на витрине. Синхронность закреплена тестом
# `frontend/src/api/transitsHorizon.test.js` (читает оба файла).
FREE_TRANSITS_TEASER_MONTHS = 12

# Насколько назад вообще разрешено смотреть транзиты и планер — одно число на
# все тарифы. Прошлое не монетизируется ни одним пунктом сетки, поэтому это
# не тарифная фича, а бэкстоп: и таймлайн (`loadPrevious`), и планер (кнопка
# «‹») отматывают назад БЕЗ нижней границы, по месяцу за клик, и без этого
# числа скрипт мог бы гонять эфемериды на произвольную глубину. 24 месяца —
# заведомо дальше, чем доходят руками (24 клика), поэтому видимого поведения
# не меняет. На витрине не описывается, как и CHART_CREATION_ABUSE_LIMIT.
PAST_WINDOW_ABUSE_MONTHS = 24


def transits_horizon_months(tier: str) -> int:
    """Сколько месяцев вперёд разрешено запрашивать транзиты.

    Для free это размер витрины (см. FREE_TRANSITS_TEASER_MONTHS), для
    остальных — тарифный `transits_months`.
    """
    if tier == "free":
        return FREE_TRANSITS_TEASER_MONTHS
    return TIER_FLAGS.get(tier, TIER_FLAGS["free"])["transits_months"]


def _month_edge(anchor: "date", months: int, *, end: bool) -> "date":
    """Первый (end=False) или последний (end=True) день месяца anchor+months."""
    import calendar as _cal
    from datetime import date as _date

    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    day = _cal.monthrange(year, month)[1] if end else 1
    return _date(year, month, day)


def transits_date_window(tier: str, today: "date") -> tuple["date", "date"]:
    """Разрешённый диапазон дат транзитов: (не раньше, не позже).

    Верхняя граница повторяет `monthEndISO(today, maxMonths)` из
    `TransitTimeline.jsx` — ПОСЛЕДНИЙ ДЕНЬ месяца `today + horizon`, а не
    `today + horizon` день в день. Текущий месяц входит в горизонт целиком,
    поэтому листается `horizon + 1` месяцев: у Веги (`transits_months = 1`)
    это текущий и следующий. Так работает интерфейс с 19.08.2026; проверка
    ставится ПОД существующее поведение, а не вместо него — иначе платящая
    Вега потеряла бы месяц, который видит сегодня.

    ⚠️ Обе границы сдвинуты на сутки наружу, и это не запас «на всякий
    случай». Фронтенд берёт «сегодня» по ЛОКАЛЬНОМУ времени пользователя
    (`todayLocalISO`, см. шапку `utils/dateISO.js`), сервер — по UTC. В ночь
    смены месяца это разные месяцы: в Москве (UTC+3) уже 1 сентября, на
    сервере ещё 31 августа — горизонт фронтенда уходит на месяц дальше
    серверного, и таймлайн получил бы 403 на несколько часов каждый месяц.
    Сутки покрывают любой реальный пояс (крайние — UTC-11…UTC+14).
    Направление выбрано осознанно: лишний месяц раз в месяц безвреден,
    ложный 403 на витрине — нет.
    """
    from datetime import timedelta as _td

    horizon = transits_horizon_months(tier)
    return (
        _month_edge(today - _td(days=1), -PAST_WINDOW_ABUSE_MONTHS, end=False),
        _month_edge(today + _td(days=1), horizon, end=True),
    )


def planner_offset_window(tier: str) -> tuple[int, int]:
    """Разрешённый диапазон `month_offset` планера: (минимум, максимум).

    Максимум — тарифный `planner_months` (free 0 / Вега 3 / Лира 12 /
    Орион 12). Интерфейс сам уходит не дальше 11 (`PlannerPage.jsx`, кнопка
    «›» скрыта при `monthOffset >= 11`) и у free/lite не показывает
    навигацию по месяцам вовсе, поэтому проверка ничего из видимого не
    сокращает — она закрывает прямой запрос мимо интерфейса.

    Минимум — общий бэкстоп по прошлому (PAST_WINDOW_ABUSE_MONTHS), а не
    `-planner_months`: кнопка «‹» в планере отматывает назад без нижней
    границы на всех тарифах, и симметричный тарифный минимум отобрал бы у
    людей то, что у них сегодня работает.
    """
    limit = TIER_FLAGS.get(tier, TIER_FLAGS["free"])["planner_months"]
    return (-PAST_WINDOW_ABUSE_MONTHS, limit)


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


# ═══════════════════════════════════════════════════════════
# CHART RATE LIMIT — тарифный per-minute лимит на создание карт
# ═══════════════════════════════════════════════════════════
# 20.08.2026: calculate_full_chart дёшев по CPU (~3мс), но api — один процесс,
# один event loop на все запросы разом (см. CLAUDE.md про Swiss Ephemeris).
# Единственная защита раньше — плоский @limiter.limit(rate_limit_anon) =
# 30/минуту по IP, без различия тарифов и без привязки к аккаунту (общий NAT
# делит один лимит на всех). Числа ниже — не оценка «сколько выдержит
# сервер» (там запас на порядки), а «сколько правдоподобно делает живой
# человек руками за минуту» — никто не отправляет форму рождения 10+ раз
# подряд.
CHART_RATE_LIMIT_PER_MINUTE = {
    "free": 10,
    "lite": 15,
    "pro": 20,
    "premium": 30,  # с запасом под CRM-сессию (несколько клиентов подряд)
}
CHART_RATE_LIMIT_WINDOW_SEC = 60


async def check_chart_rate_limit(user: Optional[User], request: Request) -> None:
    """Тарифный per-minute лимит на построение карты — POST /chart/calculate
    и CRM (backend/crm/router.py). Тариф — из уже декодированного JWT
    (Depends(get_current_user_optional) в эндпоинте), не из
    request.state.user_tier: то поле зависело от TierMiddleware, снятого
    27.05.2026 (см. докстринг модуля) — здесь такой ошибки повторить нельзя,
    потому что мы вообще не читаем request.state.

    Redis, фиксированное окно 60 сек. Fail-open при сбое Redis — как и
    остальные rate-limit'ы в проекте (см. backend/limiter.py): это защита от
    перебора, не контроль доступа, отвал кэша не должен ронять сервис.
    """
    tier = user.tier if user else "free"
    limit = CHART_RATE_LIMIT_PER_MINUTE.get(tier, CHART_RATE_LIMIT_PER_MINUTE["free"])
    identity = f"user:{user.id}" if user else f"ip:{client_ip(request)}"
    key = f"chart_rate:{identity}"

    try:
        from backend.redis_client import get_redis
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, CHART_RATE_LIMIT_WINDOW_SEC)
    except Exception as e:
        import logging
        logging.getLogger("astro.rate_limits").warning(
            "chart rate limit check failed (fail open): %s", e
        )
        return

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Слишком много запросов на построение карт ({limit}/мин). "
                f"Подождите минуту и повторите."
            ),
        )


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

    def check_interpretation_limit(self, user: Optional[User], db=None, chart=None) -> None:
        """Проверка лимита интерпретаций.

        Free: 0/мес по тарифу, НО одна бесплатная на КАЖДУЮ сохранённую карту —
              разрешается, если chart.free_interpretation_used == False.
              Ключ — карта, а не аккаунт: у Free два слота (profiles_limit),
              значит два разбора. Отдельного счётчика нет и не нужно — потолок
              задаёт число слотов, а удаление карты возвращает право по новой
              вместе со строкой.
        Lite/Pro/Premium: месячный лимит из usage_counters.

        `chart` обязателен для Free. Вызывающая сторона (main.py) передаёт уже
        разрешённую resolve_chart_access карту, поэтому проверка стоит ПОСЛЕ
        неё: до 28.08.2026 лимит отбивал раньше доступа, и Free-пользователь,
        спросивший чужую карту, получал 403 вместо 404. Теперь наоборот, и это
        не утечка — resolve_chart_access отвечает 404 одинаково на «нет карты»
        и «нет доступа».
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

        # Бесплатный разбор Free — по одному на карту (048)
        if limit == 0 and flags.get("first_interpretation_free"):
            # chart=None означает, что вызывающая сторона карту не передала.
            # Отказывать в этом случае нельзя (это была бы поломка на ровном
            # месте), пропускать молча — тоже: право осталось бы бесконтрольным.
            # Такой вызывающей стороны сейчас нет, обе передают карту.
            if chart is not None and not getattr(chart, "free_interpretation_used", False):
                return  # по этой карте разбора ещё не было
            if chart is None and not getattr(user, "free_interpretation_used", False):
                return  # запасной путь по старому ключу — аккаунт целиком
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

    def commit_interpretation(self, user: Optional[User], db, chart=None) -> None:
        """Зафиксировать расход интерпретации ПОСЛЕ успешной генерации."""
        if user is None or db is None:
            return
        tier = user.tier
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
        limit = flags["interpretations_per_month"]

        # Free: гасим право по КАРТЕ (048). users.free_interpretation_used при
        # этом продолжаем писать — гейтом он больше не является, но остаётся
        # ответом на вопрос «разбирал ли пользователь хоть раз» (его читает
        # get_feature_flags.first_interpretation_available).
        if limit == 0 and flags.get("first_interpretation_free"):
            changed = False
            if chart is not None and not getattr(chart, "free_interpretation_used", False):
                chart.free_interpretation_used = True
                db.add(chart)
                changed = True
            if not getattr(user, "free_interpretation_used", False):
                user.free_interpretation_used = True
                db.add(user)
                changed = True
            if changed:
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

    def check_pdf_limit(self, user: Optional[User], db=None) -> None:
        """Доступ к PDF-экспорту натальной карты.

        Free: запрещено (pdf_export=False).
        Lite/Pro: pdf_per_month штук в месяц.
        Premium: pdf_per_month=None — безлимит.

        До 30.08.2026 гейта не было вовсе: ручка проверяла только доступ к
        карте, и бесплатный пользователь получал PDF в любом количестве.
        Устройство повторяет check_transit_ai_limit — тот же порядок ветвей
        (флаг доступа, затем квота), тот же вид отказа с названием тарифа.
        """
        tier = user.tier if user else "free"
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])

        if not flags["pdf_export"]:
            from backend.email_service import TIER_NAMES
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"PDF-отчёты недоступны на {TIER_NAMES['free']} плане. "
                    f"Оформите {TIER_NAMES['lite']}."
                ),
            )

        # Недостижимо, пока free не имеет pdf_export: аноним получает tier
        # "free" и отбивается веткой выше. Оставлено как страховка на случай,
        # если флаг когда-нибудь откроют бесплатному тарифу.
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Войдите в аккаунт, чтобы скачать PDF-отчёт.",
            )

        quota = flags.get("pdf_per_month")
        if quota is None:
            return  # безлимит
        if db is None:
            return
        used = get_monthly_usage(db, str(user.id), "pdf")
        if used >= quota:
            from backend.email_service import TIER_NAMES
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                # Формулировка без согласования числа с существительным:
                # при quota = 1 (free с 30.08.2026) прежний текст читался как
                # «Лимит 1 PDF-отчётов». «{quota} в месяц» верно для любого
                # числа и не потребует правки при следующей смене сетки.
                detail=(
                    "PDF-отчёты на этот месяц закончились: тариф "
                    f"{TIER_NAMES.get(tier, tier.capitalize())} даёт {quota} в месяц. "
                    "Оформите более высокий тариф."
                ),
            )

    def commit_pdf(self, user: Optional[User], db) -> None:
        """Зафиксировать расход PDF ПОСЛЕ успешной генерации файла."""
        if user is None or db is None:
            return
        flags = TIER_FLAGS.get(user.tier, TIER_FLAGS["free"])
        if not flags["pdf_export"]:
            return
        if flags.get("pdf_per_month") is None:
            return  # безлимитным тарифам счётчик не нужен
        increment_monthly_usage(db, str(user.id), "pdf")


tier_limiter = TierRateLimiter()

# Алиасы для совместимости с задачей 2
TIER_LIMITS = TIER_FLAGS

def get_tier_limits(tier: str) -> dict:
    return TIER_FLAGS.get(tier, TIER_FLAGS["free"])
