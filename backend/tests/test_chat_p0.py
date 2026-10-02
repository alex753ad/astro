"""P0 чата по прогону вопросов 02.10.2026: даты пика, карта без времени,
память только своей карты, правила «Даты» и «Это приложение», род."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.ephemeris.calculator import PLANETS, _calc_planet_position, _datetime_to_jd
from backend.interpretation import rag_router
from backend.interpretation.gender_check import gendered_you
from backend.interpretation.rag import build_chart_summary, build_transits_block, chat_chart_data
from backend.tests.test_rag_chat import auth_headers, make_chart, make_pro_user
from backend.tests.test_rag_memory import _fold_client

_TODAY = date(2026, 10, 2)
_SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio",
          "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
_RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]


def _lon(planet: str, d: date) -> float:
    jd = _datetime_to_jd(datetime(d.year, d.month, d.day, 12))
    return _calc_planet_position(PLANETS[planet], round(jd, 6))[0]


def _natal(name: str, lon: float, house: int | None = 4) -> dict:
    lon %= 360
    return {"name": name, "longitude": lon, "sign": _SIGNS[int(lon // 30)],
            "degree_in_sign": lon % 30, "house": house, "retrograde": False}


def _exact_dates(block: str) -> list[date]:
    out = []
    for d, m, y in re.findall(r"Точный аспект: (\d+) (\w+) (\d{4})", block):
        out.append(date(int(y), _RU_MONTHS.index(m) + 1, int(d)))
    return out


def test_exact_date_is_the_real_peak_not_window_edge():
    """Натальный Меркурий стоит так, что Уран в квадрате к нему был точным за
    20 дней до «сегодня». Прежний код искал точный момент в ±5 сутках от
    сегодня и выдавал край окна; теперь дата — пик из чанка ленты."""
    peak = _TODAY - timedelta(days=20)
    chart = {"planets": [_natal("Mercury", _lon("Uranus", peak) + 90)], "houses": []}
    block = build_transits_block(chart, 5, _TODAY, "test-p0-peak")
    dates = _exact_dates(block)
    assert dates, block
    assert abs((dates[0] - peak).days) <= 1, (dates, peak)


def test_time_unknown_has_no_houses_asc_mc():
    stored = {
        "planets": [_natal("Sun", 130.0, house=3)],
        "ascendant": {"sign": "Gemini", "degree": 23.0},
        "midheaven": {"sign": "Aquarius", "degree": 22.0},
        "houses": [{"number": i + 1, "sign": "Aries", "degree": i * 30.0} for i in range(12)],
        "aspects": [{"planet1": "Sun", "planet2": "Ascendant", "aspect_type": "trine", "orb": 1}],
    }
    data = chat_chart_data(stored, time_unknown=True)
    summary = build_chart_summary(data, time_unknown=True)
    assert "Время рождения неизвестно" in summary
    for word in ("дом —", "3 дом", "**Асцендент:**", "**MC", "Управители домов", "None"):
        assert word not in summary, word
    assert data["aspects"] == []

    # С временем рождения — всё на месте.
    full = build_chart_summary(chat_chart_data(stored, time_unknown=False))
    assert "3 дом" in full and "**Асцендент:**" in full


def test_time_unknown_transits_have_no_house():
    peak = _TODAY - timedelta(days=20)
    chart = chat_chart_data({"planets": [_natal("Mercury", _lon("Uranus", peak) + 90, None)]}, True)
    block = build_transits_block(chart, 5, _TODAY, "test-p0-nohouse")
    assert "Транзитная планета" in block and "дом" not in block


def test_p0_rules_in_prompt():
    text = " ".join(rag_router._system_prompt("КАРТА", [], "", "ТРАНЗИТЫ").split())
    assert "## Даты" in text and "## Это приложение" in text
    assert "шаблоном по знаку Солнца" in text
    # Требование называть периоды без данных снято.
    assert "назови периоды" not in text
    assert "только если их даты есть в данных выше" in text


@pytest.mark.parametrize("text,caught", [
    ("Разреши сам себе отдых", True),
    ("ты сама себя загоняешь", True),
    ("стоит быть более основательным", True),
    ("Сатурн сам по себе не страшен", False),
    ("сделай это для себя", False),
])
def test_gender_detector_new_phrases(text, caught):
    assert bool(gendered_you(text)) is caught


@pytest.fixture
def _quiet():
    with patch.object(rag_router, "_classify_topic", AsyncMock(return_value="astrology")), \
         patch.object(rag_router, "retrieve", return_value=[]), \
         patch.object(rag_router, "_get_transits_block_cached", AsyncMock(return_value="")):
        yield


@pytest.mark.parametrize("own", [True, False])
def test_memory_only_for_own_chart(own, client: TestClient, db: Session, _quiet):
    """Своя карта — память читается и сворачивается; чужая — ни то, ни другое."""
    user = make_pro_user(db, email=f"p0mem{int(own)}@example.com")
    mine = make_chart(db, user.id)
    friend = make_chart(db, user.id)
    user.primary_chart_id = mine.id
    db.commit()
    target = mine if own else friend

    load = MagicMock(return_value="")
    fold = AsyncMock()
    with patch.object(rag_router, "_load_memory", load), \
         patch.object(rag_router, "_update_memory", fold), \
         patch.object(rag_router, "SessionLocal", lambda: db), \
         patch.object(rag_router.httpx, "AsyncClient", _fold_client("", {"answer": "Ответ."})):
        resp = client.post(f"/api/v1/chart/{target.id}/rag-chat",
                           json={"question": "Что ты обо мне знаешь?"}, headers=auth_headers(user))
    assert resp.status_code == 200
    assert load.called is own
    assert fold.await_count == (1 if own else 0)
