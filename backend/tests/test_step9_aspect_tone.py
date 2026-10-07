"""Шаг 9.5 (термины, под sky_event): характер аспекта «гармония / напряжение /
соединение» — промпты прогнозов, контекст чата, группы аспектов натального
PDF. Без флага — прежние тексты слово в слово."""
from datetime import date, datetime, timezone

import pytest

from backend import flags
from backend.models import FeatureFlag


@pytest.fixture(autouse=True)
def _fresh_flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


def _day(sky):
    from backend.forecast.facts import DayFacts
    return DayFacts(local_date=date(2026, 10, 7), trimmed=False, moon_sign="Овен",
                    aspects=[{"natal": "Venus", "aspect": "trine", "tone": "harmonious"}],
                    main={"transit": "Saturn", "natal": "Venus", "aspect": "square",
                          "tone": "tense", "slow": True}, sky=sky)


def test_daily_prompt_terms():
    from backend.forecast.prompts import build_daily_prompt
    old, new = build_daily_prompt(_day(False)), build_daily_prompt(_day(True))
    assert "— напряжённый акцент на теме" in old and "- Гармоничный акцент на теме:" in old
    assert "— напряжение, акцент на теме" in new and "- Гармония, акцент на теме:" in new


def test_lunation_prompt_terms():
    from backend.forecast.facts import LunationFacts
    from backend.forecast.prompts import build_lunation_prompt
    at = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)

    def p(sky):
        return build_lunation_prompt(LunationFacts(
            phase="new_moon", at_utc=at, at_local=at, sign="Весы", trimmed=False, house=None,
            aspects=[{"planet": "Saturn", "natal": "Venus", "tone": "strong"}], sky=sky))
    assert "усиливающий акцент" in p(False)
    assert "соединение, акцент" in p(True) and "усиливающий" not in p(True)


def test_forecast_cache_key_bumped_only_under_flag():
    from backend.forecast.router import _ver
    assert _ver(6, False) == "v6" and _ver(6, True) == "v6-sky2"


def test_pdf_fingerprint_only_under_flag():
    from backend.pdf_reports.sections import fingerprint
    d = date(2026, 10, 7)
    assert "g9" not in fingerprint("i1", "free", d, False)
    assert fingerprint("i1", "free", d, True).endswith("|g9")


@pytest.mark.parametrize("on", [False, True])
def test_natal_pdf_groups_real_path(db, monkeypatch, on):
    """Флаг — по ORM-карте, как в ручке PDF и в отчёте."""
    from backend import natal_pdf
    from backend.tests.test_rag_chat import make_chart, make_pro_user
    user = make_pro_user(db, email=f"pdf95{int(on)}@example.com")
    c = make_chart(db, user.id)
    c.aspects = [{"planet1": "Sun", "planet2": "Moon", "aspect_type": k, "orb": 1.0}
                 for k in ("conjunction", "trine", "square")]
    db.commit()
    if on:
        db.add(FeatureFlag(key="sky_event", mode="users", user_ids=[user.id]))
        db.commit()
        flags.reset_cache()
    titles = []
    monkeypatch.setattr(natal_pdf._Flow, "subtitle", lambda self, t: titles.append(t))
    natal_pdf.generate_pdf_bytes(c)
    want = (["Соединение", "Гармония — трин и секстиль", "Напряжение — квадрат и оппозиция"] if on else
            ["Соединения", "Гармоничные — трин и секстиль", "Напряжённые — квадрат и оппозиция"])
    assert titles[:3] == want
