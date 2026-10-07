"""Шаг 9.6 (термины, под sky_event): «Середина неба» и подпись ретроградности
в фактах чата. Без флага — прежние тексты слово в слово."""
from datetime import date

from backend.interpretation.rag import build_chart_summary, build_planner_block, chat_chart_data
from backend.transit import planner_engine

_NATAL = {
    "planets": [],
    "houses": [{"number": i + 1, "sign": "Овен", "degree": i * 30} for i in range(12)],
    "ascendant": {"sign": "Овен", "degree": 0},
    "midheaven": {"sign": "Козерог", "degree": 270},
}


def test_chat_mc_name():
    data = chat_chart_data({"planets": [], "houses": [], "aspects": [],
                            "ascendant": {"sign": "Aries", "degree": 1},
                            "midheaven": {"sign": "Capricorn", "degree": 2}}, time_unknown=False)
    assert "**MC (Середина Неба):**" in build_chart_summary(data)
    assert "**MC (Середина неба):**" in build_chart_summary(data, sky=True)


def test_chat_planner_retro_label(monkeypatch):
    real = planner_engine.build_planner

    def fake(**kw):
        p = real(**kw)
        p["upcoming"] = [{"date": "2026-07-28", "kind": "station", "planet": "uranus",
                          "planet_name": "Уран", "status": "start"}]
        return p
    monkeypatch.setattr(planner_engine, "build_planner", fake)
    args = (_NATAL, "premium", "Europe/Moscow", date(2026, 7, 24))
    assert "28.07 Уран: начало ретроградного движения" in build_planner_block(*args)
    assert "28.07 Уран: начало ретроградности" in build_planner_block(*args, sky=True)
