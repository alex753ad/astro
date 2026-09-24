"""System prompt construction for AI interpretation.

Builds a detailed system prompt with:
1. Astrological knowledge base context
2. Style and tone instructions
3. Output format specification
"""

from __future__ import annotations

import json
from backend.interpretation.base import InterpretationRequest
# Склонение числительных в этом рантайме живёт в одном месте — там же,
# где числа в письмах (CLAUDE.md, раздел про склонение). Второй копии
# правила «1 абзац / 3 абзаца / 12 абзацев» не заводим.
from backend.email_service import _plural
from backend.interpretation.address import ADDRESS_RULE

# Версия промпта натального разбора — часть ключей кэша `interp:` и
# `stream:` (`interpretation/router.py`). Кэш живёт 30 дней: без версии правка
# промпта доезжала бы до человека только по истечении TTL. Поднимать при
# любой правке, которая должна заменить уже закэшированные тексты.
# 2 — переход на «ты», 24.09.2026. Сохранённые в БД разборы не трогаются
# (решение владельца) — они останутся в той форме, в какой были написаны.
INTERPRETATION_PROMPT_VERSION = 2


def resolve_word_limit(request: InterpretationRequest) -> int:
    """Единственный источник целевого объёма слов — для промпта (сколько слов
    просить у модели) и для max_tokens (backend/interpretation/gpt4o.py). Явный
    request.word_limit (если задан и в допустимом диапазоне — брифы/кастомные
    запросы) имеет приоритет, иначе — TIER_FLAGS[tier].interpretation_word_limit.
    """
    word_limit = getattr(request, "word_limit", None)
    if word_limit and isinstance(word_limit, int) and 1000 <= word_limit <= 5000:
        return word_limit
    from backend.auth.rate_limits import TIER_FLAGS
    tier = getattr(request, "tier", "free")
    return TIER_FLAGS.get(tier, TIER_FLAGS["free"])["interpretation_word_limit"]


# Сколько слов в живом абзаце этого стиля. Не выдумано и не оценено — замерено
# прогоном всех четырёх тарифов на одной карте 09.09.2026 (deepseek-v4-pro,
# новый промпт):
#   free     6 абзацев → 69.5 слова
#   lite    12 абзацев → 74.7
#   pro     35 абзацев → 81.2
#   premium 70 абзацев → 69.1
# Среднее по итоговому прогону — 73.6, то есть 70 попадает в разброс. Все
# четыре тарифа при этом сошлись в цель (free 417, lite 896, pro 2842,
# premium 4834 слова, finish_reason=stop, шесть секций закрыты).
#
# ⚠️ Первая версия этой константы была 60 — из одного замера (1067 слов в 18
# абзацах). Замер был верный, но нерепрезентативный: тот разбор шёл по старому
# промпту с тремя абзацами на секцию. Четыре точки дали настоящее значение.
#
# Число нужно ровно для одного — перевести целевой объём в число абзацев;
# отдельной тарифной ручкой оно не является и в TIER_FLAGS ему не место.
_WORDS_PER_PARAGRAPH = 70

# Модель систематически перевыполняет объём на КОРОТКИХ секциях: ниже примерно
# сотни слов она добирает связность и пишет на два десятка слов больше, чем
# просили. Замер 09.09.2026, одна карта, deepseek-v4-pro, слов на секцию:
#   просили  33 →  54   (+21)
#   просили  50 →  70   (+20)
#   просили  75 →  92   (+17)
#   просили 133 → 124   (−9)
#   просили 417 → 487   (+70)
#   просили 833 → 618   (−215)
# Первые три точки — устойчивое смещение около +20. С 133 оно исчезает: там
# модель идёт за планом. Поэтому поправка применяется ТОЛЬКО в нижней зоне,
# где она измерена, а не ко всем тарифам подряд.
#
# ⚠️ Это поправка на поведение МОДЕЛИ, а не второй тарифный лимит. Источник
# объёма остаётся один — interpretation_word_limit; здесь только пересчёт
# «сколько попросить, чтобы получить столько, сколько заявлено». Три прогона
# free подряд без неё дали 596, 549 и 562 слова при заявленных 450.
_SHORT_SECTION_WORDS = 100
_SHORT_SECTION_OVERSHOOT = 20


