"""Summary prompt builder (roadmap idea 7 — «AI-портрет клиента»).

Собирает custom_prompt для короткой справки по клиенту:
кто человек + ключевые темы карты + о чём говорили + что в работе.
Смотрит назад (в отличие от брифа, который смотрит вперёд по транзитам).
"""
from __future__ import annotations

from typing import Optional

from backend.crm.brief_prompt import _fmt_planets


def build_summary_prompt(
    *,
    client_name: str,
    birth_info: str,
    natal_profile: dict,
    notes: str = "",
    consultations: Optional[list[dict]] = None,
    author_context: str = "",
) -> str:
    planets_line = _fmt_planets(natal_profile.get("planets"))
    asc = (natal_profile.get("ascendant") or {}).get("sign")

    notes_block = (notes or "").strip() or "нет общих заметок"

    if consultations:
        lines = []
        for c in consultations:
            when = str(c.get("date") or "")[:10]
            topic = c.get("topic") or "—"
            status = c.get("status") or ""
            cnote = (c.get("notes") or "").strip()
            seg = f"- {when} · {topic}" + (f" [{status}]" if status else "")
            if cnote:
                seg += f": {cnote}"
            lines.append(seg)
        cons_block = "\n".join(lines)
    else:
        cons_block = "консультаций ещё не было"

    return (
        "Ты — ассистент практикующего астролога. Составь короткую справку-портрет клиента, "
        "чтобы астролог за пару минут восстановил контекст перед созвоном. "
        f"Клиент: {client_name}. Пиши по-русски, сжато и по делу, без воды.\n"
        "ПРАВИЛА РАБОТЫ С ФАКТАМИ: планеты и дома ниже уже посчитаны точно — не вычисляй "
        "их сам. Используй только то, что есть в данных ниже; если чего-то там нет — "
        "не упоминай. Не называй дат, которых нет в истории консультаций.\n\n"
        f"ДАННЫЕ РОЖДЕНИЯ: {birth_info}\n"
        f"АСЦЕНДЕНТ: {asc or 'неизвестен'}\n"
        f"ПЛАНЕТЫ: {planets_line}\n\n"
        f"ОБЩИЕ ЗАМЕТКИ:\n{notes_block}\n\n"
        f"ИСТОРИЯ КОНСУЛЬТАЦИЙ:\n{cons_block}\n\n"
        + (author_context + "\n\n" if author_context else "")
        + "Сформируй справку из четырёх коротких разделов:\n"
        "1. Кто человек — 1–2 предложения по сути личности (из карты и заметок).\n"
        "2. Ключевые темы натальной карты (2–3 пункта).\n"
        "3. О чём уже говорили — краткое резюме прошлых консультаций.\n"
        "4. Что в работе / на что обратить внимание на следующей встрече.\n"
    )
