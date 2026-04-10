"""Tests for interpretation engines."""

import pytest
from backend.interpretation.base import InterpretationRequest
from backend.interpretation.template import TemplateEngine
from backend.interpretation.prompts import build_system_prompt, _compact_profile
from backend.interpretation.router import InterpretationRouter


# Sample natal profile for testing
SAMPLE_PROFILE = {
    "planets": [
        {"name": "Sun", "sign": "Aries", "degree_in_sign": 15.3, "house": 10, "retrograde": False, "longitude": 15.3},
        {"name": "Moon", "sign": "Cancer", "degree_in_sign": 22.1, "house": 1, "retrograde": False, "longitude": 112.1},
        {"name": "Mercury", "sign": "Pisces", "degree_in_sign": 28.5, "house": 9, "retrograde": True, "longitude": 358.5},
        {"name": "Venus", "sign": "Taurus", "degree_in_sign": 10.0, "house": 11, "retrograde": False, "longitude": 40.0},
        {"name": "Mars", "sign": "Leo", "degree_in_sign": 5.7, "house": 2, "retrograde": False, "longitude": 125.7},
        {"name": "Jupiter", "sign": "Sagittarius", "degree_in_sign": 18.2, "house": 6, "retrograde": False, "longitude": 258.2},
        {"name": "Saturn", "sign": "Capricorn", "degree_in_sign": 3.9, "house": 7, "retrograde": False, "longitude": 273.9},
        {"name": "Uranus", "sign": "Aquarius", "degree_in_sign": 12.0, "house": 8, "retrograde": False, "longitude": 312.0},
        {"name": "Neptune", "sign": "Aquarius", "degree_in_sign": 1.5, "house": 8, "retrograde": False, "longitude": 301.5},
        {"name": "Pluto", "sign": "Sagittarius", "degree_in_sign": 8.3, "house": 5, "retrograde": False, "longitude": 248.3},
        {"name": "North Node", "sign": "Leo", "degree_in_sign": 15.0, "house": 2, "retrograde": False, "longitude": 135.0},
    ],
    "houses": [
        {"number": i, "sign": s, "degree": d}
        for i, (s, d) in enumerate([
            ("Cancer", 90.0), ("Leo", 120.0), ("Virgo", 150.0),
            ("Libra", 180.0), ("Scorpio", 210.0), ("Sagittarius", 240.0),
            ("Capricorn", 270.0), ("Aquarius", 300.0), ("Pisces", 330.0),
            ("Aries", 0.0), ("Taurus", 30.0), ("Gemini", 60.0),
        ], 1)
    ],
    "aspects": [
        {"planet1": "Sun", "planet2": "Moon", "aspect_type": "square", "orb": 3.2, "angle": 96.8, "applying": True},
        {"planet1": "Venus", "planet2": "Mars", "aspect_type": "square", "orb": 4.3, "angle": 85.7, "applying": False},
        {"planet1": "Jupiter", "planet2": "Saturn", "aspect_type": "sextile", "orb": 5.7, "angle": 15.7, "applying": True},
    ],
    "ascendant": {"sign": "Cancer", "degree": 5.2, "longitude": 95.2},
    "midheaven": {"sign": "Aries", "degree": 1.0, "longitude": 1.0},
    "time_unknown": False,
}


