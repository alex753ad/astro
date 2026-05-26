"""tests/test_aspects.py — тесты ephemeris/aspects.py.

Покрывает:
  - ASPECTS конфигурация (углы, орбы)
  - _angular_distance — кратчайший угол между двумя долготами
  - _get_orb — светила получают расширенные орбы
  - _is_applying — сближение / удаление
  - calculate_aspects — полный расчёт для набора планет
  - Граничные случаи: wrap-around 359°/1°, одна точка, пустой список

Запуск: pytest backend/tests/test_aspects.py -v
"""

from __future__ import annotations

import pytest

from backend.ephemeris.aspects import (
    calculate_aspects,
    _angular_distance,
    _get_orb,
    _is_applying,
    ASPECTS,
    DEFAULT_ORBS,
    LUMINARY_ORBS,
    LUMINARIES,
    AspectResult,
)
from backend.ephemeris.calculator import PlanetResult, _longitude_to_sign


# ── Helpers ───────────────────────────────────────────────────────────────────

def _planet(name: str, lon: float, speed: float = 1.0) -> PlanetResult:
    sign, deg = _longitude_to_sign(lon % 360)
    return PlanetResult(
        name=name,
        longitude=lon % 360,
        latitude=0.0,
        distance=1.0,
        speed=speed,
        sign=sign,
        degree_in_sign=deg,
        retrograde=speed < 0,
    )


def _find(aspects: list[AspectResult], p1: str, p2: str) -> AspectResult | None:
    """Найти аспект между двумя планетами."""
    for a in aspects:
        if {a.planet1, a.planet2} == {p1, p2}:
            return a
    return None


# ═══════════════════════════════════════════════════════════
# ASPECTS — конфигурация
# ═══════════════════════════════════════════════════════════

class TestAspectsConfig:
    def test_all_five_major_aspects_present(self):
        required = {"conjunction", "sextile", "square", "trine", "opposition"}
        assert required == set(ASPECTS.keys())

    def test_aspect_angles_correct(self):
        assert ASPECTS["conjunction"]  == 0.0
        assert ASPECTS["sextile"]      == 60.0
        assert ASPECTS["square"]       == 90.0
        assert ASPECTS["trine"]        == 120.0
        assert ASPECTS["opposition"]   == 180.0

    def test_default_orbs_positive(self):
        for name, orb in DEFAULT_ORBS.items():
            assert orb > 0, f"{name}: orb must be positive"

    def test_luminary_orbs_wider_than_default(self):
        """Светила всегда имеют орбы >= стандартных."""
        for name in ASPECTS:
            assert LUMINARY_ORBS[name] >= DEFAULT_ORBS[name], (
                f"{name}: luminary orb {LUMINARY_ORBS[name]} < default {DEFAULT_ORBS[name]}"
            )

    def test_luminaries_are_sun_and_moon(self):
        assert "Sun" in LUMINARIES
        assert "Moon" in LUMINARIES

    def test_all_aspects_have_orb_defined(self):
        for name in ASPECTS:
            assert name in DEFAULT_ORBS
            assert name in LUMINARY_ORBS


# ═══════════════════════════════════════════════════════════
# _angular_distance
# ═══════════════════════════════════════════════════════════

class TestAngularDistance:
    def test_same_point_is_zero(self):
        assert _angular_distance(45.0, 45.0) == pytest.approx(0.0)

    def test_opposition_is_180(self):
        assert _angular_distance(0.0, 180.0) == pytest.approx(180.0)

    def test_always_returns_shortest(self):
        """_angular_distance всегда <= 180°."""
        for lon1, lon2 in [(0, 270), (10, 350), (90, 300), (1, 359)]:
            dist = _angular_distance(float(lon1), float(lon2))
            assert 0.0 <= dist <= 180.0, f"{lon1}↔{lon2}: {dist}"

    def test_wrap_around_zero(self):
        """359° и 1° → 2°, не 358°."""
        assert _angular_distance(359.0, 1.0) == pytest.approx(2.0)

    def test_symmetric(self):
        """d(a, b) == d(b, a)."""
        assert _angular_distance(30.0, 150.0) == _angular_distance(150.0, 30.0)

    def test_90_degrees(self):
        assert _angular_distance(0.0, 90.0) == pytest.approx(90.0)

    def test_60_degrees(self):
        assert _angular_distance(10.0, 70.0) == pytest.approx(60.0)

    def test_trine_120(self):
        assert _angular_distance(0.0, 120.0) == pytest.approx(120.0)

    def test_270_gives_90(self):
        """270° по длинному пути = 90° по короткому."""
        assert _angular_distance(0.0, 270.0) == pytest.approx(90.0)


