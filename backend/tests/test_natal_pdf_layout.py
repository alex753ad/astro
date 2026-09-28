"""Оформление PDF натальной карты (28.09.2026).

Держит то, что было сломано в присланном владельцем файле:
* английские планеты/знаки/аспекты и дата «2000-05-08»;
* «Натальная карта» дважды на обложке;
* значки квадратиками: каждый символ рисуется шрифтом, в котором он есть;
* «стр. N из M» — M равно настоящему числу страниц, N идут подряд.

Тексты ловятся на `natal_pdf._draw` (через неё идёт всё, кроме прозы
разбора) и на проходе по canvas: шрифт, которым строка реально легла на
страницу, проверяется по его таблице символов.
"""
import re

import pytest
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from backend import natal_pdf

PLANETS = [
    {"name": "Sun", "longitude": 48.2, "sign": "Taurus", "degree_in_sign": 18.2, "house": 9, "retrograde": False},
    {"name": "Moon", "longitude": 107.1, "sign": "Cancer", "degree_in_sign": 17.1, "house": 11, "retrograde": False},
    {"name": "Mars", "longitude": 63.3, "sign": "Gemini", "degree_in_sign": 3.3, "house": 10, "retrograde": False},
    {"name": "Pluto", "longitude": 252.2, "sign": "Sagittarius", "degree_in_sign": 12.2, "house": 4, "retrograde": True},
    {"name": "North Node", "longitude": 118.3, "sign": "Cancer", "degree_in_sign": 28.3, "house": 11, "retrograde": True},
]
HOUSES = [{"number": i + 1, "sign": s, "degree": i * 30 + 5.0} for i, s in enumerate(
    ["Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn",
     "Aquarius", "Pisces", "Aries", "Taurus", "Gemini", "Cancer"])]
KINDS = ["conjunction", "sextile", "square", "trine", "opposition", "quincunx"]


def _chart(n_aspects=6, name=""):
    return {
        "name": name,
        "birth_date": "2000-05-08", "birth_time": "13:25",
        "birth_place": "Рим, Roma Capitale, Лацио, Италия",
        "house_system": "placidus",
        "planets": PLANETS, "houses": HOUSES,
        "aspects": [{"planet1": "Sun", "planet2": "Moon", "aspect_type": KINDS[i % 6], "orb": i * 0.3}
                    for i in range(n_aspects)],
        "ascendant": {"sign": "Leo", "degree": 29.0, "longitude": 149.0},
        "midheaven": {"sign": "Taurus", "degree": 22.7, "longitude": 52.7},
    }


INTERP = ("### Общий портрет\n\nТекст с **выделением**, знаками < & > и символами ✦ ☉ ♉ 🙂 внутри.\n\n"
          "### Карьера\n\n" + "Длинный абзац. " * 400)


@pytest.fixture
def drawn(monkeypatch):
    """Все строки, легшие на страницу через drawString, с их шрифтом."""
    seen = []
    orig = Canvas.drawString

    def spy(self, x, y, text, *a, **kw):
        seen.append((self._fontname, text))
        return orig(self, x, y, text, *a, **kw)

    monkeypatch.setattr(Canvas, "drawString", spy)
    return seen


def _pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type /Page\b", pdf))


def test_russian_names_date_and_single_title(drawn):
    natal_pdf.generate_pdf_bytes(_chart(), interpretation="")
    text = " ".join(t for _, t in drawn)
    for eng in ("Sun", "Moon", "Taurus", "Cancer", "Leo", "conjunction", "trine", "Placidus", "2000-05-08"):
        assert eng not in text, eng
    for ru in ("Солнце", "Телец", "во Льве", "соединение", "трин", "квинконс", "Плацидус", "8 мая 2000", "Рим, Италия"):
        assert ru in text, ru
    # Без имени заголовок один (раньше — «НАТАЛЬНАЯ КАРТА» и «Натальная карта»).
    cover = [t for _, t in drawn if "атальная карта".lower() in t.lower()]
    assert len(cover) == 2 and cover[0] == cover[1] == "Натальная карта"  # два прохода — по разу в каждом


def test_nodes_have_no_retro_mark_but_planets_do(monkeypatch):
    # Целыми строками (_draw), а не кусками drawString: «℞» ложится другим
    # шрифтом, чем градусы перед ним.
    lines = []
    orig = natal_pdf._draw
    monkeypatch.setattr(natal_pdf, "_draw", lambda c, x, y, text, *a, **kw: (lines.append(text), orig(c, x, y, text, *a, **kw))[1])
    natal_pdf.generate_pdf_bytes(_chart(), interpretation="")
    retro_rows = [t for t in lines if t.endswith("℞")]
    # «12°10′  ℞» у Плутона — есть; у узла (всегда «ретрограден») — нет.
    assert any(t.startswith("12°") for t in retro_rows)
    assert not any(t.startswith("28°") for t in retro_rows)


def test_every_symbol_is_drawn_with_a_font_that_has_it(drawn):
    natal_pdf.generate_pdf_bytes(_chart(), interpretation=INTERP)
    for font, text in drawn:
        face = pdfmetrics.getFont(font).face
        missing = [ch for ch in text if ch != " " and ord(ch) not in face.charToGlyph]
        assert not missing, f"{font}: {missing} в «{text}»"
    used = {f for f, _ in drawn}
    assert {"SymNoto", "SymDejaVu"} <= used, "значки должны идти символьными шрифтами"


def test_prose_markup_routes_symbols_and_escapes():
    m = natal_pdf._para_markup("Солнце ☉ и ⚹, **важно** < & >", natal_pdf.SERIF)
    assert '<font name="SymDejaVu">☉</font>' in m
    assert '<font name="SymNoto">⚹</font>' in m
    assert "<b>важно</b>" in m and "&lt; &amp; &gt;" in m
    # Символа нет ни в одном шрифте — он выбрасывается, а не рисуется квадратиком.
    assert "🙂" not in natal_pdf._para_markup("улыбка 🙂", natal_pdf.SERIF)


def test_all_astro_glyphs_are_covered():
    glyphs = (list(natal_pdf.PLANET_GLYPHS.values()) + list(natal_pdf.SIGN_GLYPHS.values())
              + list(natal_pdf.ASPECT_SYMBOLS.values()) + [natal_pdf.RETRO])
    assert [g for g in glyphs if natal_pdf._symbol_font(g) is None] == []


@pytest.mark.parametrize("n_aspects, interp", [(3, ""), (60, ""), (6, INTERP)])
def test_page_numbers_say_the_true_total(drawn, n_aspects, interp):
    pdf = natal_pdf.generate_pdf_bytes(_chart(n_aspects), interpretation=interp)
    total = _pages(pdf)
    marks = [t for _, t in drawn if t.startswith("стр. ")]
    # Первый проход (подсчёт) номеров не пишет — все метки из второго.
    assert marks == [f"стр. {i} из {total}" for i in range(1, total + 1)]
    if n_aspects == 60 or interp:
        assert total >= 3   # таблица и разбор действительно переносятся


def test_astrologer_brand_in_footer_without_service_address(drawn):
    natal_pdf.generate_pdf_bytes(_chart(name="Анна"), interpretation="", astrologer_name="Мария Звёздная")
    footers = [t for _, t in drawn if "Мария Звёздная" in t]
    assert footers and all("aristeatime.ru" not in t for t in footers)
    assert "Анна" in [t for _, t in drawn]
