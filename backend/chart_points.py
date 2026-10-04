"""Натальные точки карты — ОДНО место для всех разделов (шаг 3 аудита,
docs/audit_unified_model.md; решение владельца 02.10.2026).

Карта без времени рождения (`time_unknown`) хранит дома, ASC и MC,
посчитанные на полдень, и натальную Луну с ошибкой до ±6°. Этих данных у
человека НЕТ, и ни один раздел не должен на них опираться: без натальной Луны,
ASC, MC и домов. До 04.10.2026 каждый раздел решал это сам, и пуши планера,
«Новая сфера», PDF «Долгосрочные», карточка на вебе брали полуденные дома и
ASC, а лента, чат и «Важный транзит» — натальную Луну.

Набор точек раздела (с узлами ли, с углами ли) пока свой — его сведёт шаг 5;
здесь только СОСТАВ карты: кто из раздела берёт точки, берёт их отсюда.
"""
from __future__ import annotations

ANGLES = ("Ascendant", "Midheaven")
UNKNOWN_TIME_HIDDEN = frozenset({"Moon", *ANGLES})


def _get(chart, key):
    return chart.get(key) if isinstance(chart, dict) else getattr(chart, key, None)


def time_unknown(chart) -> bool:
    return bool(_get(chart, "time_unknown"))


def targets(chart, angles: bool = True) -> list[dict]:
    """Натальные точки: планеты карты (с узлами) и, если `angles`, ASC и MC —
    из `chart.ascendant/midheaven`, не куспиды (#107). Без времени рождения —
    без Луны, ASC, MC, и у планет `house=None`."""
    unknown = time_unknown(chart)
    out = []
    for p in _get(chart, "planets") or []:
        if not p.get("name") or p.get("longitude") is None:
            continue
        if unknown and p["name"] == "Moon":
            continue
        out.append({**p, "house": None} if unknown else p)
    if angles and not unknown:
        for name, key in zip(ANGLES, ("ascendant", "midheaven")):
            point = _get(chart, key) or {}
            if point.get("longitude") is not None:
                out.append({"name": name, "longitude": point["longitude"], "sign": point.get("sign", "")})
    return out


def planets(chart) -> list[dict]:
    """Планеты карты (с узлами) без углов — то, что раньше бралось как
    `chart.planets` напрямую."""
    return targets(chart, angles=False)


def cusps(chart) -> list[float] | None:
    """Куспиды домов; None — домов нет (без времени рождения или пустые)."""
    if time_unknown(chart):
        return None
    from backend.transit.house_passages import _extract_cusps
    c = _extract_cusps({"houses": _get(chart, "houses")})
    return None if all(x == 0.0 for x in c) else c