# ═══════════════════════════════════════════════════════════
# _get_orb
# ═══════════════════════════════════════════════════════════

class TestGetOrb:
    def test_sun_gets_luminary_orb(self):
        orb = _get_orb("Sun", "Mars", "conjunction")
        assert orb == LUMINARY_ORBS["conjunction"]

    def test_moon_gets_luminary_orb(self):
        orb = _get_orb("Saturn", "Moon", "trine")
        assert orb == LUMINARY_ORBS["trine"]

    def test_two_luminaries_get_luminary_orb(self):
        orb = _get_orb("Sun", "Moon", "opposition")
        assert orb == LUMINARY_ORBS["opposition"]

    def test_non_luminaries_get_default_orb(self):
        orb = _get_orb("Mars", "Saturn", "square")
        assert orb == DEFAULT_ORBS["square"]

    def test_mercury_venus_default(self):
        orb = _get_orb("Mercury", "Venus", "sextile")
        assert orb == DEFAULT_ORBS["sextile"]

    @pytest.mark.parametrize("aspect", list(ASPECTS.keys()))
    def test_all_aspects_return_valid_orb(self, aspect):
        orb = _get_orb("Jupiter", "Saturn", aspect)
        assert orb > 0


# ═══════════════════════════════════════════════════════════
# _is_applying
# ═══════════════════════════════════════════════════════════

class TestIsApplying:
    def test_applying_moon_approaching_sun(self):
        """Луна (быстрая) движется к Солнцу → applying."""
        # Sun на 100°, Moon на 95°, Moon движется вперёд со скоростью 13°/день
        # → Moon через сутки будет на 108°, ближе к Sun (100°), угол 5°→8° нет...
        # Лучше: Sun=100, Moon=97 speed=13 → future Moon=110, dist=10 vs current=3 → separating
        # Нужно: Moon approaching Sun: Sun=100, Moon=95, speed=13/day
        # future Moon=95+13=108, future dist=|108-100|=8 > current=5 → separating
        # Actually let's think again:
        # Sun=100 speed=1, Moon=94 speed=13
        # current dist = 6° (Moon behind Sun)
        # future: Sun=101, Moon=107 → dist=6 (same). Let's try:
        # Sun=100, Moon=93, speed_sun=1, speed_moon=13
        # future: Sun=101, Moon=106 → dist=5 < 7 → applying!
        sun  = _planet("Sun",   100.0, speed=1.0)
        moon = _planet("Moon",   93.0, speed=13.0)
        # current dist = 7°, future dist = |106-101| = 5° → applying
        result = _is_applying(sun, moon, angle=7.0)
        assert result is True

    def test_separating_moon_past_conjunction(self):
        """Луна уже прошла Солнце → separating."""
        # Sun=100 speed=1, Moon=107 speed=13
        # current dist=7, future: Sun=101, Moon=120, dist=19 > 7 → separating
        sun  = _planet("Sun",  100.0, speed=1.0)
        moon = _planet("Moon", 107.0, speed=13.0)
        result = _is_applying(sun, moon, angle=7.0)
        assert result is False

    def test_retrograde_planet_can_apply(self):
        """Ретроградная планета движется назад — может сближаться."""
        # Mars ретроградный на 105°, Sun на 100°, Mars движется к 100°
        # current dist=5, future: Sun=101, Mars=105+(-0.5)=104.5, dist=3.5 < 5 → applying
        sun  = _planet("Sun",  100.0, speed=1.0)
        mars = _planet("Mars", 105.0, speed=-0.5)
        result = _is_applying(sun, mars, angle=5.0)
        assert result is True

    def test_returns_bool(self):
        p1 = _planet("Sun",   0.0)
        p2 = _planet("Moon", 90.0)
        result = _is_applying(p1, p2, angle=90.0)
        assert isinstance(result, bool)


# ═══════════════════════════════════════════════════════════
# calculate_aspects — основные случаи
# ═══════════════════════════════════════════════════════════

