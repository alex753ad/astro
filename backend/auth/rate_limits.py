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

import math
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, Request, status

from backend.limiter import client_ip
from backend.config import get_settings
from backend.auth.jwt import decode_token
from backend.models import User

settings = get_settings()


# ═══════════════════════════════════════════════════════════
# TIER FLAGS
# ═══════════════════════════════════════════════════════════

TIER_FLAGS: dict[str, dict] = {
    "free": {
        # 09.09.2026: было 500. Замер настоящего разбора на боевом
        # free-аккаунте дал 1067 слов — вдвое больше заявленного, потому
        # что рядом с числом слов в промпте стояло независимое число
        # абзацев (см. _volume_plan в interpretation/prompts.py). После
        # того как абзацы стали производными, целевые 450 попадают в
        # заявленную владельцем вилку 400–500 слов.
        "interpretation_word_limit": 450,
        "interpretations_per_month": 0,        # только превью (блюр)
        "first_interpretation_free": True,     # 3.3: одна полная интерпретация навсегда
        "charts_per_day": None,
        # 08.09.2026: было 0. Ноль здесь означал «AI-разбор не входит», а не
        # «списка транзитов нет», и длину списка free держала отдельная
        # константа FREE_TRANSITS_TEASER_MONTHS мимо флага — два числа об
        # одном и том же. Решение E2 (список транзитов виден ВСЕМ тарифам,
        # платят за AI-разбор аспектов) от этого не меняется: платное здесь
        # описывают transits_ai/transits_ai_per_month ниже, оба нулевые.
        "transits_months": 3,
        "transits_ai": False,
        "transits_ai_per_month": 0,
        # Пробные разборы транзитов и сообщения чата — на всё время аккаунта,
        # на любые транзиты (решение владельца 28.09.2026). Счёт с нуля: у
        # free раньше счётчика не было. Период счётчика — TRIAL_PERIOD.
        "transits_ai_trial": 2,
        "chat_trial": 3,
        "chat_per_month": 0,
        # Экспорт событий в Google Календарь: сколько РАЗНЫХ карт можно
        # выгружать (решение владельца 29.09.2026). 0 — нельзя, None — все.
        # Держит /calendar/export-allowed; витрина — tierCatalog LIMITS.gcal.
        "gcal_charts": 0,
        "profiles_limit": 2,    # 19.08.2026: было 1 — «Карты» на /pricing, единственный источник этого числа
        "lunar_months": 1,                     # текущий месяц
        "planner_months": 0,
        # Недели «Луны по домам» с расшифровкой ВПЕРЁД, считая текущую
        # (решение владельца 16.09.2026). Завершённые проходы открыты всем
        # тарифам мимо этого числа — см. is_moon_week_locked().
        #
        # ⚠️ None = «всё окно ленты», по общему правилу этого файла (так же
        # записаны безлимиты interpretations_per_month и profiles_limit).
        # У free это единица — текущая неделя и не дальше.
        "planner_weeks_ahead": 1,
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
        "transits_months": 6,                  # 31.08.2026: было 1 — решение владельца, платный не хуже free-витрины
        "transits_ai": False,                  # полный AI-доступ — нет
        # 28.09.2026: было 3 — решение владельца. Разбор стоит ≈0,35–0,7 ₽
        # (DeepSeek Pro, ≈2500 токенов входа и ≈1000 выхода), 15 в месяц — до
        # ≈11 ₽ при цене тарифа 790 ₽. «Без лимита» остаётся отличием Лиры.
        "transits_ai_per_month": 15,
        "chat_per_month": 30,                  # 28.09.2026: чат открыт Веге
        "gcal_charts": 1,                      # одна карта
        "profiles_limit": 5,    # 19.08.2026: было 1 — «Карты» на /pricing, единственный источник этого числа
        "lunar_months": 12,                    # на год
        "planner_months": 3,                   # 3.4a: было 1
        # Всё окно ленты: на платном тарифе замков на проходах Луны нет
        # вовсе (решение владельца 16.09.2026).
        "planner_weeks_ahead": None,
        "synastry": False,
        "pdf_export": True,
        "pdf_per_month": 5,     # 19.08.2026: было безлимитно — новая сетка
        "ai_engine": settings.deepseek_model_pro,
    },
    "pro": {
        "interpretation_word_limit": 2500,
        "interpretations_per_month": 15,       # = числу карт (19.08.2026)
        "charts_per_day": None,
        "transits_months": 12,                 # 31.08.2026: было 3 — решение владельца, платный не хуже free-витрины
        "transits_ai": True,
        "transits_ai_per_month": None,         # безлимит
        "gcal_charts": None,                   # все карты
        "profiles_limit": 15,   # 19.08.2026: было 5 — «Карты» на /pricing, единственный источник этого числа
        "lunar_months": 12,
        "planner_months": 12,
        "planner_weeks_ahead": None,
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
        "gcal_charts": None,
        "profiles_limit": None,
        "lunar_months": None,   # 19.08.2026: было 12 — «безлимит» по новой сетке (12 = как у Pro, не дифференциатор)
        "planner_months": 12,
        "planner_weeks_ahead": None,
        # 31.08.2026: снято с True — решение владельца (AUDIT, FIXES_19).
        # Флаг обещал Ориону функцию, недоступную никому: эндпоинты
        # /chart/synastry и /synastry/interpret за require_admin,
        # SynastryPage редиректит не-админа. Фронт его и не читал (пункт
        # меню шёл по user?.is_admin, не по флагу) — вреда не было, но
        # TIER_FLAGS обязан быть источником правды, а не аспирацией.
        # Вернуть True ТЕМ ЖЕ заходом, что снимет require_admin с обеих
        # ручек в advanced_charts_router.py и редирект в SynastryPage.jsx.
        "synastry": False,
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


# ── Горизонт транзитов: бэкстоп по прошлому ─────────────────────────────────
#
# Вперёд горизонт считается по тарифному `transits_months` и только по нему.
# До 08.09.2026 у free это число жило вторым местом — константой
# FREE_TRANSITS_TEASER_MONTHS (3) в обход флага, при котором сам флаг стоял
# нулём. Мотив был в том, чтобы не смешивать в одном числе «что человек
# видит» и «за что платит»; на деле смешения и не было — за AI-разбор
# отвечают отдельные флаги `transits_ai` / `transits_ai_per_month`, а флаг
# длины списка описывал длину списка. Два числа об одном и том же успели
# разойтись по смыслу: сервер отдавал `features.transits = false` при живой
# витрине на 3 месяца, и фронтенду пришлось обходить это вручную.
#
# ⚠️ Остаётся в силе то, ради чего константа заводилась:
# 1. free НЕ должен видеть дальше платного тарифа — при следующей правке
#    сетки проверить, что `transits_months` у free не обгоняет ни один
#    платный (тест test_free_teaser_never_beats_a_paid_tier);
# 2. число НЕ должно стать нулём: под блюром должно быть что показать,
#    иначе FreePlanBanner со счётчиком закрытых транзитов и
#    PlanComparisonModal остаются без данных, и апселл не на чем строить;
# 3. число обязано совпадать с `FREE_TRANSITS_TEASER_MONTHS` в
#    `frontend/src/constants.js` — фронтенд для free горизонт с сервера НЕ
#    запрашивает (TransitTimeline.jsx, ветка `isFree`), а берёт свою
#    константу. Расхождение = free запрашивает больше, чем разрешает
#    сервер, и получает 403 на витрине. Синхронность закреплена тестом
#    `frontend/src/api/transitsHorizon.test.js` (читает оба файла).

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

    Единственный источник — тарифный `transits_months`, включая free (см.
    блок выше: отдельной константы под free с 08.09.2026 нет).
    """
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
        # С 28.09.2026 чат есть на всех тарифах: free — 3 сообщения на пробу,
        # Вега — chat_per_month, Лира и Орион — без лимита (check_chat_limit).
        "rag_chat": True,
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


# Здесь до 09.09.2026 стояли interpret_free_key / interpret_pro_key /
# interpret_premium_key с комментарием «/interpret — два ключа, два декоратора
# в main.py». Комментарий описывал состояние, которого не было с 27.05.2026:
# декораторы `@limiter.limit(..., key_func=interpret_free_key)` снял коммит
# `3041ef1`, а сами функции остались и три с половиной месяца читались как
# действующий механизм лимита на интерпретации. Вызывающих на момент удаления
# не было ни одного (grep по backend и frontend).
#
# Удалены не только за мёртвость: они считали ключ через `_base_id`, то есть
# были третьей копией того же дефекта, что чинился в rag_chat_key и export_key
# (первые 60 символов JWT вместо user_id). Оживить их «как есть» значило бы
# вернуть склейку аккаунтов по началу UUID. Понадобится лимит на интерпретации
# снова — писать по образцу rag_chat_key, а не восстанавливать эти три.


def _token_user_id(request: Request) -> Optional[str]:
    """user_id из ПОДПИСАННОГО access-токена, иначе None.

    Подпись здесь обязательна, а не для порядка: ключ лимита, который можно
    назвать самому, позволил бы любому желающему выбрать чужие 20 запросов в
    час, просто подставив чужой id. `decode_token` проверяет подпись (и срок),
    поэтому назвать чужой id нельзя — можно только предъявить чужой токен, а
    это уже не проблема лимитера.

    Любая ошибка разбора — None, а не исключение: ключ считается до
    обработчика, и падение здесь превратило бы протухший токен в 500 вместо
    честного 401.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        return decode_token(auth[7:]).user_id
    except Exception:  # noqa: BLE001 — см. докстринг: ключ не имеет права падать
        return None


# /rag-chat — счёт по владельцу токена, а не по IP: эндпоинт платный (Pro+),
# и лимит должен ограничивать аккаунт, а не офис за общим NAT.
#
# ⚠️ Ключ — user_id из токена, а НЕ сам токен. Здесь стоял `_base_id`, то есть
# первые 60 символов JWT; из них на пользователя приходились ровно 8 hex-символов
# UUID — проверено разбором реального токена: заголовок занимает 36 символов,
# точка ещё один, и на payload остаётся кусок, декодирующийся как `{"sub":"0f8c1a2b-`.
# Значит два аккаунта с совпадающим НАЧАЛОМ UUID делили одно ведро на 20 запросов
# в час: первый выбирал лимит, второй получал 429 за чужую активность.
#
# ⚠️ Свойство, которое здесь легко потерять правкой: ключ обязан переживать
# обновление токена. Прежний вариант это свойство имел случайно — `sub` стоит в
# payload первым (`create_access_token`), поэтому меняющиеся `jti`/`iat`/`exp` в
# первые 60 символов не попадали. Достаточно было переставить claim'ы местами,
# чтобы каждый refresh обнулял лимит и лимита фактически не стало. Теперь
# свойство прямое: user_id при обновлении не меняется по определению.
# Закреплено `TestRagChatKeySurvivesRefresh`.
def rag_chat_key(request: Request) -> str:
    user_id = _token_user_id(request)
    if user_id:
        return f"rag:user:{user_id}"
    # Токена нет или он нечитаем — до обработчика такой запрос всё равно не
    # дойдёт (401). Ведро по IP оставлено, чтобы неаутентифицированные запросы
    # не сходились в один общий ключ на всех.
    return f"rag:{_base_id(request)}"


# Обращения в поддержку и жалобы (POST /feedback, 27.09.2026). Вошедший —
# по user_id: за общим NAT (мобильный оператор, офис) лимит по IP делили бы
# все, и пятое за час чужое обращение отбивало бы твоё. Аноним — по IP, и
# именно client_ip, а не `_base_id`: ручка открыта без входа, и ключ по
# строке неподписанного токена позволял бы получать новое ведро на каждый
# запрос, просто меняя мусор в заголовке.
def feedback_key(request: Request) -> str:
    user_id = _token_user_id(request)
    if user_id:
        return f"feedback:user:{user_id}"
    return f"feedback:ip:{client_ip(request)}"


# Гость приложения (анонимная карта, 27.09.2026): карта и прогноз без входа.
# Каждая анонимная карта — это ещё и прогноз модели на каждый день, то есть
# расход бюджета DeepSeek, который никто не оплачивает. Поэтому у гостя свой
# суточный потолок по IP; вошедшим он не мешает — у них ключ по user_id и
# лимит заведомо недостижимый (их держат тарифные лимиты).
GUEST_UNLIMITED = "10000/day"


def guest_key(request: Request) -> str:
    user_id = _token_user_id(request)
    if user_id:
        return f"guest:user:{user_id}"
    return f"guest:ip:{client_ip(request)}"


def guest_limit(daily: str):
    """Лимит slowapi, зависящий от ключа: `daily` — только гостю (ключ по IP)."""
    def provider(key: str) -> str:
        return daily if key.startswith("guest:ip:") else GUEST_UNLIMITED
    return provider


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
                f"Подожди минуту и повтори."
            ),
        )


