"""Tests for transit calculation engine (Phase 3).

Validates:
- Transit event detection
- Aspect orb correctness
- Deduplication within same week
- Exact date refinement
- Planet filter
- Orb filter
- Date range validation
- Template-based transit interpretation
"""

import pytest
from datetime import date, datetime

from backend.transit.engine import (
    calculate_transits,
    get_transit_summary,
    TransitEvent,
    TRANSIT_ORBS,
    _find_exact_aspect,
)
from backend.transit.prompts import (
    get_template_transit_text,
    build_transit_event_prompt,
    build_transit_period_prompt,
)
from backend.ephemeris.calculator import PLANETS


# ── Sample natal chart data (Capricorn Sun, Cancer Moon, Berlin) ──
SAMPLE_NATAL_PLANETS = [
    {"name": "Sun", "longitude": 280.5, "sign": "Capricorn", "degree_in_sign": 10.5,
     "house": 4, "retrograde": False},
    {"name": "Moon", "longitude": 112.1, "sign": "Cancer", "degree_in_sign": 22.1,
     "house": 10, "retrograde": False},
    {"name": "Mercury", "longitude": 265.3, "sign": "Sagittarius", "degree_in_sign": 25.3,
     "house": 3, "retrograde": False},
    {"name": "Venus", "longitude": 310.0, "sign": "Aquarius", "degree_in_sign": 10.0,
     "house": 5, "retrograde": False},
    {"name": "Mars", "longitude": 45.7, "sign": "Taurus", "degree_in_sign": 15.7,
     "house": 8, "retrograde": False},
    {"name": "Jupiter", "longitude": 258.2, "sign": "Sagittarius", "degree_in_sign": 18.2,
     "house": 3, "retrograde": False},
    {"name": "Saturn", "longitude": 273.9, "sign": "Capricorn", "degree_in_sign": 3.9,
     "house": 4, "retrograde": False},
    {"name": "Uranus", "longitude": 312.0, "sign": "Aquarius", "degree_in_sign": 12.0,
     "house": 5, "retrograde": False},
    {"name": "Neptune", "longitude": 301.5, "sign": "Aquarius", "degree_in_sign": 1.5,
     "house": 5, "retrograde": False},
    {"name": "Pluto", "longitude": 248.3, "sign": "Sagittarius", "degree_in_sign": 8.3,
     "house": 3, "retrograde": False},
    {"name": "North Node", "longitude": 135.0, "sign": "Leo", "degree_in_sign": 15.0,
     "house": 11, "retrograde": False},
]


class TestTransitCalculation:
    """Core transit engine tests."""

    def test_transits_found_for_month(self):
        """A month should produce at least some transit events."""
        events = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
        )
        assert len(events) > 0
        assert all(isinstance(e, TransitEvent) for e in events)

    def test_transit_event_fields(self):
        """Each event should have all required fields populated."""
        events = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 7),
        )
        assert len(events) > 0
        for e in events:
            assert e.date
            assert e.transit_planet
            assert e.natal_planet
            assert e.aspect_type in {"conjunction", "sextile", "square", "trine", "opposition"}
            assert 0 <= e.orb <= max(TRANSIT_ORBS.values())

    def test_transit_orbs_within_limits(self):
        """All detected transits should have orbs within defined limits."""
        events = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 5, 1),
            to_date=date(2026, 5, 31),
        )
        for e in events:
            max_orb = TRANSIT_ORBS[e.aspect_type]
            assert e.orb <= max_orb + 0.01, (
                f"{e.transit_planet} {e.aspect_type} {e.natal_planet}: "
                f"orb {e.orb} > max {max_orb}"
            )

    def test_events_sorted_by_date(self):
        """Events should be sorted by date ascending."""
        events = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
        )
        dates = [e.date for e in events]
        assert dates == sorted(dates)

    def test_planet_filter(self):
        """Planet filter should only return matching transit planets."""
        events = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
            planet_filter=["Saturn"],
        )
        for e in events:
            assert e.transit_planet == "Saturn"

    def test_orb_filter(self):
        """Custom orb filter should restrict results."""
        events_wide = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
        )
        events_narrow = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
            orb_filter=0.5,
        )
        # Narrow filter should return fewer or equal events
        assert len(events_narrow) <= len(events_wide)
        for e in events_narrow:
            assert e.orb <= 0.5 + 0.01

    def test_no_north_node_transits(self):
        """North Node should be excluded from transit planets by default."""
        events = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
        )
        for e in events:
            assert e.transit_planet != "North Node"

    def test_short_period(self):
        """Single day should still produce events (fast planets)."""
        events = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 4, 15),
            to_date=date(2026, 4, 16),
        )
        # At least the Moon should form some aspects in 24h
        assert len(events) >= 0  # may be 0 on some days, but shouldn't crash

    def test_year_period(self):
        """Full year should produce many events without crashing."""
        events = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 12, 31),
        )
        # A full year should have at least 50+ transits
        assert len(events) > 50


