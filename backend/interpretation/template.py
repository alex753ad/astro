"""Template-based interpretation engine.

Emergency fallback — no LLM needed, instant response.
Uses a knowledge base of pre-written interpretations keyed by
planet+sign, planet+house, and aspect combinations.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from backend.interpretation.base import (
    InterpretationEngine,
    InterpretationRequest,
    InterpretationResult,
)

logger = logging.getLogger("astro.template")

SIGN_RU = {
    "Aries": "Овне", "Taurus": "Тельце", "Gemini": "Близнецах",
    "Cancer": "Раке", "Leo": "Льве", "Virgo": "Деве",
    "Libra": "Весах", "Scorpio": "Скорпионе", "Sagittarius": "Стрельце",
    "Capricorn": "Козероге", "Aquarius": "Водолее", "Pisces": "Рыбах",
}
# ── Knowledge Base (subset — expand as needed) ──

SUN_IN_SIGN = {
    "Aries": "Солнце в Овне наделяет тебя яркой инициативностью и стремлением к лидерству. Первопроходец по натуре — ты предпочитаешь действие размышлениям. Твоя энергия заразительна, а смелость вдохновляет окружающих.",
    "Taurus": "Солнце в Тельце даёт тебе основательность и глубокую связь с материальным миром. Ты ценишь стабильность, красоту и комфорт. Твоя надёжность — качество, которое притягивает людей.",
    "Gemini": "Солнце в Близнецах наделяет тебя живым умом и потребностью в постоянном обмене информацией. В тебе много граней, живое любопытство и дар слова.",
    "Cancer": "Солнце в Раке даёт глубокую эмоциональную чувствительность и сильную связь с семьёй и домом. Твоя интуиция — один из твоих сильнейших инструментов.",
    "Leo": "Солнце во Льве — ты в своей стихии. Щедрость, творческая энергия и естественная харизма делают тебя центром притяжения. Ты стремишься к самовыражению.",
    "Virgo": "Солнце в Деве наделяет тебя аналитическим умом и стремлением к совершенству. Ты замечаешь детали, которые другие упускают, и обладаешь природным даром служения.",
    "Libra": "Солнце в Весах даёт тебе врождённое чувство гармонии и справедливости. Ты — прирождённый дипломат: умеешь видеть ситуацию с разных сторон.",
    "Scorpio": "Солнце в Скорпионе наделяет тебя глубиной и интенсивностью. Ты стремишься к трансформации и не боишься заглядывать в тени — как свои, так и чужие.",
    "Sagittarius": "Солнце в Стрельце даёт тебе оптимизм, жажду знаний и стремление к расширению горизонтов. Ты — искатель истины и смысла.",
    "Capricorn": "Солнце в Козероге наделяет тебя амбициозностью и дисциплиной. Ты строишь долгосрочные планы и обладаешь внутренней зрелостью не по годам.",
    "Aquarius": "Солнце в Водолее даёт тебе оригинальность мышления и стремление к прогрессу. Ты видишь будущее раньше других и не боишься отличаться от всех.",
    "Pisces": "Солнце в Рыбах наделяет тебя глубокой интуицией, состраданием и творческим воображением. Твоя способность чувствовать невидимое — твой дар.",
}

MOON_IN_SIGN = {
    "Aries": "Луна в Овне — твои эмоции яркие и мгновенные. Ты быстро загораешься и быстро отпускаешь. Тебе важна эмоциональная независимость.",
    "Taurus": "Луна в Тельце — одно из самых стабильных положений. Ты нуждаешься в предсказуемости, уюте и тактильном комфорте для эмоционального равновесия.",
    "Gemini": "Луна в Близнецах — ты обрабатываешь эмоции через слова и общение. Разговор — твой способ справиться с переживаниями.",
    "Cancer": "Луна в Раке — ты дома. Глубокая эмоциональная чувствительность, забота о близких и сильная интуиция — твои главные качества.",
    "Leo": "Луна во Льве — тебе важно чувствовать свою особенность и ценность. Ты щедро делишься чувствами и ждёшь такой же отдачи.",
    "Virgo": "Луна в Деве — ты заботишься через практические действия. Порядок и структура — твой способ справиться с тревогой.",
    "Libra": "Луна в Весах — гармония в отношениях критически важна для твоего эмоционального благополучия. Конфликты выбивают тебя из равновесия.",
    "Scorpio": "Луна в Скорпионе — твои эмоции глубоки и интенсивны. Ты чувствуешь всё на максимальной громкости, но редко показываешь это.",
    "Sagittarius": "Луна в Стрельце — тебе нужна свобода и пространство для эмоционального комфорта. Рутина тебя угнетает.",
    "Capricorn": "Луна в Козероге — чувства ты проявляешь сдержанно, но это не означает их отсутствие. На тебя можно положиться, как на скалу.",
    "Aquarius": "Луна в Водолее — ты обрабатываешь эмоции через интеллект. Иногда тебе трудно отличить то, что думаешь, от того, что чувствуешь.",
    "Pisces": "Луна в Рыбах — ты впитываешь эмоции окружающих как губка. Тебе важно научиться отделять свои чувства от чужих.",
}

ASPECT_TEXTS = {
    ("Sun", "Moon", "conjunction"): "Соединение Солнца и Луны (новолуние в карте) — твоё сознательное и бессознательное направлены в одну сторону. Сильная цельность, но может быть трудно увидеть себя со стороны.",
    ("Sun", "Moon", "opposition"): "Оппозиция Солнца и Луны (полнолуние в карте) — внутренний конфликт между тем, кем ты хочешь быть, и тем, что тебе нужно эмоционально. Это даёт объёмное видение жизни.",
    ("Venus", "Mars", "conjunction"): "Соединение Венеры и Марса — страсть и нежность сплетены воедино. Ты не разделяешь любовь и желание — для тебя это одно целое.",
    ("Sun", "Saturn", "square"): "Квадрат Солнца и Сатурна — ответственность и ограничения рано вошли в твою жизнь. Это трудный аспект, но он закаляет характер и даёт глубокую зрелость.",
    ("Moon", "Pluto", "conjunction"): "Соединение Луны и Плутона — твои эмоции обладают вулканической мощью. Ты проживаешь чувства на экстремальной глубине.",
    ("Jupiter", "Saturn", "conjunction"): "Соединение Юпитера и Сатурна — ты умеешь мечтать с планом в руках. Расширение и ограничение работают в тандеме.",
}


class TemplateEngine(InterpretationEngine):
    """Rule-based interpretation — no AI, instant, free."""

    name = "template"

    async def generate(self, request: InterpretationRequest) -> InterpretationResult:
        content = self._build_interpretation(request.natal_profile, request.sections)
        return InterpretationResult(
            content=content,
            sections=None,
            engine=self.name,
            tokens_used=0,
        )

    async def stream(self, request: InterpretationRequest) -> AsyncIterator[str]:
        """Simulate streaming by yielding lines with a small delay."""
        content = self._build_interpretation(request.natal_profile, request.sections)
        for line in content.split("\n"):
            yield line + "\n"
            await asyncio.sleep(0.01)

    async def health_check(self) -> bool:
        return True  # always available

    def _build_interpretation(self, profile: dict, sections: list[str]) -> str:
        parts: list[str] = []
        planets = {p["name"]: p for p in profile.get("planets", [])}
        aspects = profile.get("aspects", [])

        # General / personality
        if "general" in sections:
            parts.append("### Общий портрет личности\n")
            sun = planets.get("Sun", {})
            moon = planets.get("Moon", {})
            asc = profile.get("ascendant", {})

            if sun.get("sign") and sun["sign"] in SUN_IN_SIGN:
                parts.append(SUN_IN_SIGN[sun["sign"]])

            if moon.get("sign") and moon["sign"] in MOON_IN_SIGN:
                parts.append(MOON_IN_SIGN[moon["sign"]])

            if asc and asc.get("sign"):
                parts.append(
                    f"Твой Асцендент в {SIGN_RU.get(asc['sign'], asc['sign'])} — это маска, которую ты показываешь миру, "
                    f"первое впечатление, которое ты производишь."
                )

        # Aspects
        for a in aspects:
            key = (a["planet1"], a["planet2"], a["aspect_type"])
            key_rev = (a["planet2"], a["planet1"], a["aspect_type"])
            text = ASPECT_TEXTS.get(key) or ASPECT_TEXTS.get(key_rev)
            if text:
                parts.append(text)

        # Career
        if "career" in sections:
            mc = profile.get("midheaven", {})
            parts.append("\n### Карьера и профессиональная реализация\n")
            if mc and mc.get("sign"):
                parts.append(
                    f"Середина Неба (MC) в {SIGN_RU.get(mc['sign'], mc['sign'])} указывает на направление "
                    f"твоей профессиональной самореализации и публичный образ."
                )
            saturn = planets.get("Saturn", {})
            if saturn.get("sign"):
                parts.append(
                    f"Сатурн в {SIGN_RU.get(saturn['sign'], saturn['sign'])} показывает, где тебе предстоит "
                    f"наиболее серьёзная работа над собой в профессиональном плане."
                )

        # Relationships
        if "relationships" in sections:
            parts.append("\n### Отношения и партнёрство\n")
            venus = planets.get("Venus", {})
            mars = planets.get("Mars", {})
            if venus.get("sign"):
                parts.append(
                    f"Венера в {SIGN_RU.get(venus['sign'], venus['sign'])} описывает твой стиль любви — "
                    f"то, как ты выражаешь нежность и что ценишь в партнёре."
                )
            if mars.get("sign"):
                parts.append(
                    f"Марс в {SIGN_RU.get(mars['sign'], mars['sign'])} — твоя страсть и инициатива в отношениях."
                )

        # Health
        if "health" in sections:
            parts.append("\n### Здоровье и энергия\n")
            parts.append(
                "Обрати внимание на баланс стихий в твоей карте — "
                "преобладание одной стихии может указывать на зоны, требующие внимания."
            )

        # Finance
        if "finance" in sections:
            parts.append("\n### Финансы и материальные ресурсы\n")
            jupiter = planets.get("Jupiter", {})
            if jupiter.get("sign"):
                parts.append(
                    f"Юпитер в {SIGN_RU.get(jupiter['sign'], jupiter['sign'])} — твоя зона роста и потенциального изобилия."
                )

        # Spirituality
        if "spirituality" in sections:
            parts.append("\n### Духовное развитие\n")
            neptune = planets.get("Neptune", {})
            if neptune.get("sign"):
                parts.append(
                    f"Нептун в {SIGN_RU.get(neptune['sign'], neptune['sign'])} (поколенческая планета) создаёт "
                    f"фон для твоего духовного поиска."
                )
            node = planets.get("North Node", {})
            if node and node.get("sign"):
                parts.append(
                    f"Северный узел в {SIGN_RU.get(node['sign'], node['sign'])} — направление твоего духовного роста "
                    f"в этой жизни, то, к чему стоит стремиться."
                )

        if not parts:
            parts.append("Интерпретация временно недоступна. Попробуй чуть позже.")

        return "\n\n".join(parts)