# Экспорт данных (152-ФЗ) — тяжёлый запрос (все карты, интерпретации,
# платежи), счёт по владельцу токена, чтобы не ограничивать общий NAT/офис.
#
# ⚠️ Ключ — user_id, а НЕ строка токена, по той же причине, что у rag_chat_key
# (разбор — в комментарии над ним): `_base_id` брал первые 60 символов JWT, из
# которых на пользователя приходились 8 hex-символов UUID, и два аккаунта с
# совпадающим началом идентификатора делили одно ведро. Здесь ведро — 3 запроса
# в час, то есть склейка ощутимее, чем у чата: человек, которому по 152-ФЗ
# положен доступ к своим данным, получал бы 429 из-за чужой выгрузки.
#
# Свойство «ключ переживает обновление токена» обязано сохраниться и здесь:
# выгрузка тяжёлая, и лимит, обнуляемый каждым refresh, не ограничивал бы
# ничего. Закреплено TestExportKeySurvivesRefresh.
def export_key(request: Request) -> str:
    user_id = _token_user_id(request)
    if user_id:
        return f"export:user:{user_id}"
    # Токена нет или он нечитаем — до обработчика такой запрос не дойдёт (401).
    return f"export:{_base_id(request)}"




# ═══════════════════════════════════════════════════════════
# DAILY INTERPRETATION COUNTER
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
# PERSISTENT MONTHLY USAGE COUNTERS (usage_counters table)
# ═══════════════════════════════════════════════════════════