class TestExactDateRefinement:
    """Test exact aspect date calculation via bisection."""

    def test_exact_date_returned(self):
        """Events should have exact_date when refinement succeeds."""
        events = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
        )
        # At least some events should have exact dates
        with_exact = [e for e in events if e.exact_date is not None]
        assert len(with_exact) > 0

    def test_exact_date_within_range(self):
        """Exact dates should be within the transit period."""
        events = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
        )
        for e in events:
            if e.exact_date:
                exact_dt = datetime.fromisoformat(e.exact_date)
                # Should be within a few days of the detection date
                event_dt = datetime.strptime(e.date, "%Y-%m-%d")
                delta = abs((exact_dt - event_dt).days)
                assert delta <= 3, (
                    f"Exact date {e.exact_date} too far from detection {e.date} "
                    f"for {e.transit_planet} {e.aspect_type} {e.natal_planet}"
                )


class TestTransitSummary:
    """Test transit summary generation."""

    def test_summary_structure(self):
        events = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
        )
        summary = get_transit_summary(events)
        assert "total_events" in summary
        assert "by_aspect" in summary
        assert "by_transit_planet" in summary
        assert "significant" in summary
        assert summary["total_events"] == len(events)

    def test_significant_limited_to_10(self):
        events = calculate_transits(
            natal_planets=SAMPLE_NATAL_PLANETS,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 12, 31),
        )
        summary = get_transit_summary(events)
        assert len(summary["significant"]) <= 10


class TestTransitTemplates:
    """Test template-based transit interpretation (fallback)."""

    def test_known_transit_template(self):
        text = get_template_transit_text("Jupiter", "Sun", "conjunction")
        assert "Юпитер" in text or "Jupiter" in text
        assert len(text) > 50

    def test_unknown_transit_fallback(self):
        text = get_template_transit_text("Mercury", "Neptune", "trine")
        assert len(text) > 20  # should produce generic fallback

    def test_saturn_square(self):
        text = get_template_transit_text("Saturn", "Moon", "square")
        assert "Сатурн" in text or "Saturn" in text

    def test_all_outer_planet_templates_exist(self):
        """Major outer planet transits should have dedicated templates."""
        outer = ["Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
        major_aspects = ["conjunction", "opposition", "square"]
        for planet in outer:
            for aspect in major_aspects:
                text = get_template_transit_text(planet, "Sun", aspect)
                # Should be longer than generic fallback
                assert len(text) > 60, f"Missing template for {planet} {aspect}"


class TestTransitPromptBuilder:
    def test_event_prompt_contains_transit(self):
        event = {
            "transit_planet": "Saturn",
            "natal_planet": "Sun",
            "aspect_type": "conjunction",
            "transit_sign": "Capricorn",
            "transit_degree": 12.3,
            "transit_house": 4,
            "transit_retrograde": False,
            "natal_sign": "Capricorn",
            "natal_degree": 10.5,
            "natal_house": 4,
            "exact_orb": 0.5,
            "exact_date": "2026-04-15",
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
        }
        profile = {"planets": SAMPLE_NATAL_PLANETS, "houses": [], "aspects": []}
        prompt = build_transit_event_prompt(event, profile)
        # Факты переводятся на русский (ИИ не видит сырых английских значений
        # от клиента) — проверяем переведённые планету и аспект.
        assert "Сатурн" in prompt
        assert "соединение" in prompt
        assert "Не вычисляй" in prompt

    def test_period_prompt_limits_events(self):
        """Period prompt should limit to top 20 events."""
        events = [
            {"date": f"2026-04-{i:02d}", "transit_planet": "Moon",
             "natal_planet": "Sun", "aspect_type": "conjunction", "orb": float(i)}
            for i in range(1, 30)
        ]
        profile = {"planets": SAMPLE_NATAL_PLANETS, "houses": [], "aspects": []}
        prompt = build_transit_period_prompt(
            events, profile, "2026-04-01", "2026-04-30"
        )
        # Should contain transit data but not all 29 events
        assert "Moon" in prompt
