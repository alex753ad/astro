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


# ── Knowledge Base (subset — expand as needed) ──

SUN_IN_SIGN = {
    "Aries": "Солнце в Овне наделяет вас яркой инициативностью и стремлением к лидерству. Вы — первопроходец по натуре, предпочитающий действие размышлениям. Ваша энергия заразительна, а смелость вдохновляет окружающих.",
    "Taurus": "Солнце в Тельце даёт вам основательность и глубокую связь с материальным миром. Вы цените стабильность, красоту и комфорт. Ваша надёжность — качество, которое притягивает людей.",
    "Gemini": "Солнце в Близнецах наделяет вас живым умом и потребностью в постоянном обмене информацией. Вы многогранны, любопытны и обладаете даром слова.",
    "Cancer": "Солнце в Раке даёт глубокую эмоциональную чувствительность и сильную связь с семьёй и домом. Ваша интуиция — один из ваших сильнейших инструментов.",
    "Leo": "Солнце во Льве — вы в своей стихии. Щедрость, творческая энергия и естественная харизма делают вас центром притяжения. Вы стремитесь к самовыражению.",
    "Virgo": "Солнце в Деве наделяет вас аналитическим умом и стремлением к совершенству. Вы замечаете детали, которые другие упускают, и обладаете природным даром служения.",
    "Libra": "Солнце в Весах даёт вам врождённое чувство гармонии и справедливости. Вы — дипломат, способный видеть ситуацию с разных сторон.",
    "Scorpio": "Солнце в Скорпионе наделяет вас глубиной и интенсивностью. Вы стремитесь к трансформации и не боитесь заглядывать в тени — как свои, так и чужие.",
    "Sagittarius": "Солнце в Стрельце даёт вам оптимизм, жажду знаний и стремление к расширению горизонтов. Вы — искатель истины и смысла.",
    "Capricorn": "Солнце в Козероге наделяет вас амбициозностью и дисциплиной. Вы строите долгосрочные планы и обладаете внутренней зрелостью не по годам.",
    "Aquarius": "Солнце в Водолее даёт вам оригинальность мышления и стремление к прогрессу. Вы видите будущее раньше других и не боитесь быть не таким, как все.",
    "Pisces": "Солнце в Рыбах наделяет вас глубокой интуицией, состраданием и творческим воображением. Ваша способность чувствовать невидимое — ваш дар.",
}

MOON_IN_SIGN = {
    "Aries": "Луна в Овне — ваши эмоции яркие и мгновенные. Вы быстро загораетесь и быстро отпускаете. Вам важна эмоциональная независимость.",
    "Taurus": "Луна в Тельце — одно из самых стабильных положений. Вы нуждаетесь в предсказуемости, уюте и тактильном комфорте для эмоционального равновесия.",
    "Gemini": "Луна в Близнецах — вы обрабатываете эмоции через слова и общение. Разговор — ваш способ справиться с переживаниями.",
    "Cancer": "Луна в Раке — вы дома. Глубокая эмоциональная чувствительность, забота о близких и сильная интуиция — ваши главные качества.",
    "Leo": "Луна во Льве — вам нужно чувствовать себя особенным и ценным. Вы эмоционально щедры и ждёте такой же отдачи.",
    "Virgo": "Луна в Деве — вы заботитесь через практические действия. Порядок и структура — ваш способ справиться с тревогой.",
    "Libra": "Луна в Весах — гармония в отношениях критически важна для вашего эмоционального благополучия. Конфликты выбивают вас из равновесия.",
    "Scorpio": "Луна в Скорпионе — ваши эмоции глубоки и интенсивны. Вы чувствуете всё на максимальной громкости, но редко показываете это.",
    "Sagittarius": "Луна в Стрельце — вам нужна свобода и пространство для эмоционального комфорта. Рутина вас угнетает.",
    "Capricorn": "Луна в Козероге — вы сдержанны в проявлении чувств, но это не означает их отсутствие. Вы надёжны как скала.",
    "Aquarius": "Луна в Водолее — вы обрабатываете эмоции через интеллект. Иногда вам трудно отличить то, что вы думаете, от того, что чувствуете.",
    "Pisces": "Луна в Рыбах — вы впитываете эмоции окружающих как губка. Вам важно научиться отделять свои чувства от чужих.",
}