class TestCalculateAspects:
    def test_conjunction_exact(self):
        """Sun и Moon в 0° → conjunction, orb=0."""
        sun  = _planet("Sun",  100.0)
        moon = _planet("Moon", 100.0)
        aspects = calculate_aspects([sun, moon])
        conj = _find(aspects, "Sun", "Moon")
        assert conj is not None
        assert conj.aspect_type == "conjunction"
        assert conj.orb == pytest.approx(0.0)

    def test_conjunction_within_orb(self):
        """Sun и Moon в 5° → conjunction (орб 5° < 10° для светил)."""
        sun  = _planet("Sun",  100.0)
        moon = _planet("Moon", 105.0)
        aspects = calculate_aspects([sun, moon])
        conj = _find(aspects, "Sun", "Moon")
        assert conj is not None
        assert conj.aspect_type == "conjunction"
        assert conj.orb == pytest.approx(5.0, abs=0.01)

    def test_no_conjunction_outside_orb(self):
        """Mars и Saturn в 15° → нет conjunction (орб 8°)."""
        mars   = _planet("Mars",    0.0)
        saturn = _planet("Saturn", 15.0)
        aspects = calculate_aspects([mars, saturn])
        conj = _find(aspects, "Mars", "Saturn")
        assert conj is None

    def test_opposition_180(self):
        sun  = _planet("Sun",   0.0)
        mars = _planet("Mars", 180.0)
        aspects = calculate_aspects([sun, mars])
        opp = _find(aspects, "Sun", "Mars")
        assert opp is not None
        assert opp.aspect_type == "opposition"
        assert opp.orb == pytest.approx(0.0)

    def test_trine_120(self):
        sun     = _planet("Sun",       0.0)
        jupiter = _planet("Jupiter", 120.0)
        aspects = calculate_aspects([sun, jupiter])
        tri = _find(aspects, "Sun", "Jupiter")
        assert tri is not None
        assert tri.aspect_type == "trine"

    def test_square_90(self):
        sun    = _planet("Sun",     0.0)
        saturn = _planet("Saturn",  90.0)
        aspects = calculate_aspects([sun, saturn])
        sq = _find(aspects, "Sun", "Saturn")
        assert sq is not None
        assert sq.aspect_type == "square"

    def test_sextile_60(self):
        sun   = _planet("Sun",    0.0)
        venus = _planet("Venus", 60.0)
        aspects = calculate_aspects([sun, venus])
        sxt = _find(aspects, "Sun", "Venus")
        assert sxt is not None
        assert sxt.aspect_type == "sextile"

    def test_returns_list(self):
        result = calculate_aspects([_planet("Sun", 0.0), _planet("Moon", 90.0)])
        assert isinstance(result, list)

    def test_empty_list_returns_empty(self):
        assert calculate_aspects([]) == []

    def test_single_planet_returns_empty(self):
        assert calculate_aspects([_planet("Sun", 0.0)]) == []

    def test_no_duplicates(self):
        """Sun-Moon аспект не дублируется как Moon-Sun."""
        planets = [_planet("Sun", 0.0), _planet("Moon", 120.0)]
        aspects = calculate_aspects(planets)
        pairs = [frozenset([a.planet1, a.planet2]) for a in aspects]
        assert len(pairs) == len(set(pairs))

    def test_sorted_by_orb(self):
        """Результат отсортирован по орбу (тесные аспекты первые)."""
        planets = [
            _planet("Sun",      0.0),
            _planet("Moon",   121.0),   # trine с орбом 1°
            _planet("Mars",   178.0),   # opposition с орбом 2°
        ]
        aspects = calculate_aspects(planets)
        orbs = [a.orb for a in aspects]
        assert orbs == sorted(orbs)

    def test_all_results_are_aspect_result(self):
        planets = [_planet("Sun", 0.0), _planet("Moon", 90.0), _planet("Mars", 180.0)]
        aspects = calculate_aspects(planets)
        for a in aspects:
            assert isinstance(a, AspectResult)


# ═══════════════════════════════════════════════════════════
# AspectResult — структура
# ═══════════════════════════════════════════════════════════

