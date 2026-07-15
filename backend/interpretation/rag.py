"""RAG (Retrieval-Augmented Generation) для чата по натальной карте.

Подход: keyword-search по knowledge_base.json (191 запись).
Без внешних зависимостей — FAISS/sentence-transformers не нужны
при таком объёме базы знаний.

Экспортирует:
    retrieve(question, chart_context) -> list[str]   — релевантные фрагменты
    build_chart_summary(chart)         -> str         — компактный текст карты
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("astro.rag")

# ── загрузка базы знаний ──────────────────────────────────────────────────────

_KB_PATH = Path(__file__).parent / "knowledge_base.json"

def _load_kb() -> list[dict]:
    """Разворачивает иерархический JSON в плоский список {key, text}."""
    try:
        with open(_KB_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.error("Failed to load knowledge_base.json: %s", e)
        return []

    entries: list[dict] = []
    for section, value in raw.items():
        if section == "_meta" or not isinstance(value, dict):
            continue
        for key, text in value.items():
            entries.append({
                "key":     key,
                "section": section,
                "text":    text,
                "tokens":  _tokenize(f"{key} {text}"),
            })
    return entries


def _tokenize(text: str) -> set[str]:
    """Простая токенизация: строчные слова 3+ символов."""
    return set(re.findall(r"[а-яёa-z]{3,}", text.lower()))


_KB: list[dict] | None = None

def _get_kb() -> list[dict]:
    global _KB
    if _KB is None:
        _KB = _load_kb()
    return _KB


# ── keyword retrieval ─────────────────────────────────────────────────────────

# Словарь переводов для матчинга русских терминов с ключами базы
_RU_TO_KEY: dict[str, str] = {
    "солнце": "Sun", "луна": "Moon", "меркурий": "Mercury",
    "венера": "Venus", "марс": "Mars", "юпитер": "Jupiter",
    "сатурн": "Saturn", "уран": "Uranus", "нептун": "Neptune",
    "плутон": "Pluto", "асцендент": "ASC", "асц": "ASC",
    "овен": "Aries", "телец": "Taurus", "близнецы": "Gemini",
    "рак": "Cancer", "лев": "Leo", "дева": "Virgo",
    "весы": "Libra", "скорпион": "Scorpio", "стрелец": "Sagittarius",
    "козерог": "Capricorn", "водолей": "Aquarius", "рыбы": "Pisces",
    "карьера": "career", "деньги": "finance", "финансы": "finance",
    "отношения": "relationships", "любовь": "relationships",
    "здоровье": "health", "работа": "career", "дети": "5",
    "семья": "4", "дом": "house",
    "соединение": "conjunction", "оппозиция": "opposition",
    "трин": "trine", "квадрат": "square", "секстиль": "sextile",
    "ретроградный": "retrograde", "ретро": "retrograde",
}


def retrieve(question: str, chart_context: dict, top_k: int = 6) -> list[str]:
    """Возвращает top_k релевантных фрагментов из базы знаний.

    Args:
        question:      вопрос пользователя
        chart_context: dict с planets, ascendant, houses карты
        top_k:         сколько фрагментов вернуть
    """
    kb = _get_kb()
    if not kb:
        return []

    # Строим набор поисковых токенов из вопроса + маппинга
    q_lower = question.lower()
    q_tokens = _tokenize(q_lower)

    # Добавляем английские эквиваленты русских терминов
    extra: set[str] = set()
    for ru, en in _RU_TO_KEY.items():
        if ru in q_lower:
            extra.update(_tokenize(en))
    q_tokens |= extra

    # Добавляем термины из карты пользователя (планеты, знаки)
    chart_tokens = _chart_tokens(chart_context)
    # Взвешиваем: совпадение с вопросом важнее, чем просто контекст карты

    scored: list[tuple[float, str]] = []
    for entry in kb:
        key_tokens = _tokenize(entry["key"])
        text_tokens = entry["tokens"]

        # Совпадение с вопросом (вес 2) + совпадение с картой (вес 1)
        q_match    = len(q_tokens & (key_tokens | text_tokens))
        chart_match = len(chart_tokens & key_tokens)
        score = q_match * 2 + chart_match

        if score > 0:
            scored.append((score, entry["text"]))

    scored.sort(reverse=True)
    return [text for _, text in scored[:top_k]]


def _chart_tokens(chart: dict) -> set[str]:
    """Извлекает токены из данных карты для контекстуализации поиска."""
    tokens: set[str] = set()
    for p in chart.get("planets") or []:
        tokens.update(_tokenize(str(p.get("name", ""))))
        tokens.update(_tokenize(str(p.get("sign", ""))))
        h = p.get("house")
        if h:
            tokens.add(str(h))
    asc = chart.get("ascendant") or {}
    if asc.get("sign"):
        tokens.update(_tokenize(asc["sign"]))
    return tokens


# ── chart summary для system prompt ──────────────────────────────────────────

_SIGN_RU = {
    "Aries": "Овен", "Taurus": "Телец", "Gemini": "Близнецы",
    "Cancer": "Рак", "Leo": "Лев", "Virgo": "Дева",
    "Libra": "Весы", "Scorpio": "Скорпион", "Sagittarius": "Стрелец",
    "Capricorn": "Козерог", "Aquarius": "Водолей", "Pisces": "Рыбы",
}
_PLANET_RU = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий",
    "Venus": "Венера", "Mars": "Марс", "Jupiter": "Юпитер",
    "Saturn": "Сатурн", "Uranus": "Уран", "Neptune": "Нептун",
    "Pluto": "Плутон",
}
_ASP_RU = {
    "conjunction": "соединение", "sextile": "секстиль",
    "square": "квадрат", "trine": "трин", "opposition": "оппозиция",
}
# Традиционные управители знаков (по одному управителю на знак)
_SIGN_RULER = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury",
    "Cancer": "Moon", "Leo": "Sun", "Virgo": "Mercury",
    "Libra": "Venus", "Scorpio": "Mars", "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}


def build_chart_summary(chart: dict) -> str:
    """Компактный текстовый дамп карты для system prompt (≈400 токенов)."""
    lines: list[str] = ["## Натальная карта пользователя\n"]

    # Планеты
    planets = chart.get("planets") or []
    if planets:
        lines.append("**Планеты:**")
        for p in planets:
            name = _PLANET_RU.get(p.get("name", ""), p.get("name", ""))
            sign = _SIGN_RU.get(p.get("sign", ""), p.get("sign", ""))
            house = p.get("house", "")
            deg   = p.get("degree", "")
            retro = " ℞" if p.get("retrograde") else ""
            lines.append(f"  {name}: {sign} {deg}°{retro}, {house} дом")

    # Асцендент
    asc = chart.get("ascendant") or {}
    if asc.get("sign"):
        sign = _SIGN_RU.get(asc["sign"], asc["sign"])
        lines.append(f"\n**Асцендент:** {sign} {asc.get('degree', '')}°")

    mc = chart.get("midheaven") or {}
    if mc.get("sign"):
        sign = _SIGN_RU.get(mc["sign"], mc["sign"])
        lines.append(f"**MC (Середина Неба):** {sign} {mc.get('degree', '')}°")

    # Управители домов (по знаку на куспиде) — считаем явно, не даём ИИ угадывать
    houses = chart.get("houses") or []
    if houses:
        lines.append("\n**Управители домов** (по знаку на куспиде, традиционные):")
        for h in sorted(houses, key=lambda x: x.get("number", 0)):
            num = h.get("number", "")
            sign_en = h.get("sign", "")
            sign_ru = _SIGN_RU.get(sign_en, sign_en)
            ruler_en = _SIGN_RULER.get(sign_en, "")
            ruler_ru = _PLANET_RU.get(ruler_en, ruler_en)
            if num and ruler_ru:
                lines.append(f"  {num} дом — куспид в {sign_ru} → управитель {ruler_ru}")

    # Ключевые аспекты (топ-8 по орбу)
    aspects = chart.get("aspects") or []
    if aspects:
        sorted_asp = sorted(aspects, key=lambda a: abs(a.get("orb", 9)))
        lines.append("\n**Ключевые аспекты:**")
        for a in sorted_asp[:8]:
            p1  = _PLANET_RU.get(a.get("planet1", ""), a.get("planet1", ""))
            p2  = _PLANET_RU.get(a.get("planet2", ""), a.get("planet2", ""))
            asp_key = a.get("aspect_type") or a.get("aspect", "")
            asp = _ASP_RU.get(asp_key, asp_key)
            orb = a.get("orb", "")
            lines.append(f"  {p1} {asp} {p2} (орб {orb}°)")

    return "\n".join(lines)
