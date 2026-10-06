"""PDF по тарифам (29.09.2026): состав Веги и Лиры, разбор под тариф, сборка
в фоне, кеш и лимит.

Задание владельца, п. 6: PDF Веги и Лиры из фикстуры — нужные разделы есть,
нет английских названий, дат вида ГГГГ-ММ-ДД, «стр. N из M» верное.
Остальное — правила backend/pdf_reports: повторная выгрузка лимит не
списывает, сбой — failed без списания, одна сборка на человека.
"""
import asyncio
import re
from datetime import date, timedelta

import pytest
from reportlab.pdfgen.canvas import Canvas

from backend import natal_pdf
from backend.auth.rate_limits import get_monthly_usage
from backend.models import Interpretation, PdfReport
from backend.pdf_reports import build, sections
from backend.tests.test_chart_access import _make_chart
from backend.tests.test_natal_pdf_layout import INTERP, _chart
from backend.time_utils import utcnow

TODAY = date(2026, 10, 5)

ASPECTS = [{"title": "Солнце и Луна — трин", "kind": "trine", "orb": 0.4, "text": "Абзац про аспект. " * 12}] * 7
TRANSITS = [{"title": "Сатурн — квадрат к Солнцу", "kind": "square", "when": "с 3 марта по 18 июня 2027",
             "exact": "12 апреля 2027", "text": "Абзац про транзит. " * 10}] * 10
LONGTERM = [{"title": "Сатурн в 10 доме", "lead": "Сатурн — структура и ответственность.",
             "when": "до 18 июня 2028", "theme": "Карьера, статус, признание",
             "groups": [{"heading": "Что делать", "items": ["Пункт первый.", "Пункт второй."]}]}] * 3


@pytest.fixture
def drawn(monkeypatch):
    seen = []
    orig = Canvas.drawString

    def spy(self, x, y, text, *a, **kw):
        seen.append(text)
        return orig(self, x, y, text, *a, **kw)

    monkeypatch.setattr(Canvas, "drawString", spy)
    return seen


def _report(tier):
    plan = sections.plan_for(tier)
    return sections.Report(
        tier=tier, interpretation=INTERP, transit_months=plan.transit_months,
        aspects=ASPECTS[:plan.aspects], transits=TRANSITS[:plan.transits],
        longterm=LONGTERM if plan.longterm else [],
    )


@pytest.mark.parametrize("tier,must,must_not", [
    ("lite", ["Главные аспекты", "Главные транзиты: следующие 6 месяцев"], ["Долгосрочные периоды"]),
    ("pro", ["Главные аспекты", "Главные транзиты: следующие 12 месяцев", "Долгосрочные периоды"], []),
])
def test_vega_and_lyra_sections_russian_and_page_numbers(drawn, tier, must, must_not):
    pdf = natal_pdf.generate_pdf_bytes(_chart(), interpretation=INTERP, report=_report(tier))
    text = " ".join(drawn)
    for title in must:
        assert title in text, title
    for title in must_not:
        assert title not in text, title
    for eng in ("Sun", "Moon", "Taurus", "conjunction", "trine", "square"):
        assert not re.search(rf"\b{eng}\b", text), eng
    assert not re.search(r"\d{4}-\d{2}-\d{2}", text)
    total = len(re.findall(rb"/Type /Page\b", pdf))
    marks = [t for t in drawn if t.startswith("стр. ")]
    assert marks[-total:] == [f"стр. {i} из {total}" for i in range(1, total + 1)]


def test_free_pdf_as_before(drawn):
    natal_pdf.generate_pdf_bytes(_chart(), interpretation=INTERP, report=_report("free"))
    text = " ".join(drawn)
    assert "Главные аспекты" not in text and "Главные транзиты" not in text


def test_plans_match_owner_decision():
    assert sections.plan_for("lite") == sections.Plan(aspects=5, transit_months=6, transits=6)
    lyra = sections.plan_for("pro")
    assert (lyra.aspects, lyra.transit_months, lyra.longterm) == (7, 12, True)
    assert sections.plan_for("free") == sections.Plan()


# ── Разбор под тариф ────────────────────────────────────────

def _interp(db, chart, words, tier=None, minutes_ago=0):
    row = Interpretation(chart_id=chart.id, profile_hash="h", engine="deepseek",
                         content="слово " * words, tier=tier,
                         created_at=utcnow() - timedelta(minutes=minutes_ago))
    db.add(row)
    db.commit()
    return row


def test_depth_of_old_rows_by_word_count(db, user_free):
    chart = _make_chart(db, user_id=user_free.id)
    assert sections.interpretation_depth(_interp(db, chart, 450)) == "free"
    assert sections.interpretation_depth(_interp(db, chart, 700)) == "lite"      # ≥ 0,7 × 800
    assert sections.interpretation_depth(_interp(db, chart, 1900)) == "pro"      # ≥ 0,7 × 2500
    assert sections.interpretation_depth(_interp(db, chart, 100, tier="pro")) == "pro"