class TestAspectResultStructure:
    def test_has_all_fields(self):
        sun  = _planet("Sun",  0.0)
        moon = _planet("Moon", 90.0)
        aspects = calculate_aspects([sun, moon])
        assert len(aspects) > 0
        a = aspects[0]
        assert hasattr(a, "planet1")
        assert hasattr(a, "planet2")
        assert hasattr(a, "aspect_type")   # не "aspect"!
        assert hasattr(a, "angle")
        assert hasattr(a, "orb")
        assert hasattr(a, "applying")

    def test_planet_names_are_strings(self):
        planets = [_planet("Sun", 0.0), _planet("Mars", 90.0)]
        for a in calculate_aspects(planets):
            assert isinstance(a.planet1, str)
            assert isinstance(a.planet2, str)

    def test_aspect_type_is_valid(self):
        planets = [_planet("Sun", 0.0), _planet("Moon", 120.0)]
        for a in calculate_aspects(planets):
            assert a.aspect_type in ASPECTS

    def test_orb_is_non_negative(self):
        planets = [
            _planet("Sun",      0.0),
            _planet("Moon",   118.0),
            _planet("Mars",   180.0),
        ]
        for a in calculate_aspects(planets):
            assert a.orb >= 0.0

    def test_angle_within_0_180(self):
        planets = [
            _planet("Sun",    0.0),
            _planet("Moon",  90.0),
            _planet("Mars", 180.0),
        ]
        for a in calculate_aspects(planets):
            assert 0.0 <= a.angle <= 180.0

    def test_applying_is_bool(self):
        planets = [_planet("Sun", 0.0), _planet("Moon", 3.0, speed=13.0)]
        for a in calculate_aspects(planets):
            assert isinstance(a.applying, bool)


# ═══════════════════════════════════════════════════════════
# Граничные случаи
# ═══════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_wrap_359_and_1_is_conjunction(self):
        """359° и 1° → угол 2° → conjunction для светил."""
        sun  = _planet("Sun",  359.0)
        moon = _planet("Moon",   1.0)
        aspects = calculate_aspects([sun, moon])
        conj = _find(aspects, "Sun", "Moon")
        assert conj is not None
        assert conj.aspect_type == "conjunction"
        assert conj.orb == pytest.approx(2.0, abs=0.01)

    def test_exact_opposition_wrap(self):
        """10° и 190° → точная opposition."""
        sun  = _planet("Sun",    10.0)
        mars = _planet("Mars",  190.0)
        aspects = calculate_aspects([sun, mars])
        opp = _find(aspects, "Sun", "Mars")
        assert opp is not None
        assert opp.aspect_type == "opposition"
        assert opp.orb == pytest.approx(0.0, abs=0.01)

    def test_11_planets_max_55_aspects(self):
        """11 планет → максимум C(11,2)=55 аспектов."""
        lons = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300]
        planets = [
            _planet(n, float(l))
            for n, l in zip(
                ["Sun","Moon","Mercury","Venus","Mars",
                 "Jupiter","Saturn","Uranus","Neptune","Pluto","North Node"],
                lons,
            )
        ]
        aspects = calculate_aspects(planets)
        assert 0 <= len(aspects) <= 55

    def test_luminary_pair_uses_wider_orb(self):
        """Sun-Moon получают расширенный орб — аспект с орбом 9° проходит."""
        sun  = _planet("Sun",    0.0)
        moon = _planet("Moon",   9.0)   # conjunction, орб 9° < luminary orb 10°
        aspects = calculate_aspects([sun, moon])
        conj = _find(aspects, "Sun", "Moon")
        assert conj is not None, "Sun-Moon 9° должен быть в пределах luminary orb=10°"

    def test_non_luminary_pair_uses_default_orb(self):
        """Mars-Saturn с орбом 9° → нет conjunction (default orb=8°)."""
        mars   = _planet("Mars",    0.0)
        saturn = _planet("Saturn",  9.0)
        aspects = calculate_aspects([mars, saturn])
        conj = _find(aspects, "Mars", "Saturn")
        assert conj is None, "Mars-Saturn 9° не должен попасть в orb=8°"

    def test_trine_with_small_orb(self):
        """Trine с орбом 1° → попадает."""
        sun     = _planet("Sun",       0.0)
        jupiter = _planet("Jupiter", 121.0)
        aspects = calculate_aspects([sun, jupiter])
        tri = _find(aspects, "Sun", "Jupiter")
        assert tri is not None
        assert tri.orb == pytest.approx(1.0, abs=0.01)

    def test_trine_outside_orb_not_found(self):
        """Trine с орбом 9° → не попадает (luminary orb trine=8°)."""
        # Используем не-светила: default orb trine=7°
        mars    = _planet("Mars",      0.0)
        jupiter = _planet("Jupiter", 129.0)   # orb = 9°
        aspects = calculate_aspects([mars, jupiter])
        tri = _find(aspects, "Mars", "Jupiter")
        assert tri is None