# Счётчики «на всё время аккаунта» (пробные разборы и сообщения free) живут в
# той же таблице UsageCounter с этим периодом вместо месяца.
TRIAL_PERIOD = "ALL"

# ── Окно счётчика: оплаченный период, а не календарный месяц (065) ──────────
#
# Решение владельца 28.09.2026. Доступ даётся на 30 дней с даты оплаты
# (payments/common.PERIOD_DAYS), а счётчики обнулялись 1-го числа: купивший
# 29 сентября получал два лимита за несколько дней. Теперь у платного тарифа
# окно — 30 дней от `Subscription.usage_anchor`:
#   * новая покупка и смена тарифа (Вега → Лира) ставят якорь «сейчас» —
#     свежий счётчик;
#   * продление того же тарифа якорь не трогает: срок прибавляется в конец,
#     и следующее окно начинается ровно там, где кончилось оплаченное;
#   * бонусные дни (реферал) удлиняют доступ, окна остаются по 30 дней.
# Бесплатный тариф (1 PDF в месяц) — по-прежнему календарный месяц; пробные
# free — TRIAL_PERIOD, навсегда, их это не касается.
#
# ⚠️ Ключ окна содержит якорь: «ггммддЧЧММ.k». Смена тарифа меняет якорь, и
# счётчик начинается с нуля даже при том же номере окна k.
PAID_WINDOW = timedelta(days=30)
MSK = timedelta(hours=3)


