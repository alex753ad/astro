"""Что чат знает о приложении: ответы о продукте и контекст P1.

Решения владельца 02.10.2026 (тексты — таблицей до кода). Общий модуль для
ручки чата (rag_router) и прогона вопросов (scripts/chat_eval.py): разойдутся
— прогон проверит не то, что видит человек.

Две части, и устроены они противоположно:

* **Ответы о продукте** (`product_reply`) — фиксированные тексты, числа из
  TIER_FLAGS и PRICE_SCHEDULE. Модель их не пишет: цену и условия возврата
  нельзя доверить генерации. Классификатор темы отправляет сюда вопросы о
  тарифах, остатке сообщений, отмене и навигации (rag_router).
* **Контекст P1** (`day_block`, `upcoming_block`, `tier_block`) — данные для
  модели, под флагом chat_planner_context. Источники — те же функции, что
  показывают это человеку: прогноз дня (forecast/facts.compute_day и его
  кэш), главное событие (day_event.main_event), «Неделя вперёд»
  (day_event.week_events), лента (feed/builder.build_feed).

Синхронные части (Swiss Ephemeris) — из async только через to_thread.
"""
from __future__ import annotations

from datetime import date, timedelta

from backend.ephemeris.ru_names import PLANET_RU

# ── ответы о продукте ─────────────────────────────────────────────────────────

PRODUCT_TOPICS = ("tariffs", "quota", "cancel", "navigation")

TIER_NAMES = {"free": "Бесплатный", "lite": "Вега", "pro": "Лира", "premium": "Орион"}
_TIER_PREP = {"lite": "Веге", "pro": "Лире", "premium": "Орионе"}

NAVIGATION = (
    "Коротко, где что. В приложении: прогноз дня, события и фазы Луны — «Лента»; "
    "твоя карта, «Разбор карты →» и «PDF-отчёт →» — «Карта»; тариф, «История "
    "разборов», «Уведомления», «Друзья», поддержка — «Ещё». На сайте: «Натальная "
    "карта», «Timeline Планер», «Лунный календарь», тарифы и подписка — «Профиль»."
)

# ⚠️ Условия возврата — строго по оферте (TermsPage.jsx, раздел 4.3 и 6),
# цитата согласована владельцем. Меняется оферта — меняется этот текст.
CANCEL = (
    "Отменять ничего не нужно: автопродления нет. Оплата даёт доступ на 30 дней, "
    "потом деньги сами не спишутся. Вернуть деньги можно в любой момент оплаченного "
    "срока — пропорционально неиспользованным дням, за вычетом подтверждённых "
    "расходов. Для этого напиши заявление на carearistea@mail.ru: причину и "
    "подтверждение оплаты. Возврат — в течение 10 дней, тем же способом, которым "
    "была оплата."
)


def _plural(n: int, one: str, few: str, many: str) -> str:
    m10, m100 = n % 10, n % 100
    if m10 == 1 and m100 != 11:
        return one
    if 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        return few
    return many


def _count(n, forms: tuple[str, str, str], unlimited: str) -> str:
    return unlimited if n is None else f"{n} {_plural(n, *forms)}"


_MSG = ("сообщение", "сообщения", "сообщений")
_READ = ("разбор карты", "разбора карты", "разборов карты")
_TRANS = ("разбор транзитов", "разбора транзитов", "разборов транзитов")
_MONTHS = ("месяц", "месяца", "месяцев")


