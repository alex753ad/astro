"""Письмо клиентам астролога: аспект по-русски, дата словами в поясе карты
клиента (06.10.2026; до этого — «square» и ISO-дата по UTC)."""
from backend.email_service import broadcast_when, build_client_broadcast


def test_date_in_client_timezone_words():
    # 29.10 19:12 UTC — во Владивостоке уже 30 октября.
    assert broadcast_when("2026-10-29T19:12", "2026-10-29", "Asia/Vladivostok") == "30 октября"
    assert broadcast_when("2026-10-29T19:12", "2026-10-29", "Europe/Moscow") == "29 октября"
    assert broadcast_when(None, "2026-10-12", "Europe/Moscow") == "12 октября"


def test_template_row_is_russian():
    t = {"transit_planet": "Saturn", "natal_planet": "Sun", "aspect_type": "square",
         "peak_date": "2026-10-12", "when": "12 октября"}
    _, html = build_client_broadcast("Бренд", "октябрь 2026", [t])
    assert "<b>Сатурн</b> квадрат <b>Солнце</b>" in html and "12 октября" in html
    assert "square" not in html and "2026-10-12" not in html
