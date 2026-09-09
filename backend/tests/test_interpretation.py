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

    def test_never_cut_off_instruction_present_for_every_tier(self):
        """Раньше «не обрывай предложение» была только в word_limit-ветке —
        в тарифных ветках (в т.ч. free) отсутствовала вовсе."""
        for tier in ("free", "lite", "pro", "premium"):
            req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, tier=tier)
            prompt = build_system_prompt(req)
            assert "не обрывай текст" in prompt, f"tier={tier}"

    def test_prompt_asks_exactly_what_the_plan_says(self):
        """Промпт и план объёма не должны расходиться.

        Раньше тест сверял промпт напрямую с TIER_FLAGS. С 09.09.2026 это
        неверно для коротких секций: модель систематически перевыполняет
        объём, и в нижней зоне мы намеренно просим МЕНЬШЕ заявленного, чтобы
        получить заявленное (см. _volume_plan). Инвариант сместился — теперь
        сверяем промпт с тем, что он обязан просить, а не с витриной.
        """
        from backend.interpretation.prompts import _volume_plan, resolve_word_limit
        for tier in ("free", "lite", "pro", "premium"):
            req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, tier=tier)
            prompt = build_system_prompt(req)
            sections, per_section, _, _ = _volume_plan(req, resolve_word_limit(req))
            assert str(per_section) in prompt, f"tier={tier}: нет объёма на секцию"
            assert str(per_section * sections) in prompt, f"tier={tier}: нет общего объёма"

    def test_uncorrected_tiers_still_match_the_flag(self):
        """Поправка бьёт только по нижней зоне: у lite/pro/premium промпт
        обязан называть ровно тарифное число, иначе поправка расползлась."""
        from backend.auth.rate_limits import TIER_FLAGS
        from backend.interpretation.prompts import _volume_plan, resolve_word_limit
        for tier in ("lite", "pro", "premium"):
            req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, tier=tier)
            sections, per_section, _, _ = _volume_plan(req, resolve_word_limit(req))
            flag = TIER_FLAGS[tier]["interpretation_word_limit"]
            assert abs(per_section * sections - flag) <= sections, tier

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


class TestVolumePlanDerivesParagraphs:
    """Число абзацев обязано выводиться из числа слов, а не стоять рядом с ним.

    До 09.09.2026 в промпте было два независимых числа: «около 500 слов» и
    «2–3 абзаца» на каждую из шести секций. Они противоречили друг другу —
    12–18 абзацев в 500 слов не помещаются, — и модель слушала абзацы. Замер
    настоящего разбора на боевом free-аккаунте: 1067 слов вместо 500, ровно
    по три абзаца в каждой из шести секций.

    Тот же класс дефекта, что charts_per_month рядом с profiles_limit. Здесь
    он закрыт тем, что второе число вычисляется, а тесты ниже стерегут, чтобы
    его не завели обратно руками.
    """

    @staticmethod
    def _plan(tier: str):
        from backend.interpretation.prompts import _volume_plan, resolve_word_limit
        req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, tier=tier)
        return _volume_plan(req, resolve_word_limit(req))

    def test_paragraph_budget_fits_the_word_budget(self):
        """Главный инвариант: абзацы не просят больше слов, чем разрешено.

        Именно это раньше и нарушалось — вдвое. Допуск 25% сверху: абзац
        живой, а не ровно _WORDS_PER_PARAGRAPH.
        """
        from backend.auth.rate_limits import TIER_FLAGS
        from backend.interpretation.prompts import _WORDS_PER_PARAGRAPH

        for tier in ("free", "lite", "pro", "premium"):
            sections, per_section, paragraphs, _ = self._plan(tier)
            asked_by_paragraphs = paragraphs * _WORDS_PER_PARAGRAPH * sections
            allowed = TIER_FLAGS[tier]["interpretation_word_limit"] * 1.25
            assert asked_by_paragraphs <= allowed, (
                f"tier={tier}: абзацы просят {asked_by_paragraphs} слов при "
                f"лимите {TIER_FLAGS[tier]['interpretation_word_limit']}"
            )

    def test_old_free_config_would_fail_this(self):
        """Проверка самой проверки: прежняя пара (500 слов, 3 абзаца на 6
        секций) обязана этот инвариант нарушать — иначе тест выше ничего не
        стережёт."""
        from backend.interpretation.prompts import _WORDS_PER_PARAGRAPH
        assert 3 * _WORDS_PER_PARAGRAPH * 6 > 500 * 1.25

    def test_higher_tier_is_wider(self):
        """Требование владельца: старший тариф шире, младший короче."""
        prev_words, prev_paragraphs = 0, 0
        for tier in ("free", "lite", "pro", "premium"):
            _, per_section, paragraphs, _ = self._plan(tier)
            assert per_section > prev_words, f"tier={tier}"
            assert paragraphs >= prev_paragraphs, f"tier={tier}"
            prev_words, prev_paragraphs = per_section, paragraphs

    def test_correction_applies_only_where_it_was_measured(self):
        """Поправка на перевыполнение — только для коротких секций.

        Замер 09.09.2026: при плане 33/50/75 слов на секцию модель писала
        54/70/92 (устойчивое +20), а начиная со 133 шла за планом. Применить
        поправку ко всем тарифам значило бы урезать те, где перебора нет.
        """
        from backend.auth.rate_limits import TIER_FLAGS
        from backend.interpretation.prompts import (
            _SHORT_SECTION_WORDS, _volume_plan, resolve_word_limit,
        )
        for tier in ("free", "lite", "pro", "premium"):
            req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, tier=tier)
            sections, per_section, _, _ = _volume_plan(req, resolve_word_limit(req))
            target = TIER_FLAGS[tier]["interpretation_word_limit"] / sections
            if target < _SHORT_SECTION_WORDS:
                assert per_section < target, f"{tier}: поправка не применилась"
            else:
                assert per_section == round(target), f"{tier}: поправка залезла не туда"

    def test_free_lands_in_the_owners_range(self):
        """Целевой факт задания: free 400–500 слов. Здесь — намерение промпта;
        фактическую длину живой генерации тест не проверяет и проверить не
        может (нужен реальный вызов модели)."""
        from backend.auth.rate_limits import TIER_FLAGS
        assert 400 <= TIER_FLAGS["free"]["interpretation_word_limit"] <= 500

    def test_section_count_comes_from_the_request(self):
        """Секций может быть не шесть: CRM просит свой набор. Захардкоженная
        шестёрка молча перекосила бы объём на каждую секцию."""
        from backend.interpretation.prompts import _volume_plan
        req = InterpretationRequest(
            natal_profile=SAMPLE_PROFILE, tier="pro", sections=["general", "career"],
        )
        sections, per_section, _, _ = _volume_plan(req, 2000)
        assert sections == 2
        assert per_section == 1000

    def test_prompt_states_both_numbers_and_they_agree(self):
        """В тексте промпта обязаны стоять и общий объём, и объём на секцию —
        иначе у модели снова остаётся один ориентир, и не тот."""
        from backend.auth.rate_limits import TIER_FLAGS
        for tier in ("free", "lite", "pro", "premium"):
            req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, tier=tier)
            prompt = build_system_prompt(req)
            _, per_section, paragraphs, _ = self._plan(tier)
            assert str(per_section) in prompt, f"tier={tier}: нет объёма на секцию"
            assert f"{paragraphs} абзац" in prompt, f"tier={tier}: нет числа абзацев"

    def test_single_paragraph_is_declined_correctly(self):
        """free получает один абзац — «1 абзацев» в промпте выглядело бы так
        же неряшливо, как в письме."""
        req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, tier="free")
        prompt = build_system_prompt(req)
        assert "1 абзац " in prompt
        assert "1 абзацев" not in prompt
        assert "1 абзаца" not in prompt