def _tariffs(tier: str) -> str:
    from backend.auth.rate_limits import TIER_FLAGS
    from backend.payments.common import prices_on

    price = prices_on()
    f = {t: TIER_FLAGS[t] for t in ("free", "lite", "pro", "premium")}

    def chat(t):
        n = f[t].get("chat_per_month")
        return "чат без лимита" if not n else f"{_count(n, _MSG, '')} в чате в месяц"

    def reads(t):
        return _count(f[t]["interpretations_per_month"], _READ, "разборы карты без лимита")

    def trans(t):
        return _count(f[t]["transits_ai_per_month"], _TRANS, "разборы транзитов без лимита")

    def horizon(t):
        n = f[t]["transits_months"]
        return f"транзиты на {n} {_plural(n, *_MONTHS)}"

    lines = [
        "Доступ на 30 дней, без автопродления.",
        f"· Вега — {price['lite']} ₽: {chat('lite')}, {reads('lite')}, {trans('lite')}, {horizon('lite')} вперёд.",
        f"· Лира — {price['pro']} ₽: {chat('pro')}, {reads('pro')}, {trans('pro')}, {horizon('pro')}, долгосрочные периоды.",
        f"· Орион — {price['premium']} ₽: всё без лимита, {horizon('premium')}, кабинет астролога.",
        f"Сейчас у тебя — {'бесплатный тариф' if tier == 'free' else TIER_NAMES.get(tier, tier)}. "
        "Сравнить подробно: в приложении — «Ещё» → карточка тарифа, на сайте — страница тарифов.",
    ]
    return "\n".join(lines)


def _quota(tier: str, left, period, dates: dict | None) -> str:
    from backend.auth.rate_limits import TIER_FLAGS, ru_day_month

    if left is None:
        return f"На {_TIER_PREP.get(tier, TIER_NAMES.get(tier, tier))} чат без лимита — пиши сколько нужно."
    if period == "trial":
        trial = TIER_FLAGS["free"]["chat_trial"]
        lite = TIER_FLAGS["lite"]["chat_per_month"]
        return (f"На бесплатном — {_count(trial, _MSG, '')} на пробу, осталось {left}. "
                f"Дальше чат открыт на Веге ({lite} в месяц), на Лире и Орионе — без лимита.")
    # Вега: счётчик живёт в окне оплаченного срока (rate_limits.usage_window),
    # а не в календарном месяце. Дата — конец ЭТОГО окна: начало следующего
    # (продление оплачено заранее) или конец доступа.
    limit = TIER_FLAGS.get(tier, {}).get("chat_per_month") or TIER_FLAGS["lite"]["chat_per_month"]
    when = (dates or {}).get("resets_on") or (dates or {}).get("access_until")
    tail = f" — до {ru_day_month(when)}" if when else ""
    return f"Осталось {left} из {limit}{tail}."


def product_reply(topic: str, tier: str, left=None, period=None, dates: dict | None = None) -> str:
    if topic == "tariffs":
        return _tariffs(tier)
    if topic == "quota":
        return _quota(tier, left, period, dates)
    if topic == "cancel":
        return CANCEL
    return NAVIGATION


# ── контекст P1 (флаг chat_planner_context) ──────────────────────────────────

# Правило «чего нет — скажи, где посмотреть»: места согласованы владельцем
# 02.10.2026 (таблица шага 5), те же названия, что в NAVIGATION.
WHERE_RULES = """
## Чего нет в данных — скажи, где посмотреть
Не придумывай. Если нужного для ответа нет в данных выше, скажи, где это открыть:
- текст прогноза дня, фазы Луны — «Лента»;
- разбор карты — «Карта» → «Разбор карты →», прошлые разборы — «Ещё» → «История разборов»;
- разбор транзита — «Лента», нажать на событие;
- PDF-отчёт — «Карта» → «PDF-отчёт →»;
- планер дальше месяца — на сайте, «Timeline Планер»;
- карта другого человека — открыть чат на его карте.

## Сверяйся с днём
О сегодняшнем дне не противоречь блоку «День»: это прогноз дня и уведомление, которые человек видит в приложении. Главное событие называй так же, как в уведомлении.
"""


def _dm(d) -> str:
    return f"{d:%d.%m}"