def _now() -> datetime:
    """Текущее время UTC без пояса — как в колонках БД. Отдельной функцией,
    чтобы тесты окон (покупка 29-го, продление) подменяли время."""
    return datetime.utcnow()


def _current_period_ym() -> str:
    """Текущий календарный месяц в формате 'YYYY-MM' (UTC)."""
    return _now().strftime("%Y-%m")


def _active_subscription(db, user_id: str, now: datetime):
    from backend.models import Subscription
    return (
        db.query(Subscription)
        .filter(Subscription.user_id == str(user_id), Subscription.status == "active",
                Subscription.current_period_end > now)
        .order_by(Subscription.current_period_end.desc())
        .first()
    )


def _derived_anchor(end: datetime, now: datetime) -> datetime:
    """Якорь для подписки без записанного: окна кончаются ровно в end."""
    n = max(1, math.ceil((end - now) / PAID_WINDOW))
    return end - n * PAID_WINDOW


def usage_window(db, user_id: str, now: datetime | None = None) -> dict | None:
    """Текущее окно счётчика платного тарифа; None — оплаченного срока нет
    (бесплатный тариф или срок истёк) и считается календарный месяц.

    key          — значение period_ym счётчиков этого окна;
    fresh_at     — когда начнётся новое окно, если оно ещё внутри оплаченного
                   срока (оплачено продление); None — новые только после
                   продления;
    access_until — конец оплаченного доступа.
    """
    now = now or _now()
    sub = _active_subscription(db, user_id, now)
    if sub is None:
        return None
    anchor = sub.usage_anchor or _derived_anchor(sub.current_period_end, now)
    k = max(0, int((now - anchor) // PAID_WINDOW))
    window_end = anchor + (k + 1) * PAID_WINDOW
    return {
        "key": f"{anchor:%y%m%d%H%M}.{k}",
        "fresh_at": window_end if window_end < sub.current_period_end else None,
        "access_until": sub.current_period_end,
    }


def current_period_key(db, user_id: str) -> str:
    w = usage_window(db, user_id)
    return w["key"] if w else _current_period_ym()


def msk_date(dt: datetime | None) -> str | None:
    """UTC-время из базы → дата по Москве 'YYYY-MM-DD' (так её показывают клиенты)."""
    return (dt + MSK).date().isoformat() if dt else None


def usage_dates(db, user_id: str) -> dict:
    """Даты для текста «закончились — …», одинаковые для API и отказов.

    resets_on    — когда счётчик обновится сам (МСК); None — только после
                   продления;
    access_until — до какого дня оплачен доступ (МСК); None — у бесплатного.
    Клиенты эти даты не вычисляют (решение владельца 28.09.2026).
    """
    w = usage_window(db, user_id)
    if w is None:
        y, m = map(int, _current_period_ym().split("-"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return {"resets_on": f"{y:04d}-{m:02d}-01", "access_until": None}
    return {"resets_on": msk_date(w["fresh_at"]), "access_until": msk_date(w["access_until"])}


def ru_day_month(iso: str) -> str:
    """'2026-10-01' → '1 октября'."""
    months = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря")
    y, m, d = map(int, iso.split("-"))
    return f"{d} {months[m - 1]}"


def ended_tail(db, user_id: str) -> str:
    """«— обновятся 1 октября» или «— новые после продления, доступ до 29
    октября». Общий хвост текстов отказа по месячным лимитам."""
    d = usage_dates(db, user_id)
    if d["resets_on"]:
        return f" — обновятся {ru_day_month(d['resets_on'])}"
    if d["access_until"]:
        return f" — новые после продления, доступ до {ru_day_month(d['access_until'])}"
    return ""


def get_monthly_usage(db, user_id: str, kind: str, period: str | None = None) -> int:
    """Сколько единиц `kind` израсходовано в текущем окне (оплаченный период
    у платного, календарный месяц у бесплатного) или в `period`, например
    TRIAL_PERIOD — за всё время."""
    from backend.models import UsageCounter
    row = (
        db.query(UsageCounter)
        .filter(
            UsageCounter.user_id == user_id,
            UsageCounter.kind == kind,
            UsageCounter.period_ym == (period or current_period_key(db, user_id)),
        )
        .first()
    )
    return row.count if row else 0


def increment_monthly_usage(db, user_id: str, kind: str, period: str | None = None) -> int:
    """Атомарно +1 к счётчику текущего окна (или `period`). Возвращает новое значение."""
    from backend.models import UsageCounter
    period = period or current_period_key(db, user_id)
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
                detail="Войди в аккаунт, чтобы получить разбор карты.",
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
                    "Бесплатный разбор этой карты уже использован. "
                    f"Оформи {TIER_NAMES['lite']}, чтобы разбирать карты дальше."
                ),
            )

        if limit == 0:
            from backend.email_service import TIER_NAMES
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Разбор карты недоступен на тарифе {TIER_NAMES['free']}. Оформи {TIER_NAMES['lite']}.",
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
                    f"Разборы карты закончились ({limit} за оплаченный период на тарифе "
                    f"{TIER_NAMES.get(tier, tier.capitalize())}){ended_tail(db, str(user.id))}. "
                    "Или оформи тариф повыше."
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
        """Доступ к ПРОСМОТРУ транзитов (без AI).

        ⚠️ Вызывающих нет и не планируется, а с 08.09.2026 (free
        transits_months = 3) её 403 недостижим ни для одного тарифа сетки —
        условие ниже больше не выполняется нигде. Оставлена как есть:
        реальный гейт горизонта идёт через transits_date_window, см.
        комментарий в main.py у проверки диапазона. Не «оживлять» её,
        подставив другое условие — список транзитов открыт всем тарифам
        (решение E2), платный там только AI-разбор.
        """
        tier = user.tier if user else "free"
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
        if flags["transits_months"] == 0:
            from backend.email_service import TIER_NAMES
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Транзиты недоступны на {TIER_NAMES['free']} плане. Оформи {TIER_NAMES['lite']}.",
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
                detail=f"Разбор транзитов доступен на тарифе {TIER_NAMES['lite']} и выше.",
            )

        # Lite — квота в месяц
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Войди в аккаунт, чтобы получить разбор транзита.",
            )
        if db is None:
            return
        used = get_monthly_usage(db, str(user.id), "transit_ai")
        if used >= quota:
            from backend.email_service import TIER_NAMES
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Разборы транзитов закончились ({quota} за оплаченный период на тарифе "
                    f"{TIER_NAMES['lite']}){ended_tail(db, str(user.id))}. "
                    f"На {TIER_NAMES['pro']} — без лимита."
                ),
            )

    def check_transit_trial(self, user: Optional[User], db) -> None:
        """Free: пробные разборы транзитов — `transits_ai_trial` на всё время
        аккаунта, на любые транзиты. Без входа — 403 (клиент зовёт войти)."""
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Войди в аккаунт, чтобы получить разбор транзита.",
            )
        if transit_trials_left(db, user) <= 0:
            from backend.email_service import TIER_NAMES
            # 403, а не 429: клиенты читают 403 как «отказ по тарифу» и
            # показывают предложение; 429 у разбора — месячная квота Веги.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Пробные разборы транзитов закончились. На тарифе {TIER_NAMES['lite']} — "
                    f"{TIER_FLAGS['lite']['transits_ai_per_month']} в месяц, "
                    f"на {TIER_NAMES['pro']} — без лимита."
                ),
            )

    def check_chat_limit(self, user: User, db) -> None:
        """Чат: free — `chat_trial` на всё время, Вега — `chat_per_month`,
        Лира и Орион — без лимита. Отказ — 429 с понятным текстом; клиент
        показывает своё предложение по правилу offerRule.js."""
        left, period = chat_quota(db, user)
        if left is not None and left <= 0:
            from backend.email_service import TIER_NAMES
            # 403, а не 429: 429 у чата — антифлуд slowapi (20 в час), и клиент
            # обязан их различать — там «подожди», здесь «тариф» (chatRules.js).
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    ("Пробные сообщения закончились. " if period == "trial"
                     else f"Сообщения закончились{ended_tail(db, str(user.id))}. ")
                    + f"На тарифе {TIER_NAMES['lite']} — {TIER_FLAGS['lite']['chat_per_month']} в месяц, "
                    f"на {TIER_NAMES['pro']} — без лимита."
                ),
            )

    def commit_chat(self, user_id: str, tier: str, db) -> None:
        """Списать сообщение ПОСЛЕ выданного ответа (фоном, rag_router)."""
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
        if flags.get("chat_trial"):
            increment_monthly_usage(db, user_id, "chat_trial", TRIAL_PERIOD)
        elif flags.get("chat_per_month"):
            increment_monthly_usage(db, user_id, "chat")

    def commit_transit_ai(self, user: Optional[User], db) -> None:
        """Зафиксировать расход AI-транзита ПОСЛЕ успешной генерации: Lite —
        месячная квота, free — пробные на всё время."""
        if user is None or db is None:
            return
        tier = user.tier
        flags = TIER_FLAGS.get(tier, TIER_FLAGS["free"])
        if flags["transits_ai"]:
            return  # безлимитным тарифам счётчик не нужен
        if flags.get("transits_ai_trial"):
            increment_monthly_usage(db, str(user.id), "transit_trial", TRIAL_PERIOD)
            return
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
                    f"Оформи {TIER_NAMES['lite']}."
                ),
            )

        # Недостижимо, пока free не имеет pdf_export: аноним получает tier
        # "free" и отбивается веткой выше. Оставлено как страховка на случай,
        # если флаг когда-нибудь откроют бесплатному тарифу.
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Войди в аккаунт, чтобы скачать PDF-отчёт.",
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
                    f"PDF-отчёты закончились{ended_tail(db, str(user.id))}. Тариф "
                    f"{TIER_NAMES.get(tier, tier.capitalize())} даёт {quota} "
                    f"{'в месяц' if tier == 'free' else 'за оплаченный период'}. "
                    "Оформи тариф повыше."
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


