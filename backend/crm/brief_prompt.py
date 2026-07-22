"""Brief prompt builder (roadmap idea 2 — «Подготовить встречу»).

Собирает единый custom_prompt для брифа к консультации:
натальные акценты + активные транзиты + прошлая консультация + вопросы.
Возвращает строку, которая уходит в InterpretationRequest(custom_prompt=...).
"""
from __future__ import annotations

from typing import Optional


def _fmt_planets(planets: Optional[list[dict]]) -> str:
    parts = []
    for p in planets or []:
        name, sign = p.get("name"), p.get("sign")
        if not name or not sign:
            continue
        seg = f"{name} в {sign}"
        if p.get("house"):
            seg += f", дом {p['house']}"
        parts.append(seg)
    return "; ".join(parts) if parts else "нет данных"


def _fmt_transits(transits: Optional[list[dict]]) -> str:
    if not transits:
        return "значимых транзитов в ближайший месяц не найдено"
    lines = []
    for t in transits:
        when = t.get("exact_date") or t.get("date") or ""
        seg = (
            f"{t.get('transit_planet', '?')} {t.get('aspect_type', '?')} "
            f"натальный {t.get('natal_planet', '?')}"
        )
        orb = t.get("orb")
        if when:
            seg += f" (точно ~{when}"
            seg += f", орб {orb}°)" if orb is not None else ")"
        lines.append("- " + seg)
    return "\n".join(lines)


def build_brief_prompt(
    *,
    client_name: str,
    birth_info: str,
    natal_profile: dict,
    transits: Optional[list[dict]] = None,
    last_consultation: Optional[dict] = None,
    author_context: str = "",
) -> str:
    planets_line = _fmt_planets(natal_profile.get("planets"))
    asc = (natal_profile.get("ascendant") or {}).get("sign")

    prev = "Предыдущих консультаций нет."
    if last_consultation:
        when = str(last_consultation.get("date") or "")[:10]
        topic = last_consultation.get("topic") or "—"
        notes = (last_consultation.get("notes") or "").strip() or "заметок нет"
        prev = f"Дата: {when}. Тема: {topic}. Итоги: {notes}"

    return (
        "Ты — ассистент практикующего астролога. Подготовь краткий бриф к консультации "
        f"с клиентом по имени {client_name}. Пиши по-русски, структурировано, по делу, без воды.\n"
        "ПРАВИЛА РАБОТЫ С ФАКТАМИ: планеты, дома и транзиты ниже уже посчитаны точно — "
        "не вычисляй их сам. Используй только то, что есть в данных ниже; если чего-то там "
        "нет — не упоминай. Не называй дат, которых нет в данных.\n\n"
        f"ДАННЫЕ РОЖДЕНИЯ: {birth_info}\n"
        f"АСЦЕНДЕНТ: {asc or 'неизвестен'}\n"
        f"ПЛАНЕТЫ: {planets_line}\n\n"
        f"АКТИВНЫЕ ТРАНЗИТЫ (ближайший месяц):\n{_fmt_transits(transits)}\n\n"
        f"ПРОШЛАЯ КОНСУЛЬТАЦИЯ:\n{prev}\n\n"
        + (author_context + "\n\n" if author_context else "")
        + "Сформируй бриф из четырёх разделов:\n"
        "1. Ключевые темы натальной карты (2–4 пункта).\n"
        "2. Что происходит сейчас — разбор активных транзитов простым языком.\n"
        "3. Связь с прошлой консультацией (если была) — к чему вернуться.\n"
        "4. Вопросы, которые стоит поднять на встрече (3–5 штук).\n"
    )
