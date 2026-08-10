"""Русские названия планет/точек и аспектов — единый источник.

Раньше PLANET_RU/NATAL_RU/ASP_RU были продублированы (и каждый раз неполно)
в email_service.py, transit/engine.py, push/cron.py, pilot/cron.py, tasks.py,
interpretation/rag.py — из-за этого узлы (North Node/South Node) и местами
Плутон оставались непереведёнными в письмах и пушах.
"""

PLANET_RU: dict[str, str] = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
    "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн", "Uranus": "Уран",
    "Neptune": "Нептун", "Pluto": "Плутон",
    "North Node": "Сев. Узел", "South Node": "Юж. Узел",
    "Ascendant": "Асцендент", "Midheaven": "MC",
    "Descendant": "Десцендент", "IC": "IC",
}

ASPECT_RU: dict[str, str] = {
    "conjunction": "соединение", "sextile": "секстиль",
    "square": "квадрат", "trine": "трин", "opposition": "оппозиция",
}
