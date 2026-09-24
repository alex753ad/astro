"""Пояс места рождения: история поясов, час перевода стрелок, ручное смещение.

Эталон в таблице — не наш же код, а история поясов по открытым источникам
(Википедия, «Самарское время», «Калининградское время», «Московское время»),
сверено 24.09.2026. Пять случаев выбраны там, где у конкурентов ломалось:
декретное/летнее время СССР, постоянное «летнее» 2011–2014, смена пояса
региона в 2010 году.
"""

import pytest
from timezonefinder import TimezoneFinder

from backend.ephemeris.geo import (
    AmbiguousTimeError,
    applied_utc_offset_minutes,
    resolve_utc_datetime,
)

_tf = TimezoneFinder()

# (место, широта, долгота, дата, ожидаемое смещение в минутах, почему)
CASES = [
    ("Москва", 55.7558, 37.6173, "1985-07-15", 240, "летнее декретное МСК, UTC+4"),
    ("Москва", 55.7558, 37.6173, "2012-01-15", 240, "постоянное «летнее» 2011–2014"),
    ("Самара", 53.1959, 50.1002, "2010-01-15", 240, "самарское время до 28.03.2010"),
    ("Самара", 53.1959, 50.1002, "2010-07-15", 240, "московское летнее после 28.03.2010"),
    ("Самара", 53.1959, 50.1002, "2011-01-15", 180, "московское зимнее"),
    ("Самара", 53.1959, 50.1002, "2011-07-15", 240, "постоянное с 27.03.2011"),
    ("Калининград", 54.7104, 20.4522, "1990-01-15", 120, "МСК−1 зимнее"),
    ("Калининград", 54.7104, 20.4522, "1990-07-15", 180, "МСК−1 летнее"),
    ("Нью-Йорк", 40.7128, -74.0060, "2020-07-15", -240, "EDT"),
]


@pytest.mark.parametrize("place,lat,lon,day,expected,why", CASES)
def test_history_of_zones(place, lat, lon, day, expected, why):
    tz = _tf.timezone_at(lat=lat, lng=lon)
    utc, _, _ = resolve_utc_datetime(day, "12:00", tz)
    assert applied_utc_offset_minutes(day, "12:00", utc) == expected, (place, day, why)


def test_ambiguous_hour_offers_offsets_that_resolve_it():
    """Выбор из ошибки обязан проходить обратно — раньше кнопки слали подпись
    «02:30 MSD», поле времени её отбивало, и карту построить было нельзя."""
    with pytest.raises(AmbiguousTimeError) as exc:
        resolve_utc_datetime("2010-10-31", "02:30", "Europe/Moscow")
    assert exc.value.offsets == [240, 180]
    moments = {
        resolve_utc_datetime("2010-10-31", "02:30", "Europe/Moscow", utc_offset_minutes=o)[0]
        for o in exc.value.offsets
    }
    assert len(moments) == 2  # два разных момента, по часу разницы


def test_manual_offset_wins_over_place():
    utc, _, _ = resolve_utc_datetime("2012-01-15", "12:00", "Europe/Moscow", utc_offset_minutes=180)
    assert applied_utc_offset_minutes("2012-01-15", "12:00", utc) == 180


def test_unknown_time_offset_is_taken_at_noon():
    utc, unknown, _ = resolve_utc_datetime("1985-07-15", None, "Europe/Moscow")
    assert unknown and applied_utc_offset_minutes("1985-07-15", None, utc) == 240


class TestApi:
    def test_ambiguous_then_pick_builds_chart(self, client, mock_geo):
        body = {"birth_date": "2010-10-31", "birth_time": "02:30", "birth_place": "Moscow"}
        r = client.post("/api/v1/chart/calculate", json=body)
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert detail["type"] == "ambiguous_time" and detail["offsets"] == [240, 180]

        r = client.post("/api/v1/chart/calculate", json={**body, "utc_offset_minutes": 180})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["utc_offset_minutes"] == 180
        assert data["utc_offset_source"] == "manual"

    def test_place_offset_is_reported(self, client, mock_geo):
        body = {"birth_date": "1985-07-15", "birth_time": "12:00", "birth_place": "Moscow"}
        r = client.post("/api/v1/chart/calculate", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["utc_offset_minutes"] == 240 and data["utc_offset_source"] == "place"

        r = client.get(f"/api/v1/chart/{data['id']}",
                       headers={"X-Chart-Token": data["access_token"]})
        assert r.status_code == 200, r.text
        assert r.json()["utc_offset_minutes"] == 240
        assert r.json()["utc_offset_source"] == "place"

    def test_offset_out_of_range_is_rejected(self, client, mock_geo):
        body = {"birth_date": "1985-07-15", "birth_time": "12:00", "birth_place": "Moscow",
                "utc_offset_minutes": 900}
        assert client.post("/api/v1/chart/calculate", json=body).status_code == 422
