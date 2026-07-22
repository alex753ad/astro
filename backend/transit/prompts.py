"""Prompts for transit AI interpretation.

Builds system prompts for:
1. Single transit event interpretation (click on timeline event)
2. Period overview (summary of all transits for a date range)
"""

from __future__ import annotations

import json

ASPECT_LABELS_RU = {
    "conjunction": "соединение", "sextile": "секстиль",
    "square": "квадрат", "trine": "трин", "opposition": "оппозиция",
}

_MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _format_degree(deg: float | None) -> str:
    if deg is None:
        return "?"
    d = int(deg)
    m = int(round((deg - d) * 60))
    if m == 60:
        d, m = d + 1, 0
    return f"{d}°{m:02d}'"


def _format_date_ru(iso_date: str | None) -> str:
    if not iso_date:
        return "?"
    from datetime import date as _date
    d = _date.fromisoformat(iso_date)
    return f"{d.day} {_MONTHS_RU[d.month - 1]} {d.year}"


def _build_facts_block(transit_event: dict) -> str:
    """Человекочитаемый блок ФАКТЫ из полей, посчитанных compute_exact_facts —
    ничего из клиентского body здесь не используется как источник фактов."""
    from backend.interpretation.rag import _PLANET_RU, _SIGN_RU

    tp = transit_event.get("transit_planet", "?")
    natal_p = transit_event.get("natal_planet", "?")
    aspect = transit_event.get("aspect_type", "?")
    aspect_ru = ASPECT_LABELS_RU.get(aspect, aspect)
    tp_ru = _PLANET_RU.get(tp, tp)
    natal_p_ru = _PLANET_RU.get(natal_p, natal_p)

    transit_line = f"Транзитная планета: {tp_ru}"
    if transit_event.get("transit_sign"):
        sign_ru = _SIGN_RU.get(transit_event["transit_sign"], transit_event["transit_sign"])
        transit_line += f", {_format_degree(transit_event.get('transit_degree'))} в знаке {sign_ru}"
    if transit_event.get("transit_house"):
        transit_line += f", дом {transit_event['transit_house']}"
    transit_line += ", ретроградный" if transit_event.get("transit_retrograde") else ", директный"

    natal_line = f"Натальная планета: {natal_p_ru}"
    if transit_event.get("natal_sign"):
        sign_ru = _SIGN_RU.get(transit_event["natal_sign"], transit_event["natal_sign"])
        natal_line += f", {_format_degree(transit_event.get('natal_degree'))} в знаке {sign_ru}"
    if transit_event.get("natal_house"):
        natal_line += f", дом {transit_event['natal_house']}"

    aspect_line = f"Аспект: {aspect_ru}"
    if transit_event.get("exact_orb") is not None:
        aspect_line += f", орб {_format_degree(transit_event['exact_orb'])}"

    lines = [transit_line, natal_line, aspect_line]
    if transit_event.get("exact_date"):
        lines.append(f"Точный аспект: {_format_date_ru(transit_event['exact_date'])}")
    if transit_event.get("period_start") and transit_event.get("period_end"):
        lines.append(
            f"Период влияния: {_format_date_ru(transit_event['period_start'])} — "
            f"{_format_date_ru(transit_event['period_end'])}"
        )
    return "\n".join(lines)


TRANSIT_EVENT_PROMPT = """Тебя зовут Астрея, ты — навигатор решений, а не предсказатель.
Тебе дан конкретный транзитный аспект.

## Твоя задача
Написать краткую, но содержательную интерпретацию этого транзита (3–5 абзацев).

## Правила
1. Описывай тенденции и энергии, а НЕ конкретные события.
2. Учитывай контекст натальной карты (знаки, дома).
3. Укажи примерный период действия транзита — из блока ФАКТЫ ниже, не выдумывай даты.
4. Если аспект напряжённый (квадрат, оппозиция) — опиши как зону роста, не как угрозу.
5. Дай практический совет, как использовать энергию транзита.

## ФАКТЫ (посчитаны точно через Swiss Ephemeris, использовать только их)
{facts_block}

## ПРАВИЛА РАБОТЫ С ФАКТАМИ
- Не вычисляй градусы, знаки, дома и даты самостоятельно — только то, что в ФАКТАХ.
- Если чего-то нет в ФАКТАХ — не упоминай это вообще.
- Не добавляй другие транзиты и аспекты, которых нет в ФАКТАХ.
- Не называй даты, которых нет в ФАКТАХ.

## Тон
Ты — Астрея: спокойная, конкретная, без фатализма. Живой язык, без астро-пафоса и клише.

## Натальная карта (контекст)
```json
{natal_context}
```

Напиши интерпретацию на языке: {language}."""