ASPECT_TEXTS = {
    ("Sun", "Moon", "conjunction"): "Соединение Солнца и Луны (новолуние в карте) — ваше сознательное и бессознательное направлены в одну сторону. Сильная цельность, но может быть трудно увидеть себя со стороны.",
    ("Sun", "Moon", "opposition"): "Оппозиция Солнца и Луны (полнолуние в карте) — внутренний конфликт между тем, кем вы хотите быть, и тем, что вам нужно эмоционально. Это даёт объёмное видение жизни.",
    ("Venus", "Mars", "conjunction"): "Соединение Венеры и Марса — страсть и нежность сплетены воедино. Вы не разделяете любовь и желание — для вас это одно целое.",
    ("Sun", "Saturn", "square"): "Квадрат Солнца и Сатурна — вы рано узнали, что такое ответственность и ограничения. Это трудный аспект, но он закаляет характер и даёт глубокую зрелость.",
    ("Moon", "Pluto", "conjunction"): "Соединение Луны и Плутона — ваши эмоции обладают вулканической мощью. Вы проживаете чувства на экстремальной глубине.",
    ("Jupiter", "Saturn", "conjunction"): "Соединение Юпитера и Сатурна — вы умеете мечтать с планом в руках. Расширение и ограничение работают в тандеме.",
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
                    f"Ваш Асцендент в {asc['sign']} — это маска, которую вы показываете миру, "
                    f"первое впечатление, которое вы производите."
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
                    f"Середина Неба (MC) в {mc['sign']} указывает на направление "
                    f"вашей профессиональной самореализации и публичный образ."
                )
            saturn = planets.get("Saturn", {})
            if saturn.get("sign"):
                parts.append(
                    f"Сатурн в {saturn['sign']} показывает, где вам предстоит "
                    f"наиболее серьёзная работа над собой в профессиональном плане."
                )

        # Relationships
        if "relationships" in sections:
            parts.append("\n### Отношения и партнёрство\n")
            venus = planets.get("Venus", {})
            mars = planets.get("Mars", {})
            if venus.get("sign"):
                parts.append(
                    f"Венера в {venus['sign']} описывает ваш стиль любви — "
                    f"то, как вы выражаете нежность и что цените в партнёре."
                )
            if mars.get("sign"):
                parts.append(
                    f"Марс в {mars['sign']} — ваша страсть и инициатива в отношениях."
                )

        # Health
        if "health" in sections:
            parts.append("\n### Здоровье и энергия\n")
            parts.append(
                "Обратите внимание на баланс стихий в вашей карте — "
                "преобладание одной стихии может указывать на зоны, требующие внимания."
            )

        # Finance
        if "finance" in sections:
            parts.append("\n### Финансы и материальные ресурсы\n")
            jupiter = planets.get("Jupiter", {})
            if jupiter.get("sign"):
                parts.append(
                    f"Юпитер в {jupiter['sign']} — ваша зона роста и потенциального изобилия."
                )

        # Spirituality
        if "spirituality" in sections:
            parts.append("\n### Духовное развитие\n")
            neptune = planets.get("Neptune", {})
            if neptune.get("sign"):
                parts.append(
                    f"Нептун в {neptune['sign']} (поколенческая планета) создаёт "
                    f"фон для вашего духовного поиска."
                )
            node = planets.get("North Node", {})
            if node and node.get("sign"):
                parts.append(
                    f"Северный узел в {node['sign']} — направление вашего духовного роста "
                    f"в этой жизни, то, к чему стоит стремиться."
                )

        if not parts:
            parts.append("Интерпретация временно недоступна. Пожалуйста, попробуйте позже.")

        return "\n\n".join(parts)