def test_pick_takes_newest_not_shorter_than_tier(db, user_free):
    chart = _make_chart(db, user_id=user_free.id)
    deep = _interp(db, chart, 2400, tier="pro", minutes_ago=10)
    _interp(db, chart, 800, tier="lite", minutes_ago=1)
    assert sections.pick_interpretation(db, chart.id, "pro").id == deep.id
    assert sections.pick_interpretation(db, chart.id, "lite").tier == "lite"
    assert sections.pick_interpretation(db, chart.id, "premium") is None


def test_pick_skips_interpretation_with_gendered_forms(db, user_free):
    """Разбор с «ты склонен» в PDF не идёт — пишется новый (решение 29.09.2026)."""
    chart = _make_chart(db, user_id=user_free.id)
    clean = _interp(db, chart, 800, tier="lite", minutes_ago=10)
    dirty = _interp(db, chart, 800, tier="lite", minutes_ago=1)
    dirty.content += " Ты склонен торопиться."
    db.commit()
    assert sections.pick_interpretation(db, chart.id, "lite").id == clean.id
    db.delete(clean)
    db.commit()
    assert sections.pick_interpretation(db, chart.id, "lite") is None


def test_vo_lve_in_pdf_text():
    from backend.natal_pdf import SERIF, _para_markup
    assert "Солнце во Льве" in _para_markup("Солнце в Льве", SERIF)
    assert "Во Льве" in _para_markup("В Льве Луна", SERIF)
    assert "Юпитер во Льве" in _para_markup("Юпитер во Льве", SERIF)


def test_numbered_answer_must_have_every_paragraph():
    assert sections._parse_numbered("### 1\nПервый.\n### 2\nВторой\nабзац.", 2) == ["Первый.", "Второй абзац."]
    with pytest.raises(sections.SectionError):
        sections._parse_numbered("### 1\nТолько один.", 2)


def test_prompts_ask_for_ty():
    from backend.interpretation.address import ADDRESS_RULE
    from backend.models import NatalChart
    chart = NatalChart(planets=[], aspects=[])
    assert ADDRESS_RULE in sections.aspects_prompt(chart, [])
    assert ADDRESS_RULE in sections.transits_prompt(chart, [], 6)


def test_main_transits_are_in_russian_words():
    planets = [{"name": n, "longitude": lon, "sign": "Aries"} for n, lon in
               (("Sun", 10.0), ("Moon", 100.0), ("Mercury", 200.0), ("Venus", 250.0), ("Mars", 330.0))]
    items = sections.main_transits(planets, TODAY, 12, 10)
    assert items and len(items) <= 10
    for t in items:
        assert re.fullmatch(r"[А-Яа-яё —]+", t["title"]), t["title"]
        assert not re.search(r"\d{4}-\d{2}-\d{2}", t["when"] + t["exact"])
    assert [t["kind"] for t in items]
    assert sections.transit_title("Saturn", "Mars", "conjunction") == "Сатурн — соединение с Марсом"
    assert sections.transit_title("Jupiter", "Venus", "square") == "Юпитер — квадрат к Венере"


_CROSSING = [{"name": n, "longitude": float(i * 67), "sign": "Aries"}
             for i, n in enumerate(("Sun", "Moon", "Mercury", "Venus", "Mars"))]


def test_transit_end_is_real_not_tier_horizon():
    """Транзит, идущий за горизонт Веги, кончается той же датой, что у Лиры
    (29.09.2026: раньше конец обрезался горизонтом тарифа)."""
    vega = {t["title"]: t["when"] for t in sections.main_transits(_CROSSING, date(2026, 9, 29), 6, 6)}
    lyra = {t["title"]: t["when"] for t in sections.main_transits(_CROSSING, date(2026, 9, 29), 12, 10)}
    assert vega["Плутон — трин к Луне"] == lyra["Плутон — трин к Луне"] == "с 6 февраля по 18 августа 2027"


def test_transit_without_end_in_sight(monkeypatch):
    monkeypatch.setattr(sections, "_real_ends", lambda natal, keys, horizon: {k: None for k in keys})
    whens = [t["when"] for t in sections.main_transits(_CROSSING, date(2026, 9, 29), 6, 6)]
    assert "с 6 февраля 2027, продолжается и после 31 марта 2027" in whens


# ── Сборка, кеш, лимит ─────────────────────────────────────

@pytest.fixture
def lite(db, user_free):
    user_free.tier = "lite"
    db.commit()
    return user_free


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr("backend.tasks.build_pdf_report.delay", lambda *a: calls.append(a))
    return calls