def day_block(chart, local_date: date, tzname: str, daily_time, quiet_from,
              forecast_paragraphs: list[str] | None = None) -> str:
    """Прогноз дня и главное событие — то, что человек видит сегодня."""
    from zoneinfo import ZoneInfo
    from backend import day_event
    from backend.forecast.facts import compute_day
    from backend.forecast.meanings import HOUSE_FOCUS, MOON_SIGN_MOOD, NATAL_SPHERE, TONE_RU

    facts = compute_day(chart, local_date, ZoneInfo(tzname))
    lines = ["## День — то же, что человек видит в приложении (прогноз дня и уведомление)",
             f"Дата: {local_date:%d.%m.%Y}.",
             f"Луна в знаке {facts.moon_sign}: {MOON_SIGN_MOOD.get(facts.moon_sign, '')}."]
    for h in facts.houses:
        focus, actions = HOUSE_FOCUS[h]
        lines.append(f"Луна проходит {h} дом — {focus} (подходит: {actions}).")
    for a in facts.aspects:
        lines.append(f"Касание Луны к натальной точке {PLANET_RU.get(a['natal'], a['natal'])}: "
                     f"{TONE_RU[a['tone']]}, тема — {NATAL_SPHERE.get(a['natal'], '')}.")
    ev = day_event.main_event(chart, local_date, tzname, daily_time, quiet_from)
    if ev:
        lines.append(f"Главное событие дня (утреннее уведомление): «{day_event.title(ev)}». "
                     f"Совет в уведомлении: «{day_event.advice(ev).rstrip('.')}».")
    else:
        lines.append("Главного события в этот день нет.")
    if forecast_paragraphs:
        lines.append("Текст прогноза дня, который человек видит:\n" + "\n".join(forecast_paragraphs))
    return "\n".join(lines) + "\n"


def _retro_now(today: date, tzname: str) -> list[str]:
    """Планеты, ретроградные сегодня, с местной датой конца.

    Станции — compute_retrograde_stations, та же функция, что у ленты и
    «Ближайших 30 дней» (шаг 6 аудита). До 04.10.2026 здесь был свой
    посуточный скан скорости в 12:00 UTC — дата конца могла разойтись с
    лентой на сутки. Ретроградна та, чья ближайшая станция — конец петли;
    250 суток покрывают самую долгую петлю (Плутон, ~160 суток).
    """
    from backend.transit.house_passages import compute_retrograde_stations

    first: dict[str, dict] = {}
    for r in compute_retrograde_stations(today, today + timedelta(days=250), tzname):
        if r["planet"] not in first or r["at"] < first[r["planet"]]["at"]:
            first[r["planet"]] = r
    return [f"{r['planet_name']} (до {_dm(date.fromisoformat(r['date_iso']))})"
            for r in first.values() if r["status"] == "end"]


def upcoming_block(chart, today: date, tzname: str, daily_time, quiet_from, tier: str | None) -> str:
    """«Неделя вперёд», фазы Луны и ретроградность на 30 дней — из ленты."""
    from backend import day_event
    from backend.feed.builder import build_feed

    lines = ["## Ближайшее — из ленты приложения"]
    week = day_event.week_events(chart, today, tzname, daily_time, quiet_from)
    if week:
        lines.append("Неделя вперёд (как в карточке «Неделя вперёд»): " + "; ".join(
            f"{_dm(ev.at_local)} — {day_event._what(ev)}" for ev in week) + ".")
    feed = build_feed(chart=chart, from_date=today, to_date=today + timedelta(days=30),
                      today=today, tier=tier)
    phases = [e for e in feed["events"] if e["kind"] in ("moon_phase", "eclipse")]
    if phases:
        lines.append("Фазы Луны: " + "; ".join(
            f"{e['at'][8:10]}.{e['at'][5:7]} {e['at'][11:16]} — {e['text']}" for e in phases) + ".")
    now = _retro_now(today, tzname)
    lines.append("Сейчас ретроградны: " + (", ".join(now) if now else "никто") + ".")
    retro = [e for e in feed["events"] if e["kind"] == "retrograde"]
    if retro:
        lines.append("Смены ретроградности: " + "; ".join(
            f"{e['at'][8:10]}.{e['at'][5:7]} — {e['text']}" for e in retro) + ".")
    return "\n".join(lines) + "\n"


def tier_block(tier: str, left, period, dates: dict | None) -> str:
    return ("## Тариф человека\n"
            f"Тариф: {TIER_NAMES.get(tier, tier)}. Сообщения в чате: {_quota(tier, left, period, dates)}\n")