TRANSIT_PERIOD_PROMPT = """Тебя зовут Астрея, ты — навигатор решений, а не предсказатель.
Тебе дан список транзитов за период.

## Твоя задача
Написать обзорную интерпретацию транзитного периода (5–8 абзацев).

## Правила
1. Выдели 3–5 ключевых тем периода (не перечисляй все транзиты по отдельности).
2. Сгруппируй транзиты по темам: карьера, отношения, личностный рост, здоровье.
3. Укажи наиболее значимые даты и почему они важны.
4. Начни с общего тона периода, закончи практическими рекомендациями.
5. Если несколько транзитов усиливают друг друга — отметь это.

## Тон
Ты — Астрея: спокойная, структурированная, практичная. Живой язык, без пафоса и клише.

## Транзиты периода
```json
{transits_json}
```

## Натальная карта (контекст)
```json
{natal_context}
```

Период: {from_date} — {to_date}

Напиши интерпретацию на языке: {language}."""


# ── Template-based transit interpretations (fallback, no AI) ──

TRANSIT_TEMPLATES = {
    # Outer planets — most significant transits
    ("Jupiter", "conjunction"): (
        "Транзит Юпитера в соединении с вашим натальным {natal_planet} — "
        "период расширения и возможностей в сфере, связанной с {natal_planet}. "
        "Это время оптимизма, роста и удачных совпадений. Будьте открыты новому."
    ),
    ("Jupiter", "opposition"): (
        "Транзит Юпитера в оппозиции к натальному {natal_planet} — "
        "момент переоценки и поиска баланса. Возможно чрезмерное расширение; "
        "важно не брать на себя больше, чем можете осилить."
    ),
    ("Jupiter", "square"): (
        "Транзит Юпитера в квадрате к натальному {natal_planet} — "
        "напряжение роста. Желание большего сталкивается с реальными ограничениями. "
        "Это мотивирующий аспект, если направить энергию конструктивно."
    ),
    ("Jupiter", "trine"): (
        "Транзит Юпитера в трине к натальному {natal_planet} — "
        "гармоничный поток удачи и лёгкости. Хорошее время для начинаний, "
        "связанных со сферой {natal_planet}."
    ),
    ("Jupiter", "sextile"): (
        "Транзит Юпитера в секстиле к натальному {natal_planet} — "
        "возможности появляются, но требуют вашей инициативы. "
        "Благоприятный период для развития."
    ),
    ("Saturn", "conjunction"): (
        "Транзит Сатурна в соединении с натальным {natal_planet} — "
        "серьёзный период ответственности и структурирования. "
        "То, что вы строите сейчас, будет определять следующие 7 лет."
    ),
    ("Saturn", "opposition"): (
        "Транзит Сатурна в оппозиции к натальному {natal_planet} — "
        "кульминация цикла, начатого при соединении. Проверка на прочность "
        "того, что вы построили. Время зрелых решений."
    ),
    ("Saturn", "square"): (
        "Транзит Сатурна в квадрате к натальному {natal_planet} — "
        "период испытаний и преодоления. Препятствия указывают на то, "
        "что требует доработки. Терпение и дисциплина — ваши союзники."
    ),
    ("Saturn", "trine"): (
        "Транзит Сатурна в трине к натальному {natal_planet} — "
        "стабильный период, когда усилия приносят конкретные результаты. "
        "Хорошее время для долгосрочного планирования."
    ),
    ("Saturn", "sextile"): (
        "Транзит Сатурна в секстиле к натальному {natal_planet} — "
        "возможность укрепить фундамент. Малые, но устойчивые шаги вперёд."
    ),
    ("Uranus", "conjunction"): (
        "Транзит Урана в соединении с натальным {natal_planet} — "
        "неожиданные перемены и пробуждение. Всё привычное подвергается пересмотру. "
        "Освобождение от старых паттернов."
    ),
    ("Uranus", "opposition"): (
        "Транзит Урана в оппозиции к натальному {natal_planet} — "
        "полярность между свободой и стабильностью. Внешние события "
        "могут потребовать резкой адаптации."
    ),
    ("Uranus", "square"): (
        "Транзит Урана в квадрате к натальному {natal_planet} — "
        "беспокойство и потребность в переменах. Напряжение между "
        "желанием свободы и текущими обязательствами."
    ),
    ("Neptune", "conjunction"): (
        "Транзит Нептуна в соединении с натальным {natal_planet} — "
        "длительный период размывания границ. Повышенная чувствительность, "
        "интуиция, но и риск иллюзий. Доверяйте, но проверяйте."
    ),
    ("Neptune", "opposition"): (
        "Транзит Нептуна в оппозиции к натальному {natal_planet} — "
        "проверка идеалов реальностью. Важно не поддаваться разочарованию, "
        "а искать более зрелую форму мечты."
    ),
    ("Neptune", "square"): (
        "Транзит Нептуна в квадрате к натальному {natal_planet} — "
        "туман и неопределённость. Решения лучше отложить, если возможно. "
        "Период для внутренней работы, а не активных действий."
    ),
    ("Pluto", "conjunction"): (
        "Транзит Плутона в соединении с натальным {natal_planet} — "
        "глубокая трансформация. Что-то должно умереть, чтобы родилось новое. "
        "Этот процесс может быть интенсивным, но освобождающим."
    ),
    ("Pluto", "opposition"): (
        "Транзит Плутона в оппозиции к натальному {natal_planet} — "
        "столкновение с тенью. Внешние конфликты отражают внутренние "
        "процессы трансформации. Время честности с собой."
    ),
    ("Pluto", "square"): (
        "Транзит Плутона в квадрате к натальному {natal_planet} — "
        "мощное давление к изменениям. Борьба за контроль — "
        "внутренняя или внешняя. Отпустите то, что больше не служит вам."
    ),
    # Fast planets — shorter descriptions
    ("Sun", "conjunction"): (
        "Солнечный транзит к натальному {natal_planet} — "
        "день повышенного внимания к темам {natal_planet}. Кратковременный, но яркий акцент."
    ),
    ("Moon", "conjunction"): (
        "Лунный транзит к натальному {natal_planet} — "
        "эмоциональный отклик на темы {natal_planet}. Длится несколько часов."
    ),
    ("Mars", "conjunction"): (
        "Транзит Марса к натальному {natal_planet} — "
        "всплеск энергии и инициативы. Хорошее время для активных действий "
        "в сфере {natal_planet}. Длится 2–3 дня."
    ),
    ("Mars", "square"): (
        "Транзит Марса в квадрате к натальному {natal_planet} — "
        "кратковременное напряжение и раздражение. Направьте энергию "
        "в физическую активность. Длится 2–3 дня."
    ),
    ("Venus", "conjunction"): (
        "Транзит Венеры к натальному {natal_planet} — "
        "приятный период гармонии, красоты и социальных возможностей. "
        "Длится 2–3 дня."
    ),
    ("Mercury", "conjunction"): (
        "Транзит Меркурия к натальному {natal_planet} — "
        "активизация коммуникации и мышления в сфере {natal_planet}. "
        "Хорошее время для разговоров, решений, обучения. Длится 1–2 дня."
    ),
}