def _volume_plan(request: InterpretationRequest, word_limit: int) -> tuple[int, int, int]:
    """Целевой объём → (секций, слов на секцию, абзацев, слов в абзаце).

    ⚠️ Смысл этой функции — в том, что число абзацев ВЫВОДИТСЯ, а не задаётся
    рядом с числом слов вторым независимым числом. Так было до 09.09.2026, и
    два числа противоречили друг другу: free просили «около 500 слов» и тут же
    «2–3 абзаца» на каждую из шести секций, то есть 12–18 абзацев — минимум
    вдвое больше, чем влезает в 500 слов. Модель слушала абзацы, а не слова:
    замер на боевом free-аккаунте дал 1067 слов при заявленных 500.

    Это тот же класс дефекта, что `charts_per_month` рядом с `profiles_limit`
    и `pdf_per_month` на витрине: два числа, обязанных совпадать, рано или
    поздно расходятся. Лечение то же — оставить одно и вывести из него второе.

    Число секций берётся из самого запроса, а не из константы: `sections`
    объявлены полем `InterpretationRequest`, и вызывающая сторона вправе
    попросить не все шесть (CRM так и делает). Захардкоженная шестёрка тогда
    молча перекосила бы объём.
    """
    section_count = max(1, len(getattr(request, "sections", None) or []))
    target_per_section = max(1, round(word_limit / section_count))

    # Просим меньше, чем хотим получить, ровно в той зоне, где измерен
    # систематический перебор (см. _SHORT_SECTION_OVERSHOOT выше).
    if target_per_section < _SHORT_SECTION_WORDS:
        words_per_section = max(25, target_per_section - _SHORT_SECTION_OVERSHOOT)
    else:
        words_per_section = target_per_section

    paragraphs = max(1, round(words_per_section / _WORDS_PER_PARAGRAPH))
    words_per_paragraph = max(1, round(words_per_section / paragraphs))
    return section_count, words_per_section, paragraphs, words_per_paragraph


SYSTEM_PROMPT_TEMPLATE = """Тебя зовут Аристея. Ты — навигатор решений, а не предсказатель: разбираешь карту простым живым языком и показываешь, на что опереться.
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

## ПРАВИЛА РАБОТЫ С ФАКТАМИ
- Все знаки, градусы, дома и аспекты уже посчитаны точно и даны в профиле ниже —
  не вычисляй их сам и не исправляй.
- Используй только планеты, дома и аспекты из профиля. Если чего-то там нет —
  не упоминай это вообще.
- Не называй дат — натальная карта не привязана к текущему моменту.

## Объём интерпретации
{word_count_instruction}

## Тон и стиль
- """ + ADDRESS_RULE + """
- Ты — Аристея: спокойная, собранная, тёплая через пользу, а не через утешение
- Пиши как живой человек, а не как гороскоп: просто, конкретно, без пафоса
- Без раздувания значимости, клише вроде «твой путь — раскрыть потенциал», нанизанных оборотов и обязательных троек
- Без страшилок и фатальных формулировок; напряжённое — зона роста, а не приговор
- Не выделяй жирным каждый термин; чередуй короткие и длинные фразы
- Каждая секция: {paragraphs_per_section} {paragraph_word} по ~{words_per_paragraph} слов, всего примерно {words_per_section} слов

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

    # Объём — из resolve_word_limit(): один источник и для промпта, и для
    # max_tokens в gpt4o.py/deepseek.py (раньше free целился в 800 слов
    # здесь, при лимите 500 в TIER_FLAGS — два независимых числа расходились).
    word_limit = resolve_word_limit(request)
    section_count, words_per_section, paragraphs, words_per_paragraph = _volume_plan(
        request, word_limit,
    )

    # "Не обрывай предложение" — раньше было только в word_limit-ветке,
    # в тарифных ветках (в т.ч. free) отсутствовало вовсе.
    no_cutoff = (
        " ОБЯЗАТЕЛЬНО: каждая секция и весь текст должны заканчиваться полным "
        "предложением — никогда не обрывай текст на полуслове или в середине мысли."
    )

    # Одна инструкция на все тарифы. Раньше их было четыре, и в каждой рядом с
    # числом слов стояло НЕЗАВИСИМОЕ число абзацев («2–3» у free при 500 словах
    # на шесть секций). Модель слушала абзацы: замер настоящего разбора с
    # боевого free-аккаунта 09.09.2026 дал 1067 слов вместо 500 — ровно по три
    # абзаца в каждой из шести секций. Теперь абзацы ВЫВОДЯТСЯ из слов
    # (_volume_plan), поэтому разойтись им не с чем.
    # ⚠️ Общий объём в инструкции — это words_per_section × секции, а НЕ
    # word_limit: в нижней зоне мы просим меньше заявленного (см. _volume_plan),
    # и назвать здесь заявленное число значило бы снова дать модели два
    # расходящихся ориентира — ровно то, от чего эта правка избавлялась.
    asked_total = words_per_section * section_count
    word_count_instruction = (
        f"Общий объём — около {asked_total} слов, это примерно {words_per_section} "
        f"слов на каждую из {section_count} секций. Не превышай этот объём: "
        f"лучше короче и плотнее, чем длиннее и водянистее." + no_cutoff
    )
    paragraphs_per_section = str(paragraphs)

    return SYSTEM_PROMPT_TEMPLATE.format(
        sections_list=sections_list,
        profile_json=json.dumps(compact, ensure_ascii=False, indent=2),
        language="русский" if request.language == "ru" else "English",
        time_warning=time_warning,
        word_count_instruction=word_count_instruction,
        paragraphs_per_section=paragraphs_per_section,
        paragraph_word=_plural(paragraphs, "абзац", "абзаца", "абзацев"),
        words_per_section=words_per_section,
        words_per_paragraph=words_per_paragraph,
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
