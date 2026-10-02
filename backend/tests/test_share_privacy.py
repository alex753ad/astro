"""Публичная ссылка на карту: дата, место и колесо — только по выбору человека.

Решение владельца 27.09.2026. До этого `/share/{token}/data` и карточка
отдавали дату и место рождения всем, у кого есть ссылка. Колесо скрывается
вместе с датой: по градусам планет момент рождения восстанавливается
однозначно.
"""

from datetime import date, timedelta

from backend.share_router import (
    CARD_CACHE_CONTROL, ru_date, short_place, wrap_to_width,
)
from backend.tests.test_chart_access import _make_chart
from backend.time_utils import utcnow


def _shared(db, show_birth):
    chart = _make_chart(db)
    chart.public_token = "privacy-token"
    chart.public_token_expires_at = utcnow() + timedelta(days=1)
    chart.share_show_birth = show_birth
    db.commit()
    db.refresh(chart)
    return chart


def test_default_hides_birth_and_wheel(client, db):
    chart = _shared(db, False)
    data = client.get(f"/api/v1/share/{chart.public_token}/data").json()

    assert data["show_birth"] is False
    for key in ("birth_date", "birth_place", "houses", "aspects", "midheaven", "time_unknown"):
        assert key not in data, key
    # От планет — только знак, без градусов.
    assert data["planets"] and all(set(p) == {"name", "sign"} for p in data["planets"])
    assert data["ascendant"] is None or set(data["ascendant"]) == {"sign"}


def test_opt_in_returns_birth_and_wheel(client, db):
    chart = _shared(db, True)
    data = client.get(f"/api/v1/share/{chart.public_token}/data").json()

    assert data["show_birth"] is True
    assert data["birth_date"] == chart.birth_date
    assert data["birth_place"] == chart.birth_place
    assert data["houses"] == chart.houses


def test_post_sets_flag_each_call_default_hidden(client, db, user_free, auth_headers_free):
    chart = _make_chart(db, user_id=user_free.id)
    url = f"/api/v1/charts/{chart.id}/share"

    assert client.post(url + "?show_birth=true", headers=auth_headers_free).json()["show_birth"] is True
    # Повторная отправка без переключателя закрывает дату и по старой ссылке.
    assert client.post(url, headers=auth_headers_free).json()["show_birth"] is False
    db.refresh(chart)
    assert chart.share_show_birth is False


def test_card_is_not_cached():
    assert "max-age" not in CARD_CACHE_CONTROL
    assert CARD_CACHE_CONTROL == "no-store"


def test_ru_date():
    assert ru_date("1990-03-15") == "15 марта 1990"
    assert ru_date(date(2026, 9, 26)) == "26 сентября 2026"
    assert ru_date("кривое") == "кривое"


def test_short_place():
    nominatim = ("Таганрог, городской округ Таганрог, Ростовская область, "
                 "Южный федеральный округ, Россия")
    assert short_place(nominatim) == "Таганрог, Ростовская обл."
    assert short_place("Краснодар, Краснодарский край, Россия") == "Краснодар, Краснодарский край"
    assert short_place("Paris, Île-de-France, France métropolitaine, France") == "Paris, France"
    assert short_place("Москва") == "Москва"
    assert short_place(None) == ""


def test_wrap_to_width_two_lines_with_ellipsis():
    measure = len  # 1 символ = 1 px
    assert wrap_to_width("короткое", measure, 20) == ["короткое"]
    lines = wrap_to_width("aaaa bbbb cccc dddd eeee", measure, 9)
    assert len(lines) == 2
    assert all(measure(line) <= 9 for line in lines)
    assert lines[-1].endswith("…")
