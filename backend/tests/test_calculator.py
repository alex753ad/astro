"""tests/test_calculator.py — unit tests for ephemeris/calculator.py.

Покрывает критические функции: конвертации, расчёт домов, назначение домов,
обработку крайних широт, и полный расчёт карты.

Запуск: pytest backend/tests/test_calculator.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from backend.ephemeris.calculator import (
    _datetime_to_jd,
    _longitude_to_sign,
    _find_house,
    assign_houses,
    calculate_planets,
    calculate_houses,
    calculate_full_chart,
    ZODIAC_SIGNS,
    PlanetResult,
    HouseResult,
)


# ═══════════════════════════════════════════════════════════
# _longitude_to_sign
# ═══════════════════════════════════════════════════════════

class TestLongitudeToSign:
    def test_aries_start(self):
        sign, deg = _longitude_to_sign(0.0)
        assert sign == "Aries"
        assert deg == pytest.approx(0.0)

    def test_aries_end(self):
        sign, deg = _longitude_to_sign(29.9999)
        assert sign == "Aries"

    def test_taurus_start(self):
        sign, _ = _longitude_to_sign(30.0)
        assert sign == "Taurus"

    def test_pisces_end(self):
        sign, deg = _longitude_to_sign(359.9999)
        assert sign == "Pisces"
        assert deg == pytest.approx(29.9999, abs=0.001)

    def test_all_signs_covered(self):
        signs_found = set()
        for i in range(12):
            sign, _ = _longitude_to_sign(i * 30.0)
            signs_found.add(sign)
        assert signs_found == set(ZODIAC_SIGNS)

    def test_degree_in_sign_range(self):
        for lon in [0, 15.5, 45.3, 180.0, 270.7, 359.9]:
            _, deg = _longitude_to_sign(lon)
            assert 0.0 <= deg < 30.0, f"degree {deg} out of range for lon={lon}"

    def test_rounding(self):
        sign, deg = _longitude_to_sign(45.12345)
        assert deg == pytest.approx(15.1235, abs=0.0001)


# ═══════════════════════════════════════════════════════════
# _find_house
# ═══════════════════════════════════════════════════════════

class TestFindHouse:
    # Standard cusps starting near 0°
    CUSPS_STANDARD = [0.0, 30.0, 60.0, 90.0, 120.0, 150.0,
                      180.0, 210.0, 240.0, 270.0, 300.0, 330.0]

    def test_planet_in_first_house(self):
        assert _find_house(10.0, self.CUSPS_STANDARD) == 1

    def test_planet_at_cusp_boundary(self):
        # Exactly on cusp 2 → house 2
        assert _find_house(30.0, self.CUSPS_STANDARD) == 2

    def test_planet_in_seventh_house(self):
        assert _find_house(185.0, self.CUSPS_STANDARD) == 7

    def test_planet_in_last_house(self):
        assert _find_house(340.0, self.CUSPS_STANDARD) == 12

    def test_wraps_360(self):
        # 359° should be house 12
        assert _find_house(359.9, self.CUSPS_STANDARD) == 12

    def test_cusps_with_asc_not_at_zero(self):
        # ASC at 90° — real-world scenario
        cusps = [90.0, 120.0, 150.0, 180.0, 210.0, 240.0,
                 270.0, 300.0, 330.0, 0.0, 30.0, 60.0]
        # Planet at 100° is in house 1 (just past ASC at 90°)
        assert _find_house(100.0, cusps) == 1
        # Planet at 270° is in house 7
        assert _find_house(270.0, cusps) == 7


# ═══════════════════════════════════════════════════════════
# assign_houses
# ═══════════════════════════════════════════════════════════

class TestAssignHouses:
    def _make_planet(self, name: str, lon: float) -> PlanetResult:
        sign, deg = _longitude_to_sign(lon)
        return PlanetResult(
            name=name, longitude=lon, latitude=0.0, distance=1.0,
            speed=1.0, sign=sign, degree_in_sign=deg, retrograde=False,
        )

    def _make_houses(self) -> list[HouseResult]:
        return [
            HouseResult(number=i + 1, sign=ZODIAC_SIGNS[i], degree=float(i * 30))
            for i in range(12)
        ]

    def test_planets_get_house_assigned(self):
        planets = [
            self._make_planet("Sun", 15.0),   # house 1
            self._make_planet("Moon", 45.0),  # house 2
            self._make_planet("Mars", 180.0), # house 7
        ]
        houses = self._make_houses()
        result = assign_houses(planets, houses)
        assert result[0].house == 1
        assert result[1].house == 2
        assert result[2].house == 7

    def test_all_planets_have_house(self):
        planets = [self._make_planet(f"P{i}", float(i * 25)) for i in range(12)]
        houses = self._make_houses()
        result = assign_houses(planets, houses)
        for p in result:
            assert hasattr(p, "house")
            assert 1 <= p.house <= 12


# ═══════════════════════════════════════════════════════════
# _datetime_to_jd
# ═══════════════════════════════════════════════════════════

class TestDatetimeToJD:
    def test_j2000_epoch(self):
        # J2000.0 = 2000-01-01 12:00 UTC → JD 2451545.0
        dt = datetime(2000, 1, 1, 12, 0, 0)
        jd = _datetime_to_jd(dt)
        assert jd == pytest.approx(2451545.0, abs=0.001)

    def test_unix_epoch(self):
        # 1970-01-01 00:00 UTC → JD 2440587.5
        dt = datetime(1970, 1, 1, 0, 0, 0)
        jd = _datetime_to_jd(dt)
        assert jd == pytest.approx(2440587.5, abs=0.001)

    def test_minutes_fractional(self):
        dt1 = datetime(2000, 1, 1, 12, 0, 0)
        dt2 = datetime(2000, 1, 1, 12, 30, 0)
        diff = _datetime_to_jd(dt2) - _datetime_to_jd(dt1)
        assert diff == pytest.approx(30 / (24 * 60), abs=1e-6)


# ═══════════════════════════════════════════════════════════
# calculate_planets (integration — requires ephemeris files)
# ═══════════════════════════════════════════════════════════

@pytest.mark.integration
class TestCalculatePlanets:
    """Requires actual Swiss Ephemeris data files in EPHE_PATH."""

    KNOWN_DT = datetime(2000, 1, 1, 12, 0, 0)  # J2000.0

    def test_returns_all_planets(self):
        planets = calculate_planets(self.KNOWN_DT)
        names = {p.name for p in planets}
        expected = {"Sun", "Moon", "Mercury", "Venus", "Mars",
                    "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "North Node"}
        assert expected == names

    def test_sun_longitude_range(self):
        planets = calculate_planets(self.KNOWN_DT)
        sun = next(p for p in planets if p.name == "Sun")
        assert 0.0 <= sun.longitude < 360.0

    def test_sun_in_capricorn_at_j2000(self):
        # Sun is in Capricorn on Jan 1, 2000
        planets = calculate_planets(self.KNOWN_DT)
        sun = next(p for p in planets if p.name == "Sun")
        assert sun.sign == "Capricorn"

    def test_retrograde_flag_is_bool(self):
        planets = calculate_planets(self.KNOWN_DT)
        for p in planets:
            assert isinstance(p.retrograde, bool)

    def test_degree_in_sign_in_range(self):
        planets = calculate_planets(self.KNOWN_DT)
        for p in planets:
            assert 0.0 <= p.degree_in_sign < 30.0, f"{p.name}: {p.degree_in_sign}"


# ═══════════════════════════════════════════════════════════
# calculate_houses (integration)
# ═══════════════════════════════════════════════════════════

@pytest.mark.integration
class TestCalculateHouses:
    DT = datetime(2000, 1, 1, 12, 0, 0)
    LAT, LON = 55.75, 37.62  # Moscow

    def test_returns_12_houses(self):
        houses, asc, mc, warnings = calculate_houses(self.DT, self.LAT, self.LON)
        assert len(houses) == 12

    def test_house_numbers_sequential(self):
        houses, *_ = calculate_houses(self.DT, self.LAT, self.LON)
        assert [h.number for h in houses] == list(range(1, 13))

    def test_asc_longitude_in_range(self):
        _, asc, _, _ = calculate_houses(self.DT, self.LAT, self.LON)
        assert 0.0 <= asc.longitude < 360.0

    def test_mc_longitude_in_range(self):
        _, _, mc, _ = calculate_houses(self.DT, self.LAT, self.LON)
        assert 0.0 <= mc.longitude < 360.0

    def test_polar_latitude_warning(self):
        # Lat 70° should trigger Placidus warning
        _, _, _, warnings = calculate_houses(self.DT, 70.0, 25.0, system="placidus")
        assert any("polar" in w.lower() or "placidus" in w.lower() for w in warnings)

    def test_fallback_to_equal_at_extreme_latitude(self):
        # Should not raise even at 89°N
        try:
            houses, asc, mc, warnings = calculate_houses(self.DT, 89.0, 0.0)
            assert len(houses) == 12
        except Exception as e:
            pytest.fail(f"calculate_houses raised at extreme latitude: {e}")


# ═══════════════════════════════════════════════════════════
# calculate_full_chart (integration)
# ═══════════════════════════════════════════════════════════

@pytest.mark.integration
class TestCalculateFullChart:
    DT = datetime(1990, 6, 15, 10, 30, 0)
    LAT, LON = 48.85, 2.35  # Paris

    def test_returns_tuple(self):
        result = calculate_full_chart(self.DT, self.LAT, self.LON)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_chart_has_planets_and_houses(self):
        chart, aspects = calculate_full_chart(self.DT, self.LAT, self.LON)
        assert len(chart.planets) == 11
        assert len(chart.houses) == 12

    def test_aspects_is_list(self):
        _, aspects = calculate_full_chart(self.DT, self.LAT, self.LON)
        assert isinstance(aspects, list)

    def test_time_unknown_adds_warning(self):
        chart, _ = calculate_full_chart(self.DT, self.LAT, self.LON, time_unknown=True)
        assert any("unknown" in w.lower() or "noon" in w.lower() for w in chart.warnings)

    def test_all_planets_have_house_assigned(self):
        chart, _ = calculate_full_chart(self.DT, self.LAT, self.LON)
        for p in chart.planets:
            assert hasattr(p, "house"), f"{p.name} missing house"
            assert 1 <= p.house <= 12
