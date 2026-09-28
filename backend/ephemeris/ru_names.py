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

# Знаки — именительный и предложный («Солнце в Тельце»). До 28.09.2026 словарь
# знаков жил копиями в email_service, share_router, rag, crm/dashboard_router;
# PDF печатал знаки по-английски. Новым потребителям — брать отсюда.
SIGN_RU: dict[str, str] = {
    "Aries": "Овен", "Taurus": "Телец", "Gemini": "Близнецы", "Cancer": "Рак",
    "Leo": "Лев", "Virgo": "Дева", "Libra": "Весы", "Scorpio": "Скорпион",
    "Sagittarius": "Стрелец", "Capricorn": "Козерог", "Aquarius": "Водолей",
    "Pisces": "Рыбы",
}

SIGN_IN_RU: dict[str, str] = {
    "Aries": "в Овне", "Taurus": "в Тельце", "Gemini": "в Близнецах",
    "Cancer": "в Раке", "Leo": "во Льве", "Virgo": "в Деве", "Libra": "в Весах",
    "Scorpio": "в Скорпионе", "Sagittarius": "в Стрельце",
    "Capricorn": "в Козероге", "Aquarius": "в Водолее", "Pisces": "в Рыбах",
}

# Значения — как `house_system` в BirthDataInput (schemas.py).
HOUSE_SYSTEM_RU: dict[str, str] = {
    "placidus": "Плацидус", "koch": "Кох",
    "whole_sign": "целые знаки", "equal": "равные дома",
}