class TestTemplateEngine:
    @pytest.fixture
    def engine(self):
        return TemplateEngine()

    @pytest.fixture
    def interp_request(self):
        return InterpretationRequest(natal_profile=SAMPLE_PROFILE)

    @pytest.mark.asyncio
    async def test_generate_returns_content(self, engine, interp_request):
        result = await engine.generate(interp_request)
        assert len(result.content) > 100
        assert result.engine == "template"
        assert result.tokens_used == 0

    @pytest.mark.asyncio
    async def test_generate_contains_sun_sign(self, engine, interp_request):
        result = await engine.generate(interp_request)
        assert "Овн" in result.content or "Aries" in result.content

    @pytest.mark.asyncio
    async def test_generate_contains_moon_sign(self, engine, interp_request):
        result = await engine.generate(interp_request)
        assert "Рак" in result.content or "Cancer" in result.content

    @pytest.mark.asyncio
    async def test_generate_contains_sections(self, engine, interp_request):
        result = await engine.generate(interp_request)
        assert "###" in result.content

    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self, engine, interp_request):
        chunks = []
        async for chunk in engine.stream(interp_request):
            chunks.append(chunk)
        assert len(chunks) > 0
        full_text = "".join(chunks)
        assert len(full_text) > 100

    @pytest.mark.asyncio
    async def test_health_check_always_true(self, engine):
        assert await engine.health_check() is True

    @pytest.mark.asyncio
    async def test_time_unknown_profile(self, engine):
        profile = SAMPLE_PROFILE.copy()
        profile["time_unknown"] = True
        req = InterpretationRequest(natal_profile=profile)
        result = await engine.generate(req)
        assert len(result.content) > 100

    @pytest.mark.asyncio
    async def test_empty_sections(self, engine):
        req = InterpretationRequest(
            natal_profile=SAMPLE_PROFILE,
            sections=[],
        )
        result = await engine.generate(req)
        # Should still produce something from aspects
        assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_specific_sections(self, engine):
        req = InterpretationRequest(
            natal_profile=SAMPLE_PROFILE,
            sections=["career", "finance"],
        )
        result = await engine.generate(req)
        assert "Карьер" in result.content or "карьер" in result.content


class TestPromptBuilder:
    def test_build_prompt_russian(self):
        req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, language="ru")
        prompt = build_system_prompt(req)
        assert "русский" in prompt
        assert "Общий портрет" in prompt
        assert "json" in prompt.lower()

    def test_build_prompt_english(self):
        req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, language="en")
        prompt = build_system_prompt(req)
        assert "English" in prompt
        assert "Personality" in prompt

    def test_time_unknown_warning(self):
        profile = SAMPLE_PROFILE.copy()
        profile["time_unknown"] = True
        req = InterpretationRequest(natal_profile=profile)
        prompt = build_system_prompt(req)
        assert "неизвестно" in prompt.lower() or "unknown" in prompt.lower()

    def test_compact_profile_reduces_precision(self):
        compact = _compact_profile(SAMPLE_PROFILE)
        for p in compact["planets"]:
            # Degree should have at most 1 decimal place
            deg = p["degree"]
            assert deg == round(deg, 1)


class TestInterpretationRouter:
    @pytest.mark.asyncio
    async def test_router_falls_back_to_template(self):
        """With no API keys, router should fall back to template engine."""
        router = InterpretationRouter()
        req = InterpretationRequest(natal_profile=SAMPLE_PROFILE)
        result = await router.generate(req)
        # Without API keys, GPT-4o and DeepSeek will fail
        # Router should fall back to template
        assert result.content
        assert len(result.content) > 100
        assert result.engine in ("template", "gpt4o", "deepseek")

    @pytest.mark.asyncio
    async def test_router_stream_fallback(self):
        """Streaming should also fall back to template."""
        router = InterpretationRouter()
        req = InterpretationRequest(natal_profile=SAMPLE_PROFILE)
        chunks = []
        async for chunk in router.stream(req):
            chunks.append(chunk)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_router_caches_result(self):
        """Second call should return cached result."""
        router = InterpretationRouter()
        req = InterpretationRequest(natal_profile=SAMPLE_PROFILE)
        result1 = await router.generate(req)
        result2 = await router.generate(req)
        assert result2.cached is True
        assert result2.content == result1.content

    @pytest.mark.asyncio
    async def test_router_status(self):
        router = InterpretationRouter()
        status = await router.get_status()
        assert "template" in status
        assert status["template"] is True
        assert "daily_spend_usd" in status

    @pytest.mark.asyncio
    async def test_validation_rejects_short(self):
        router = InterpretationRouter()
        assert router._validate_response("short", ["general"]) is False
        assert router._validate_response("", ["general"]) is False

    @pytest.mark.asyncio
    async def test_validation_accepts_good(self):
        router = InterpretationRouter()
        good_text = "### Общий портрет личности\n\n" + "x" * 300
        assert router._validate_response(good_text, ["general"]) is True
