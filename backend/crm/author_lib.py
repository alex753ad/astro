"""Author interpretations matching (roadmap idea 13).

По карте выводит ключи-кандидаты (напр. saturn_house_7, sun_taurus, asc_leo),
находит совпадающие авторские трактовки астролога и собирает контекст-блок,
который дописывается к промпту разбора (голосом астролога).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models import AstrologerInterpretation


def candidate_keys(planets, ascendant) -> set[str]:
    keys: set[str] = set()
    for p in (planets or []):
        name = (p.get("name") or "").lower()
        sign = (p.get("sign") or "").lower()
        house = p.get("house")
        if name and sign:
            keys.add(f"{name}_{sign}")
        if name and house:
            keys.add(f"{name}_house_{house}")
    asc_sign = (ascendant or {}).get("sign")
    if asc_sign:
        keys.add(f"asc_{str(asc_sign).lower()}")
    return keys


def match_author_blocks(db: Session, astrologer_id: int, planets, ascendant) -> list[tuple[str, str]]:
    keys = candidate_keys(planets, ascendant)
    if not keys:
        return []
    rows = (
        db.query(AstrologerInterpretation)
        .filter(
            AstrologerInterpretation.astrologer_id == astrologer_id,
            AstrologerInterpretation.key.in_(keys),
        )
        .all()
    )
    return [(r.key, r.content) for r in rows]


def format_author_context(blocks: list[tuple[str, str]]) -> str:
    if not blocks:
        return ""
    body = "\n\n".join(f"[{k}] {c}" for k, c in blocks)
    return (
        "АВТОРСКИЕ ТРАКТОВКИ АСТРОЛОГА. Ниже — собственные формулировки астролога по элементам "
        "этой карты. Используй их как основу: сохраняй их смысл, тон и акценты, органично вплетая "
        "в разбор, не противореча им.\n" + body
    )


def author_context_for_chart(db: Session, astrologer_id: int, planets, ascendant) -> str:
    return format_author_context(match_author_blocks(db, astrologer_id, planets, ascendant))
