"""Tests for input validation and edge-cases."""

import pytest
from datetime import date

from backend.schemas import BirthDataInput, TransitRequest
from backend.ephemeris.geo import resolve_utc_datetime, validate_coordinates, AmbiguousTimeError
from backend.cache import TTLCache, make_profile_hash


class TestBirthDataValidation:
    def test_valid_input(self):
        data = BirthDataInput(
            birth_date=date(2000, 1, 15),
            birth_time="14:30",
            birth_place="Berlin, Germany",
        )
        assert data.birth_date == date(2000, 1, 15)
        assert data.birth_time == "14:30"

    def test_no_time(self):
        data = BirthDataInput(
            birth_date=date(2000, 1, 15),
            birth_place="Berlin, Germany",
        )
        assert data.birth_time is None

    def test_date_before_1900_rejected(self):
        with pytest.raises(ValueError, match="1900"):
            BirthDataInput(
                birth_date=date(1800, 5, 10),
                birth_place="London",
            )

    def test_date_after_2100_rejected(self):
        with pytest.raises(ValueError, match="2100"):
            BirthDataInput(
                birth_date=date(2101, 1, 1),
                birth_place="London",
            )

    def test_future_date_rejected(self):
        with pytest.raises(ValueError, match="future"):
            BirthDataInput(
                birth_date=date(2030, 12, 31),
                birth_place="London",
            )

    def test_invalid_time_format(self):
        with pytest.raises(ValueError):
            BirthDataInput(
                birth_date=date(2000, 1, 15),
                birth_time="25:00",
                birth_place="Berlin",
            )

    def test_invalid_house_system(self):
        with pytest.raises(ValueError):
            BirthDataInput(
                birth_date=date(2000, 1, 15),
                birth_place="Berlin",
                house_system="invalid",
            )

    def test_koch_accepted(self):
        data = BirthDataInput(
            birth_date=date(2000, 1, 15),
            birth_place="Berlin",
            house_system="koch",
        )
        assert data.house_system == "koch"


class TestTransitValidation:
    def test_valid_range(self):
        req = TransitRequest(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 2, 1),
        )
        assert req.from_date < req.to_date

    def test_end_before_start(self):
        with pytest.raises(ValueError, match="after"):
            TransitRequest(
                from_date=date(2026, 2, 1),
                to_date=date(2026, 1, 1),
            )

    def test_too_long_period(self):
        with pytest.raises(ValueError, match="366"):
            TransitRequest(
                from_date=date(2026, 1, 1),
                to_date=date(2027, 6, 1),
            )


class TestTimezoneResolution:
    def test_basic_utc_conversion(self):
        utc_dt, time_unknown, warnings = resolve_utc_datetime(
            "2000-06-15", "14:00", "Europe/Berlin"
        )
        # Berlin is UTC+2 in summer → 14:00 CEST = 12:00 UTC
        assert utc_dt.hour == 12
        assert time_unknown is False

    def test_unknown_time_defaults_noon(self):
        utc_dt, time_unknown, warnings = resolve_utc_datetime(
            "2000-01-15", None, "Europe/Berlin"
        )
        assert time_unknown is True
        assert any("12:00" in w for w in warnings)

    def test_winter_time(self):
        utc_dt, _, _ = resolve_utc_datetime(
            "2000-01-15", "14:00", "Europe/Berlin"
        )
        # Berlin CET = UTC+1 in winter → 14:00 CET = 13:00 UTC
        assert utc_dt.hour == 13


class TestCoordinateValidation:
    def test_valid_coords(self):
        warnings = validate_coordinates(52.52, 13.405)
        assert len(warnings) == 0

    def test_polar_warning(self):
        warnings = validate_coordinates(70.0, 25.0)
        assert any("polar" in w.lower() for w in warnings)

    def test_invalid_latitude(self):
        with pytest.raises(ValueError):
            validate_coordinates(95.0, 13.0)

    def test_invalid_longitude(self):
        with pytest.raises(ValueError):
            validate_coordinates(52.0, 200.0)


class TestTTLCache:
    def test_set_get(self):
        cache = TTLCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_missing_key(self):
        cache = TTLCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        import time
        cache = TTLCache()
        cache.set("key1", "value1", ttl=1)
        assert cache.get("key1") == "value1"
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_delete(self):
        cache = TTLCache()
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None

    def test_clear(self):
        cache = TTLCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert len(cache) == 0


class TestProfileHash:
    def test_deterministic(self):
        profile = {"sun": "Aries", "moon": "Cancer"}
        h1 = make_profile_hash(profile)
        h2 = make_profile_hash(profile)
        assert h1 == h2

    def test_different_profiles_different_hashes(self):
        h1 = make_profile_hash({"sun": "Aries"})
        h2 = make_profile_hash({"sun": "Taurus"})
        assert h1 != h2