class TestMaxTokens:
    """max_tokens выводится из TIER_FLAGS.interpretation_word_limit, а не
    задаётся плоским числом на тир (было: free/lite получали одинаковые
    2000 при разных целевых объёмах 500/800 слов)."""

    def test_scales_with_tier_word_limit(self):
        from backend.interpretation.gpt4o import _calc_max_tokens
        from backend.auth.rate_limits import TIER_FLAGS

        prev = 0
        for tier in ("free", "lite", "pro", "premium"):
            req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, tier=tier)
            tokens = _calc_max_tokens(req)
            words = TIER_FLAGS[tier]["interpretation_word_limit"]
            # С запасом от 1 ток/слово (кириллица дороже) и больше words.
            assert tokens > words, f"tier={tier}"
            assert tokens > prev, f"tier={tier} должен получить больше токенов, чем предыдущий"
            prev = tokens

    def test_relative_headroom_is_the_same_for_every_tier(self):
        """Форма запаса важнее величины.

        Плоское слагаемое (+1500 токенов) давало тем меньший относительный
        запас, чем крупнее тариф: free 2.20×, premium 1.12×. То есть в потолок
        вероятнее всех упирался premium — тариф, которому в том же промпте
        говорили «НЕ МЕНЕЕ 5000 слов». А упереться значит получить
        finish_reason=length и ОТКАЗ вместо разбора, у самого дорогого тарифа.
        """
        from backend.auth.rate_limits import TIER_FLAGS
        from backend.interpretation.gpt4o import _calc_max_tokens

        ratios = []
        for tier in ("free", "lite", "pro", "premium"):
            req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, tier=tier)
            words = TIER_FLAGS[tier]["interpretation_word_limit"]
            ratios.append(_calc_max_tokens(req) / words)

        assert max(ratios) - min(ratios) < 0.01, (
            f"относительный запас разъехался по тарифам: {ratios}"
        )

    def test_old_additive_buffer_would_fail_this(self):
        """Проверка самой проверки: прежняя формула обязана давать разный
        запас — иначе тест выше ничего не стережёт."""
        from backend.auth.rate_limits import TIER_FLAGS
        old = [
            (int(TIER_FLAGS[t]["interpretation_word_limit"] * 2.5) + 1500)
            / TIER_FLAGS[t]["interpretation_word_limit"]
            for t in ("free", "lite", "pro", "premium")
        ]
        assert max(old) - min(old) > 1.0, old

    def test_ceiling_leaves_room_for_honest_overshoot(self):
        """Потолок страхует от разгона, а не режет нормальный текст: при
        реальных ~2.1 ток/слово любой тариф может перевыполнить объём заметно
        больше, чем в полтора раза, и остановиться сам."""
        from backend.auth.rate_limits import TIER_FLAGS
        from backend.interpretation.gpt4o import _calc_max_tokens

        for tier in ("free", "lite", "pro", "premium"):
            req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, tier=tier)
            words_before_cut = _calc_max_tokens(req) / 2.1
            target = TIER_FLAGS[tier]["interpretation_word_limit"]
            assert words_before_cut > target * 1.5, f"tier={tier}"

    def test_explicit_word_limit_overrides_tier(self):
        from backend.interpretation.gpt4o import _calc_max_tokens
        req = InterpretationRequest(natal_profile=SAMPLE_PROFILE, tier="free", word_limit=3000)
        tokens = _calc_max_tokens(req)
        assert tokens > 3000 * 2  # заметно больше, чем free-тарифный лимит дал бы


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