def build_transit_event_prompt(
    transit_event: dict,
    natal_profile: dict,
    language: str = "ru",
) -> str:
    """Build prompt for single transit event interpretation.

    `transit_event` должен содержать поля, посчитанные
    `backend.transit.engine.compute_exact_facts()` — transit_sign/degree/house/
    retrograde, natal_sign/degree/house, exact_orb, exact_date, period_start/end,
    плюс идентификаторы transit_planet/natal_planet/aspect_type.
    """
    from backend.interpretation.prompts import _compact_profile

    compact_natal = _compact_profile(natal_profile)

    return TRANSIT_EVENT_PROMPT.format(
        facts_block=_build_facts_block(transit_event),
        natal_context=json.dumps(compact_natal, ensure_ascii=False, indent=2),
        language="русский" if language == "ru" else "English",
    )


def build_transit_period_prompt(
    transit_events: list[dict],
    natal_profile: dict,
    from_date: str,
    to_date: str,
    language: str = "ru",
) -> str:
    """Build prompt for period overview interpretation."""
    from backend.interpretation.prompts import _compact_profile

    compact_natal = _compact_profile(natal_profile)

    # Limit to top 20 most significant transits for prompt size
    sorted_events = sorted(transit_events, key=lambda e: e.get("orb", 99))[:20]

    return TRANSIT_PERIOD_PROMPT.format(
        transits_json=json.dumps(sorted_events, ensure_ascii=False, indent=2),
        natal_context=json.dumps(compact_natal, ensure_ascii=False, indent=2),
        from_date=from_date,
        to_date=to_date,
        language="русский" if language == "ru" else "English",
    )


def get_template_transit_text(
    transit_planet: str,
    natal_planet: str,
    aspect_type: str,
) -> str:
    """Get template-based transit interpretation (no AI fallback)."""
    key = (transit_planet, aspect_type)
    template = TRANSIT_TEMPLATES.get(key)

    if template:
        return template.format(natal_planet=natal_planet)

    # Generic fallback
    aspect_ru = {
        "conjunction": "соединении",
        "sextile": "секстиле",
        "square": "квадрате",
        "trine": "трине",
        "opposition": "оппозиции",
    }
    aspect_word = aspect_ru.get(aspect_type, aspect_type)

    return (
        f"Транзит {transit_planet} в {aspect_word} к натальному {natal_planet}. "
        f"Обратите внимание на темы, связанные с {natal_planet} в вашей карте."
    )
