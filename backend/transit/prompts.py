"""Prompts for transit AI interpretation.

Builds system prompts for:
1. Single transit event interpretation (click on timeline event)
2. Period overview (summary of all transits for a date range)
"""

from __future__ import annotations

import json


TRANSIT_EVENT_PROMPT = """Ты — опытный профессиональный астролог.
Тебе предоставлен конкретный транзитный аспект.

## Твоя задача
Написать краткую, но содержательную интерпретацию этого транзита (3–5 абзацев).

## Правила
1. Описывай тенденции и энергии, а НЕ конкретные события.
2. Учитывай контекст натальной карты (знаки, дома).
3. Укажи примерный период действия транзита.
4. Если аспект напряжённый (квадрат, оппозиция) — опиши как зону роста, не как угрозу.
5. Дай практический совет, как использовать энергию транзита.

## Тон
Поддерживающий, не фатальный, конкретный.

## Транзит
```json
{transit_json}
```

## Натальная карта (контекст)
```json
{natal_context}
```

Напиши интерпретацию на языке: {language}."""


TRANSIT_PERIOD_PROMPT = """Ты — опытный профессиональный астролог.
Тебе предоставлен список транзитов за период.

## Твоя задача
Написать обзорную интерпретацию транзитного периода (5–8 абзацев).

## Правила
1. Выдели 3–5 ключевых тем периода (не перечисляй все транзиты по отдельности).
2. Сгруппируй транзиты по темам: карьера, отношения, личностный рост, здоровье.
3. Укажи наиболее значимые даты и почему они важны.
4. Начни с общего тона периода, закончи практическими рекомендациями.
5. Если несколько транзитов усиливают друг друга — отметь это.

## Тон
Поддерживающий, структурированный, практичный.

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
    """Build prompt for single transit event interpretation."""
    from backend.interpretation.prompts import _compact_profile

    compact_natal = _compact_profile(natal_profile)

    return TRANSIT_EVENT_PROMPT.format(
        transit_json=json.dumps(transit_event, ensure_ascii=False, indent=2),
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
