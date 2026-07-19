"""System prompt construction for AI interpretation.

Builds a detailed system prompt with:
1. Astrological knowledge base context
2. Style and tone instructions
3. Output format specification
"""

from __future__ import annotations

import json
from backend.interpretation.base import InterpretationRequest

SYSTEM_PROMPT_TEMPLATE = """Тебя зовут Астрея. Ты — навигатор решений, а не предсказатель: разбираешь карту простым живым языком и показываешь, на что опереться.
Тебе дан астрологический профиль человека в формате JSON.

## Твоя задача
Написать персонализированную интерпретацию натальной карты по следующим сферам жизни:
{sections_list}

## Правила интерпретации
1. НЕ предсказывай конкретные события. Описывай тенденции, потенциалы и энергии.
2. Связывай несколько планетарных конфигураций в единый нарратив — не перечисляй отдельные аспекты изолированно.
3. Учитывай взаимодействие между планетами, домами и аспектами.
4. Если планета ретроградна — отметь это и объясни влияние.
5. Уделяй особое внимание стеллиумам (3+ планеты в одном знаке/доме).

## Объём интерпретации
{word_count_instruction}

## Тон и стиль
- Ты — Астрея: спокойная, собранная, тёплая через пользу, а не через утешение
- Пиши как живой человек, а не как гороскоп: просто, конкретно, без пафоса
- Без раздувания значимости, клише вроде «твой путь — раскрыть потенциал», нанизанных оборотов и обязательных троек
- Без страшилок и фатальных формулировок; напряжённое — зона роста, а не приговор
- Не выделяй жирным каждый термин; чередуй короткие и длинные фразы
- Каждая секция: {paragraphs_per_section} абзацев содержательного текста

## Формат ответа
Структурируй интерпретацию по секциям. Перед каждой секцией выводи открывающий XML-тег, после — закрывающий:
<section name="general">
...текст секции...
</section>
<section name="career">
...текст секции...
</section>

Допустимые имена секций: general, career, relationships, health, finance, spirituality.

{time_warning}

## Астрологический профиль
```json
{profile_json}
```

Напиши интерпретацию на языке: {language}."""


SECTION_NAMES = {
    "general": "Общий портрет личности",
    "career": "Карьера и профессиональная реализация",
    "relationships": "Отношения и партнёрство",
    "health": "Здоровье и энергия",
    "finance": "Финансы и материальные ресурсы",
    "spirituality": "Духовное развитие и внутренний рост",
}

SECTION_NAMES_EN = {
    "general": "Personality Overview",
    "career": "Career & Professional Path",
    "relationships": "Relationships & Partnership",
    "health": "Health & Vitality",
    "finance": "Finances & Resources",
    "spirituality": "Spiritual Growth",
}


def build_system_prompt(request: InterpretationRequest) -> str:
    """Build the full system prompt for the AI model."""
    lang_sections = SECTION_NAMES if request.language == "ru" else SECTION_NAMES_EN

    sections_list = "\n".join(
        f"- **{lang_sections.get(s, s)}**" for s in request.sections
    )

    time_warning = ""
    if request.natal_profile.get("time_unknown"):
        time_warning = (
            "⚠️ ВАЖНО: Время рождения неизвестно. Дома и Асцендент рассчитаны приблизительно "
            "(полдень). НЕ интерпретируй дома и Асцендент как точные данные — "
            "сосредоточься на знаках и аспектах планет."
        )

    # Compact profile for prompt (remove excessive precision)
    compact = _compact_profile(request.natal_profile)

    # Объём зависит от word_limit или тира
    word_limit = getattr(request, "word_limit", None)
    tier = getattr(request, "tier", "free")
    if word_limit and isinstance(word_limit, int) and 1000 <= word_limit <= 5000:
        word_count_instruction = (
            f"Напиши интерпретацию объёмом около {word_limit} слов суммарно по всем секциям. "
            f"Распредели слова равномерно между секциями. "
            f"ОБЯЗАТЕЛЬНО: каждая секция и весь текст должны заканчиваться полным предложением — "
            f"никогда не обрывай текст на полуслове или в середине мысли."
        )
        paragraphs_per_section = str(max(2, word_limit // 500))
    elif tier == "premium":
        word_count_instruction = "Напиши ПОДРОБНУЮ интерпретацию объёмом НЕ МЕНЕЕ 5000 слов суммарно по всем секциям. Каждая секция должна быть развёрнутой и глубокой."
        paragraphs_per_section = "8–12"
    elif tier == "pro":
        word_count_instruction = "Напиши интерпретацию объёмом около 2500 слов суммарно."
        paragraphs_per_section = "5–7"
    else:
        word_count_instruction = "Напиши краткую интерпретацию объёмом около 800 слов суммарно."
        paragraphs_per_section = "2–3"

    return SYSTEM_PROMPT_TEMPLATE.format(
        sections_list=sections_list,
        profile_json=json.dumps(compact, ensure_ascii=False, indent=2),
        language="русский" if request.language == "ru" else "English",
        time_warning=time_warning,
        word_count_instruction=word_count_instruction,
        paragraphs_per_section=paragraphs_per_section,
    )


def _compact_profile(profile: dict) -> dict:
    """Remove unnecessary precision from profile for shorter prompt."""
    result = {}

    if "planets" in profile:
        result["planets"] = []
        for p in profile["planets"]:
            entry = {
                "name": p["name"],
                "sign": p["sign"],
                "degree": round(p.get("degree_in_sign", 0), 1),
            }
            if p.get("house"):
                entry["house"] = p["house"]
            if p.get("retrograde"):
                entry["retrograde"] = True
            result["planets"].append(entry)

    if "aspects" in profile:
        result["aspects"] = []
        for a in profile["aspects"]:
            result["aspects"].append({
                "planets": f"{a['planet1']} {a['aspect_type']} {a['planet2']}",
                "orb": round(a["orb"], 1),
                "applying": a.get("applying", False),
            })

    if "ascendant" in profile and profile["ascendant"]:
        result["ascendant"] = {
            "sign": profile["ascendant"]["sign"],
            "degree": round(profile["ascendant"]["degree"], 1),
        }

    if "midheaven" in profile and profile["midheaven"]:
        result["midheaven"] = {
            "sign": profile["midheaven"]["sign"],
            "degree": round(profile["midheaven"]["degree"], 1),
        }

    if "houses" in profile:
        result["houses"] = [
            {"number": h["number"], "sign": h["sign"]}
            for h in profile["houses"]
        ]

    result["time_unknown"] = profile.get("time_unknown", False)
    return result
