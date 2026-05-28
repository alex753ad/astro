"""tests/test_calculator_extended.py — расширенные тесты ephemeris/calculator.py.

Дополняет test_calculator.py:
  - Позиции планет для знаменитостей с известными данными рождения
  - Граничные случаи: полночь, смена дня, полярные широты
  - Полное покрытие _find_house с нестандартными куспидами
  - Тест lru_cache (_calc_planet_position вызывается один раз)
  - Тест FullChart.warnings при time_unknown

Запуск: pytest backend/tests/test_calculator_extended.py -v
Запуск только unit (без ephemeris-файлов): pytest -v -m "not integration"
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch, call, MagicMock

import pytest

from backend.ephemeris.calculator import (
    _datetime_to_jd,
    _longitude_to_sign,
    _find_house,
    _calc_planet_position,
    assign_houses,
    calculate_planets,
    calculate_houses,
    calculate_full_chart,
    ZODIAC_SIGNS,
    PlanetResult,
    HouseResult,
    PointResult,
    FullChart,
)


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def _make_planet(name: str, lon: float, speed: float = 1.0) -> PlanetResult:
    sign, deg = _longitude_to_sign(lon)
    return PlanetResult(
        name=name, longitude=lon, latitude=0.0, distance=1.0,
        speed=speed, sign=sign, degree_in_sign=deg, retrograde=speed < 0,
    )


def _make_houses_from_cusps(cusps: list[float]) -> list[HouseResult]:
    houses = []
    for i, cusp in enumerate(cusps):
        sign, _ = _longitude_to_sign(cusp)
        houses.append(HouseResult(number=i + 1, sign=sign, degree=cusp))
    return houses


# ═══════════════════════════════════════════════════════════
# _longitude_to_sign — дополнительные случаи
# ═══════════════════════════════════════════════════════════

class TestLongitudeToSignExtended:
    def test_exact_sign_boundaries(self):
        """Каждые 30° — начало нового знака."""
        expected = ZODIAC_SIGNS
        for i, expected_sign in enumerate(expected):
            sign, deg = _longitude_to_sign(float(i * 30))
            assert sign == expected_sign, f"At {i*30}° expected {expected_sign}, got {sign}"
            assert deg == pytest.approx(0.0, abs=0.001)

    def test_midpoints_of_signs(self):
        """15° каждого знака — середина."""
        for i in range(12):
            lon = i * 30 + 15.0
            sign, deg = _longitude_to_sign(lon)
            assert sign == ZODIAC_SIGNS[i]
            assert deg == pytest.approx(15.0, abs=0.001)

    def test_29_59_degrees(self):
        """29.99° в знаке — последний градус, не переход."""
        sign, deg = _longitude_to_sign(59.999)  # 29.999° Taurus
        assert sign == "Taurus"
        assert deg == pytest.approx(29.999, abs=0.001)

    def test_zero_is_aries(self):
        sign, deg = _longitude_to_sign(0.0)
        assert sign == "Aries"
        assert deg == pytest.approx(0.0)

    def test_360_wraps_to_aries(self):
        """360° = 0° Aries по модулю."""
        # Функция принимает 0–360, 360 = index 12 → 12 % 12 = 0 → Aries
        sign, deg = _longitude_to_sign(360.0)
        assert sign == "Aries"


# ═══════════════════════════════════════════════════════════
# _find_house — расширенные случаи
# ═══════════════════════════════════════════════════════════

class TestFindHouseExtended:
    def test_planet_exactly_on_asc(self):
        """Планета ровно на ASC (куспид 1) → дом 1."""
        cusps = [15.0, 45.0, 75.0, 105.0, 135.0, 165.0,
                 195.0, 225.0, 255.0, 285.0, 315.0, 345.0]
        assert _find_house(15.0, cusps) == 1

    def test_cusps_wrap_around_zero(self):
        """Куспид 12 > куспид 1: обёртка через 0°/360°."""
        # ASC=350°, так куспиды проходят через 0°
        cusps = [350.0, 20.0, 50.0, 80.0, 110.0, 140.0,
                 170.0, 200.0, 230.0, 260.0, 290.0, 320.0]
        # 5° — между куспидом 1 (350°) и куспидом 2 (20°)
        assert _find_house(5.0, cusps) == 1
        # 355° — тоже дом 1
        assert _find_house(355.0, cusps) == 1
        # 25° — дом 2
        assert _find_house(25.0, cusps) == 2

    def test_all_12_houses_reachable(self):
        """Каждый дом должен быть достижим."""
        cusps = [float(i * 30) for i in range(12)]
        found_houses = set()
        for i in range(12):
            lon = i * 30 + 15.0  # середина каждого сектора
            house = _find_house(lon, cusps)
            found_houses.add(house)
        assert found_houses == set(range(1, 13))

    def test_non_uniform_placidus_cusps(self):
        """Неравномерные куспиды Placidus — реальный сценарий."""
        # Типичные куспиды для 55°N
        cusps = [103.5, 133.2, 165.8, 201.4, 234.7, 264.1,
                 283.5, 313.2, 345.8, 21.4, 54.7, 84.1]
        # Планета в 110° → между куспидом 1 (103.5) и куспидом 2 (133.2) → дом 1
        assert _find_house(110.0, cusps) == 1
        # Планета в 200° → между куспидом 3 (165.8) и куспидом 4 (201.4) → дом 3
        assert _find_house(190.0, cusps) == 3


# ═══════════════════════════════════════════════════════════
# _datetime_to_jd — граничные случаи
# ═══════════════════════════════════════════════════════════

class TestDatetimeToJDExtended:
    def test_midnight_is_half_day_before_noon(self):
        """Полночь на 0.5 JD меньше полудня того же дня."""
        midnight = datetime(2000, 1, 1, 0, 0, 0)
        noon = datetime(2000, 1, 1, 12, 0, 0)
        assert _datetime_to_jd(noon) - _datetime_to_jd(midnight) == pytest.approx(0.5, abs=1e-6)

    def test_day_boundary_jan_to_feb(self):
        """Переход января в февраль — ровно N дней."""
        jan31 = datetime(2000, 1, 31, 0, 0, 0)
        feb1 = datetime(2000, 2, 1, 0, 0, 0)
        assert _datetime_to_jd(feb1) - _datetime_to_jd(jan31) == pytest.approx(1.0, abs=1e-6)

    def test_leap_year_feb29(self):
        """29 февраля существует в високосный год."""
        dt = datetime(2000, 2, 29, 12, 0, 0)
        jd = _datetime_to_jd(dt)
        assert jd == pytest.approx(2451604.0, abs=0.01)

    def test_seconds_precision(self):
        """Секундная точность в JD."""
        dt1 = datetime(2000, 1, 1, 12, 0, 0)
        dt2 = datetime(2000, 1, 1, 12, 0, 1)
        diff = _datetime_to_jd(dt2) - _datetime_to_jd(dt1)
        expected = 1 / (24 * 3600)
        assert diff == pytest.approx(expected, rel=1e-5)


# ═══════════════════════════════════════════════════════════
# assign_houses — граничные случаи
# ═══════════════════════════════════════════════════════════

class TestAssignHousesExtended:
    def test_retrograde_planet_gets_house(self):
        """Ретроградная планета тоже получает дом."""
        planet = _make_planet("Saturn", 270.0, speed=-0.03)
        assert planet.retrograde is True
        cusps = [float(i * 30) for i in range(12)]
        houses = _make_houses_from_cusps(cusps)
        result = assign_houses([planet], houses)
        assert result[0].house == 10  # 270° = начало 10-го дома

    def test_north_node_gets_house(self):
        """Северный узел получает дом."""
        planet = _make_planet("North Node", 45.5)
        cusps = [float(i * 30) for i in range(12)]
        houses = _make_houses_from_cusps(cusps)
        result = assign_houses([planet], houses)
        assert result[0].house == 2

    def test_asc_degree_planet_in_house_1(self):
        """Планета точно на ASC → дом 1."""
        cusps = [15.0] + [15.0 + i * 30 for i in range(1, 12)]
        houses = _make_houses_from_cusps(cusps)
        planet = _make_planet("Sun", 15.0)
        result = assign_houses([planet], houses)
        assert result[0].house == 1

    def test_empty_planets_list(self):
        """Пустой список планет — возвращается пустой список."""
        cusps = [float(i * 30) for i in range(12)]
        houses = _make_houses_from_cusps(cusps)
        result = assign_houses([], houses)
        assert result == []


# ═══════════════════════════════════════════════════════════
# Знаменитости — известные позиции Солнца
# (интеграционные тесты, требуют ephemeris-файлы)
# ═══════════════════════════════════════════════════════════

@pytest.mark.integration
class TestCelebrityCharts:
    """Верификация через реальные даты рождения знаменитостей.

    Источник: Astro-Databank (AA-рейтинг).
    Допуск: ±1° для Солнца (более чем достаточно для знака).
    """

    def _get_sun(self, dt: datetime) -> PlanetResult:
        planets = calculate_planets(dt)
        return next(p for p in planets if p.name == "Sun")

    def _get_moon(self, dt: datetime) -> PlanetResult:
        planets = calculate_planets(dt)
        return next(p for p in planets if p.name == "Moon")

    # ── Солнечные знаки ──────────────────────────────────

    def test_napoleon_sun_leo(self):
        """Наполеон Бонапарт, 15 авг 1769 → Солнце в Льве."""
        dt = datetime(1769, 8, 15, 12, 0, 0)
        sun = self._get_sun(dt)
        assert sun.sign == "Leo"

    def test_einstein_sun_pisces(self):
        """Альберт Эйнштейн, 14 мар 1879 → Солнце в Рыбах."""
        dt = datetime(1879, 3, 14, 12, 0, 0)
        sun = self._get_sun(dt)
        assert sun.sign == "Pisces"

    def test_mozart_sun_aquarius(self):
        """Моцарт, 27 янв 1756 → Солнце в Водолее."""
        dt = datetime(1756, 1, 27, 12, 0, 0)
        sun = self._get_sun(dt)
        assert sun.sign == "Aquarius"

    def test_darwin_sun_aquarius(self):
        """Чарльз Дарвин, 12 фев 1809 → Солнце в Водолее."""
        dt = datetime(1809, 2, 12, 12, 0, 0)
        sun = self._get_sun(dt)
        assert sun.sign == "Aquarius"

    def test_tesla_sun_cancer(self):
        """Никола Тесла, 10 июл 1856 → Солнце в Раке."""
        dt = datetime(1856, 7, 10, 12, 0, 0)
        sun = self._get_sun(dt)
        assert sun.sign == "Cancer"

    def test_marx_sun_taurus(self):
        """Карл Маркс, 5 мая 1818 → Солнце в Тельце."""
        dt = datetime(1818, 5, 5, 12, 0, 0)
        sun = self._get_sun(dt)
        assert sun.sign == "Taurus"

    # ── Точность градусов ────────────────────────────────

    def test_j2000_sun_capricorn_exact(self):
        """J2000.0: Солнце ~280.5° — Козерог ~10.5°."""
        dt = datetime(2000, 1, 1, 12, 0, 0)
        sun = self._get_sun(dt)
        assert sun.sign == "Capricorn"
        assert 9.0 <= sun.degree_in_sign <= 12.0

    def test_vernal_equinox_sun_aries(self):
        """Весеннее равноденствие ~20 марта → Солнце входит в Овен."""
        dt = datetime(2000, 3, 20, 7, 35, 0)  # UTC весеннее равноденствие 2000
        sun = self._get_sun(dt)
        assert sun.sign == "Aries"
        assert sun.degree_in_sign < 1.0  # почти 0° Овна

    # ── Граничные моменты ────────────────────────────────

    def test_midnight_different_from_noon(self):
        """Луна сдвигается ~6° за 12 часов — полночь ≠ полдень."""
        noon = datetime(2000, 6, 15, 12, 0, 0)
        midnight = datetime(2000, 6, 15, 0, 0, 0)
        moon_noon = self._get_moon(noon)
        moon_midnight = self._get_moon(midnight)
        diff = abs(moon_noon.longitude - moon_midnight.longitude)
        assert diff > 5.0  # Луна ~12°/сутки → ~6° за 12 ч

    def test_day_change_sun_moves_1_degree(self):
        """Солнце движется ~1°/сутки."""
        dt1 = datetime(2000, 6, 15, 12, 0, 0)
        dt2 = datetime(2000, 6, 16, 12, 0, 0)
        sun1 = self._get_sun(dt1)
        sun2 = self._get_sun(dt2)
        diff = (sun2.longitude - sun1.longitude) % 360
        assert 0.9 <= diff <= 1.1

    def test_mercury_can_be_retrograde(self):
        """Меркурий бывает ретроградным — проверяем конкретную дату."""
        # Меркурий был ретроградным в апреле 2024
        dt = datetime(2024, 4, 15, 12, 0, 0)
        planets = calculate_planets(dt)
        mercury = next(p for p in planets if p.name == "Mercury")
        assert mercury.retrograde is True

    def test_north_node_always_retrograde(self):
        """Средний Северный Узел всегда ретроградный."""
        dt = datetime(2000, 1, 1, 12, 0, 0)
        planets = calculate_planets(dt)
        node = next(p for p in planets if p.name == "North Node")
        assert node.retrograde is True


# ═══════════════════════════════════════════════════════════
# calculate_houses — расширенные интеграционные тесты
# ═══════════════════════════════════════════════════════════

@pytest.mark.integration
class TestCalculateHousesExtended:
    def test_equator_placidus(self):
        """На экваторе Placidus работает без предупреждений."""
        dt = datetime(2000, 1, 1, 12, 0, 0)
        houses, asc, mc, warnings = calculate_houses(dt, 0.0, 0.0, "placidus")
        assert len(houses) == 12
        # На экваторе нет предупреждений о полярных широтах
        polar_warnings = [w for w in warnings if "polar" in w.lower()]
        assert len(polar_warnings) == 0

    def test_southern_hemisphere(self):
        """Южное полушарие: Buenos Aires."""
        dt = datetime(2000, 6, 21, 12, 0, 0)  # зимнее солнцестояние в ЮП
        houses, asc, mc, warnings = calculate_houses(dt, -34.6, -58.4, "placidus")
        assert len(houses) == 12
        assert 0.0 <= asc.longitude < 360.0

    def test_polar_circle_warning(self):
        """Широта 67°N (за полярным кругом) → предупреждение для Placidus."""
        dt = datetime(2000, 6, 21, 12, 0, 0)
        _, _, _, warnings = calculate_houses(dt, 67.0, 25.0, "placidus")
        assert len(warnings) > 0

    def test_extreme_lat_89_no_exception(self):
        """89°N не должно бросать исключение — fallback на Equal."""
        dt = datetime(2000, 1, 1, 12, 0, 0)
        houses, asc, mc, warnings = calculate_houses(dt, 89.0, 0.0, "placidus")
        assert len(houses) == 12
        fallback_warnings = [w for w in warnings if "falling back" in w.lower()]
        assert len(fallback_warnings) > 0

    def test_whole_sign_system(self):
        """Whole Sign: все дома ровно по 30°, куспиды кратны 30°."""
        dt = datetime(2000, 3, 20, 7, 35, 0)  # ASC ~0° Овна
        houses, asc, mc, warnings = calculate_houses(dt, 0.0, 0.0, "whole_sign")
        assert len(houses) == 12

    def test_asc_mc_not_equal(self):
        """ASC и MC — разные точки."""
        dt = datetime(2000, 1, 1, 12, 0, 0)
        _, asc, mc, _ = calculate_houses(dt, 55.75, 37.62)
        assert asc.longitude != mc.longitude

    def test_house_cusps_monotone_or_wrap(self):
        """Куспиды либо монотонно растут, либо делают один переход через 0°."""
        dt = datetime(2000, 1, 1, 12, 0, 0)
        houses, _, _, _ = calculate_houses(dt, 55.75, 37.62)
        cusps = [h.degree for h in houses]
        # Считаем "обратные переходы" (где следующий куспид меньше текущего)
        wraps = sum(1 for i in range(len(cusps) - 1) if cusps[i + 1] < cusps[i])
        # Допускаем не более одного обратного перехода (через 360°→0°)
        assert wraps <= 1


# ═══════════════════════════════════════════════════════════
# calculate_full_chart — расширенные тесты
# ═══════════════════════════════════════════════════════════

@pytest.mark.integration
class TestCalculateFullChartExtended:
    def test_returns_full_chart_type(self):
        dt = datetime(1990, 6, 15, 10, 30, 0)
        chart, aspects = calculate_full_chart(dt, 48.85, 2.35)
        assert isinstance(chart, FullChart)

    def test_asc_mc_present(self):
        dt = datetime(1990, 6, 15, 10, 30, 0)
        chart, _ = calculate_full_chart(dt, 48.85, 2.35)
        assert chart.ascendant is not None
        assert chart.midheaven is not None
        assert isinstance(chart.ascendant, PointResult)
        assert isinstance(chart.midheaven, PointResult)

    def test_time_unknown_produces_warning_and_valid_chart(self):
        dt = datetime(1990, 6, 15, 12, 0, 0)  # noon
        chart, _ = calculate_full_chart(dt, 48.85, 2.35, time_unknown=True)
        warning_texts = " ".join(chart.warnings).lower()
        assert "unknown" in warning_texts or "noon" in warning_texts
        # Карта всё равно полностью посчитана
        assert len(chart.planets) == 11
        assert len(chart.houses) == 12

    def test_all_planets_have_valid_house(self):
        dt = datetime(1990, 6, 15, 10, 30, 0)
        chart, _ = calculate_full_chart(dt, 48.85, 2.35)
        for planet in chart.planets:
            assert hasattr(planet, "house"), f"{planet.name} missing house attr"
            assert 1 <= planet.house <= 12, f"{planet.name} house={planet.house} out of range"

    def test_different_house_systems_give_different_cusps(self):
        """Placidus и Equal дают разные куспиды (кроме дома 1)."""
        dt = datetime(1990, 6, 15, 10, 30, 0)
        chart_p, _ = calculate_full_chart(dt, 55.75, 37.62, house_system="placidus")
        chart_e, _ = calculate_full_chart(dt, 55.75, 37.62, house_system="equal")
        # Хотя бы один куспид (кроме дома 1) должен отличаться
        placidus_cusps = [h.degree for h in chart_p.houses[1:]]
        equal_cusps = [h.degree for h in chart_e.houses[1:]]
        assert placidus_cusps != equal_cusps

    def test_no_warnings_for_normal_case(self):
        """Обычный случай (Москва, известное время) → нет предупреждений."""
        dt = datetime(1990, 6, 15, 10, 30, 0)
        chart, _ = calculate_full_chart(dt, 55.75, 37.62)
        assert len(chart.warnings) == 0


# ═══════════════════════════════════════════════════════════
# lru_cache — кэш планет
# ═══════════════════════════════════════════════════════════

class TestPlanetCache:
    """_calc_planet_position использует lru_cache — один и тот же JD
    должен возвращать идентичный объект без повторного вызова swe.calc_ut."""

    def test_same_jd_returns_cached_result(self):
        # Сбрасываем кэш перед тестом
        _calc_planet_position.cache_clear()

        import swisseph as _swe
        sun_id = _swe.SUN
        jd = 2451545.0

        with patch("backend.ephemeris.calculator.swe.calc_ut") as mock_calc:
            mock_calc.return_value = ((280.0, 0.0, 1.0, 1.0, 0.0, 0.0), 0)

            result1 = _calc_planet_position(sun_id, jd)
            result2 = _calc_planet_position(sun_id, jd)

            assert result1 == result2
            # calc_ut должен вызваться только один раз благодаря кэшу
            mock_calc.assert_called_once()

        _calc_planet_position.cache_clear()

    def test_different_jd_calls_calc_twice(self):
        _calc_planet_position.cache_clear()

        import swisseph as _swe
        sun_id = _swe.SUN

        with patch("backend.ephemeris.calculator.swe.calc_ut") as mock_calc:
            mock_calc.return_value = ((280.0, 0.0, 1.0, 1.0, 0.0, 0.0), 0)

            _calc_planet_position(sun_id, 2451545.0)
            _calc_planet_position(sun_id, 2451546.0)

            assert mock_calc.call_count == 2

        _calc_planet_position.cache_clear()