# ═══════════════════════════════════════════════════════════
# ОСТАТКИ ПРОБНЫХ И МЕСЯЧНЫХ (28.09.2026) — их же отдаёт /payments/subscription
# ═══════════════════════════════════════════════════════════

def transit_trials_left(db, user) -> Optional[int]:
    """Сколько пробных разборов транзитов осталось; None — у тарифа их нет."""
    trial = TIER_FLAGS.get(user.tier, TIER_FLAGS["free"]).get("transits_ai_trial")
    if not trial:
        return None
    return max(0, trial - get_monthly_usage(db, str(user.id), "transit_trial", TRIAL_PERIOD))


def chat_quota(db, user) -> tuple[Optional[int], Optional[str]]:
    """(остаток, период): ("trial" — на всё время, "month" — в этом месяце).
    (None, None) — без лимита."""
    flags = TIER_FLAGS.get(user.tier, TIER_FLAGS["free"])
    if flags.get("chat_trial"):
        used = get_monthly_usage(db, str(user.id), "chat_trial", TRIAL_PERIOD)
        return max(0, flags["chat_trial"] - used), "trial"
    if flags.get("chat_per_month"):
        return max(0, flags["chat_per_month"] - get_monthly_usage(db, str(user.id), "chat")), "month"
    return None, None