@pytest.fixture
def fake_sections(monkeypatch, tmp_path):
    monkeypatch.setattr(build, "pdf_dir", lambda: tmp_path)

    async def aspects(db, chart, tier):
        return ASPECTS[:5], 0.001

    async def transits(db, chart, tier, today, sky=False, tz=None):
        return TRANSITS[:6], 0.002

    monkeypatch.setattr(sections, "aspect_section", aspects)
    monkeypatch.setattr(sections, "transit_section", transits)
    monkeypatch.setattr(build, "_notify_ready", lambda db, r: None)


def test_build_then_same_report_again_costs_nothing(db, lite, queued, fake_sections):
    chart = _make_chart(db, user_id=lite.id)
    _interp(db, chart, 800, tier="lite")
    report, new = build.start(db, lite, chart, None)
    assert new and report.status == "queued" and len(queued) == 1

    asyncio.run(build._build(db, report, None))
    assert report.status == "ready" and report.charged
    assert get_monthly_usage(db, str(lite.id), "pdf") == 1
    assert open(report.file_path, "rb").read().startswith(b"%PDF")

    again, new = build.start(db, lite, chart, None)
    assert again.id == report.id and not new and len(queued) == 1
    assert get_monthly_usage(db, str(lite.id), "pdf") == 1


def test_one_build_per_person_at_a_time(db, lite, queued):
    a = _make_chart(db, user_id=lite.id)
    b = _make_chart(db, user_id=lite.id)
    first, _ = build.start(db, lite, a, None)
    second, new = build.start(db, lite, b, None)
    assert second.id == first.id and not new and len(queued) == 1


def test_stuck_build_does_not_lock_forever(db, lite, queued):
    chart = _make_chart(db, user_id=lite.id)
    first, _ = build.start(db, lite, chart, None)
    first.created_at = utcnow() - timedelta(minutes=10)
    db.commit()
    second, new = build.start(db, lite, chart, None)
    assert new and second.id != first.id
    db.refresh(first)
    assert first.status == "failed"


def test_failed_build_is_not_charged(db, lite, queued, fake_sections, monkeypatch):
    chart = _make_chart(db, user_id=lite.id)
    _interp(db, chart, 800, tier="lite")
    report, _ = build.start(db, lite, chart, None)

    async def broken(db, chart, tier):
        raise sections.SectionError("модель сбилась")

    monkeypatch.setattr(sections, "aspect_section", broken)
    monkeypatch.setattr("backend.database.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    with pytest.raises(sections.SectionError):
        build.run(report.id, None)
    db.refresh(report)
    assert report.status == "failed" and not report.charged
    assert get_monthly_usage(db, str(lite.id), "pdf") == 0


def test_new_interpretation_for_pdf_keeps_reading_quota(db, lite, queued, fake_sections, monkeypatch):
    """Разбора под тариф нет — PDF пишет новый с тарифом, квоту разборов не трогает."""
    chart = _make_chart(db, user_id=lite.id)
    _interp(db, chart, 300, tier="free")

    async def stream(self, request):
        assert request.tier == "lite"
        request.engine_used = "deepseek"
        yield "Разбор Веги."

    monkeypatch.setattr("backend.interpretation.router.InterpretationRouter.stream", stream)
    report, _ = build.start(db, lite, chart, None)
    asyncio.run(build._build(db, report, None))
    assert report.status == "ready"
    assert sections.pick_interpretation(db, chart.id, "lite").content == "Разбор Веги."
    assert get_monthly_usage(db, str(lite.id), "interpretation") == 0


def test_purge_removes_file_and_row(db, lite, queued, fake_sections):
    chart = _make_chart(db, user_id=lite.id)
    _interp(db, chart, 800, tier="lite")
    report, _ = build.start(db, lite, chart, None)
    asyncio.run(build._build(db, report, None))
    path = report.file_path
    report.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert build.purge_expired(db) == 1
    assert db.get(PdfReport, report.id) is None
    import os
    assert not os.path.exists(path)


def test_api_list_and_foreign_report(client, db, lite, queued, auth_headers_free):
    chart = _make_chart(db, user_id=lite.id)
    r = client.post(f"/api/v1/chart/{chart.id}/pdf-reports", json={}, headers=auth_headers_free)
    assert r.status_code == 202 and r.json()["status"] == "queued"
    lst = client.get(f"/api/v1/chart/{chart.id}/pdf-reports", headers=auth_headers_free).json()["reports"]
    assert [x["id"] for x in lst] == [r.json()["id"]]
    other = _make_chart(db, user_id=None)
    assert client.get(f"/api/v1/chart/{other.id}/pdf-reports", headers=auth_headers_free).status_code == 404


# POST /chart/{id}/pdf старых APK — test_old_apk_contract.py::test_sync_pdf_still_answers_with_bytes.
