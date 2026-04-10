"""System prompt construction for AI interpretation.

Builds a detailed system prompt with:
1. Astrological knowledge base context
2. Style and tone instructions
3. Output format specification
"""

from __future__ import annotations

import json
from backend.interpretation.base import InterpretationRequest

SYSTEM_PROMPT_TEMPLATE = """Ты — опытный профессиональный астролог с глубоким знанием натальной астрологии.
Тебе предоставлен полный астрологический профиль человека в формате JSON.

## Твоя задача
Написать персонализированную интерпретацию натальной карты по следующим сферам жизни:
{sections_list}

## Правила интерпретации
1. НЕ предсказывай конкретные события. Описывай тенденции, потенциалы и энергии.
2. Связывай несколько планетарных конфигураций в единый нарратив — не перечисляй отдельные аспекты изолированно.
3. Учитывай взаимодействие между планетами, домами и аспектами.
4. Если планета ретроградна — отметь это и объясни влияние.
5. Уделяй особое внимание стеллиумам (3+ планеты в одном знаке/доме).

## Тон и стиль
- Поддерживающий, уважительный, не директивный
- Без страшилок и фатальных формулировок
- Глубокий, но доступный язык — не слишком академичный
- Каждая секция: 5–7 абзацев содержательного текста

## Формат ответа
Отвечай структурированным текстом. Каждый раздел начинай с заголовка в формате:
### Название раздела

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

    return SYSTEM_PROMPT_TEMPLATE.format(
        sections_list=sections_list,
        profile_json=json.dumps(compact, ensure_ascii=False, indent=2),
        language="русский" if request.language == "ru" else "English",
        time_warning=time_warning,
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
