"""
Natal chart PDF generator — backend module.
Called by the /api/v1/chart/{chart_id}/pdf endpoint (и CRM, портал клиента).

Usage:
    from backend.natal_pdf import generate_pdf_bytes
    pdf_bytes = generate_pdf_bytes(chart_record, interpretation_text)

Оформление переделано 28.09.2026 по DESIGN_SYSTEM.md (светлая тема веба,
Literata — заголовки и проза, Golos Text — интерфейс и таблицы). Что было не
так и почему сделано именно так — в комментариях по месту; коротко:

* Всё по-русски: планеты, знаки, аспекты, система домов, дата («8 мая 2000»),
  место — сокращённо, как на карточке «Поделиться» (`share_router`).
* Страница БЕЛАЯ, а не сиреневатая: картинка колеса с сайта приходит на белом
  непрозрачном фоне и на цветной странице печаталась белым прямоугольником.
  Поля вокруг колеса обрезаются (`_trim_png`), колесо стоит сразу под шапкой —
  раньше оно было отцентровано по странице и сверху оставалось ~6 см пустоты.
* Звёзды и туманности убраны: ложились поверх текста таблиц (и расходуют
  краску при печати). «Космос, не эзотерика» — DESIGN_SYSTEM §1.
* Значки — отдельным шрифтом по цепочке: Noto Sans Symbols (как в
  приложении), затем DejaVu. В текстовых шрифтах астрозначков нет вовсе, а в
  DejaVu нет ⚹ и ⚻ — их раньше подменяли звёздочкой. Любой символ, которого
  нет в шрифте строки, уходит в первый шрифт цепочки, где он есть
  (`_runs`, `_para_markup`); тест проверяет, что квадратиков нет.
* Таблицы и разбор текут по страницам (`_Flow`): до правки список аспектов не
  переносился и при 20+ аспектах уходил за нижний край.
* «стр. N из M»: M известно только после раскладки, поэтому документ
  собирается дважды — первый проход считает страницы.
"""

import base64
import io
import math
import os as _os
import re
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from backend.ephemeris.ru_names import (
    ASPECT_RU, HOUSE_SYSTEM_RU, PLANET_RU, SIGN_IN_RU, SIGN_RU,
)

_FONTS_DIR = _os.path.join(_os.path.dirname(__file__), "assets", "fonts")

# ── Шрифты ─────────────────────────────────────────────────
# Literata и Golos Text урезаны до латиницы и кириллицы (≈40–60 КБ), лицензия
# OFL лежит рядом. Статические начертания, а не вариативные woff2 фронтенда:
# ReportLab вариативные шрифты не читает.
_TEXT_FONTS = {
    "Literata": "Literata-Regular.ttf",
    "Literata-SemiBold": "Literata-SemiBold.ttf",
    "Golos": "GolosText-Regular.ttf",
    "Golos-SemiBold": "GolosText-SemiBold.ttf",
}
# Цепочка для символов: первый шрифт, где символ есть. Noto — начертание
# значков как в приложении; DejaVu закрывает ☉ △ □ ℞, которых в Noto нет.
_SYMBOL_FONTS = {
    "SymNoto": "NotoSansSymbols-astro.ttf",
    "SymDejaVu": "DejaVuSans.ttf",
}

for _name, _file in {**_TEXT_FONTS, **_SYMBOL_FONTS}.items():
    pdfmetrics.registerFont(TTFont(_name, _os.path.join(_FONTS_DIR, _file)))
pdfmetrics.registerFontFamily("Literata", normal="Literata", bold="Literata-SemiBold",
                              italic="Literata", boldItalic="Literata-SemiBold")
pdfmetrics.registerFontFamily("Golos", normal="Golos", bold="Golos-SemiBold",
                              italic="Golos", boldItalic="Golos-SemiBold")

SERIF, SERIF_B = "Literata", "Literata-SemiBold"
SANS, SANS_B = "Golos", "Golos-SemiBold"
SYMBOL_CHAIN = tuple(_SYMBOL_FONTS)


def _has(font: str, ch: str) -> bool:
    return ord(ch) in pdfmetrics.getFont(font).face.charToGlyph


def _symbol_font(ch: str) -> str | None:
    return next((f for f in SYMBOL_CHAIN if _has(f, ch)), None)


def _runs(text: str, font: str) -> list[tuple[str, str]]:
    """Разбить строку на куски по шрифтам: символ, которого нет в `font`,
    уходит в первый шрифт цепочки, где он есть. Символа нет нигде — он
    выбрасывается (пустое место лучше квадратика)."""
    out: list[tuple[str, str]] = []
    for ch in text:
        f = font if (ch in " \n" or _has(font, ch)) else _symbol_font(ch)
        if f is None:
            continue
        if out and out[-1][0] == f:
            out[-1] = (f, out[-1][1] + ch)
        else:
            out.append((f, ch))
    return out


def _text_width(text: str, font: str, size: float) -> float:
    return sum(pdfmetrics.stringWidth(t, f, size) for f, t in _runs(text, font))


def _draw(c, x: float, y: float, text: str, font: str, size: float, color, align: str = "left"):
    """drawString с запасными шрифтами. align: left | center | right."""
    w = _text_width(text, font, size)
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    c.setFillColor(color)
    for f, t in _runs(text, font):
        c.setFont(f, size)
        c.drawString(x, y, t)
        x += pdfmetrics.stringWidth(t, f, size)
    return w


# ── Палитра: светлая тема веба (DESIGN_SYSTEM.md §2) ────────
W, H = A4
C_PAGE = colors.white                     # см. шапку: белый, а не --bg
C_TEXT = colors.HexColor("#1E1A2E")       # --text-primary
C_MUTED = colors.HexColor("#6B6885")      # --text-secondary
C_LINE = colors.HexColor("#EDE8F5")       # --border
C_ACCENT = colors.HexColor("#7C6CFF")     # --accent
C_ACCENT_BG = colors.HexColor("#F6F1FE")  # --accent-muted на белом (8 %)
# Семантические цвета светлой темы: гармоничные / нейтральные / напряжённые.
C_HARMONY = colors.HexColor("#059669")
C_NEUTRAL = colors.HexColor("#D97706")
C_TENSION = colors.HexColor("#DC2626")

MARGIN = 48
CONTENT_W = W - 2 * MARGIN
TOP = H - 56
BOTTOM = 64            # над подвалом

PLANET_GLYPHS = {
    "Sun": "☉", "Moon": "☽", "Mercury": "☿", "Venus": "♀", "Mars": "♂",
    "Jupiter": "♃", "Saturn": "♄", "Uranus": "♅", "Neptune": "♆", "Pluto": "♇",
    "North Node": "☊", "South Node": "☋",
}
SIGN_GLYPHS = {
    "Aries": "♈", "Taurus": "♉", "Gemini": "♊", "Cancer": "♋", "Leo": "♌", "Virgo": "♍",
    "Libra": "♎", "Scorpio": "♏", "Sagittarius": "♐", "Capricorn": "♑", "Aquarius": "♒", "Pisces": "♓",
}
ASPECT_SYMBOLS = {
    "conjunction": "☌", "opposition": "☍", "trine": "△", "square": "□",
    "sextile": "⚹", "quincunx": "⚻",
}
ASPECT_COLORS = {
    "conjunction": C_NEUTRAL, "trine": C_HARMONY, "sextile": C_HARMONY,
    "square": C_TENSION, "opposition": C_TENSION, "quincunx": C_MUTED,
}
# Группы таблицы аспектов: так её читает человек без подготовки — «что
# помогает, что напрягает», а не сплошной список по орбу.
ASPECT_GROUPS = (
    ("Соединения", ("conjunction",)),
    ("Гармоничные — трин и секстиль", ("trine", "sextile")),
    ("Напряжённые — квадрат и оппозиция", ("square", "opposition")),
)
# Узлы в эфемериде «ретроградны» всегда (средний узел) — метка ℞ у них шум.
_NODES = ("North Node", "South Node")
RETRO = "℞"

DISCLAIMER = "Документ носит ознакомительный характер. Астрология — язык символов и архетипов."

SECTION_TITLES = (
    ("general", "Общий портрет"),
    ("career", "Карьера и призвание"),
    ("relationships", "Отношения и партнёрство"),
    ("health", "Здоровье и энергия"),
    ("finance", "Финансы"),
    ("spirituality", "Внутренний рост"),
)


# ── Формат ─────────────────────────────────────────────────

def _field(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def dms(deg: float) -> str:
    """17.7 → «17°42′»."""
    deg = float(deg or 0) % 30
    d = int(deg)
    m = int(round((deg - d) * 60))
    if m == 60:
        d, m = d + 1, 0
    return f"{d}°{m:02d}′"


def planet_ru(name: str) -> str:
    return PLANET_RU.get(name, name)


def sign_ru(sign: str) -> str:
    return SIGN_RU.get(sign, sign)


def aspect_ru(kind: str) -> str:
    return ASPECT_RU.get(kind, {"quincunx": "квинконс"}.get(kind, kind))


def _birth_line(d: dict) -> str:
    """«8 мая 2000 · 13:25 · Рим, Италия» — как на карточке «Поделиться»."""
    from backend.share_router import ru_date, short_place  # тяжёлый модуль — лениво
    parts = [ru_date(d.get("birth_date"))]
    if d.get("birth_time") and not d.get("time_unknown"):
        parts.append(str(d["birth_time"])[:5])
    place = short_place(d.get("birth_place"))
    if place:
        parts.append(place)
    return " · ".join(p for p in parts if p)


# ── Картинка колеса ────────────────────────────────────────

def _trim_png(png_bytes: bytes) -> bytes:
    """Срезать белые поля вокруг колеса: экспорт с сайта квадратный, а колесо
    внутри меньше кадра — поля съедали место под шапкой."""
    try:
        from PIL import Image, ImageChops
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        box = ImageChops.difference(img, bg).convert("L").point(lambda v: 255 if v > 12 else 0).getbbox()
        if not box:
            return png_bytes
        pad = 6
        box = (max(0, box[0] - pad), max(0, box[1] - pad), min(img.width, box[2] + pad), min(img.height, box[3] + pad))
        out = io.BytesIO()
        img.crop(box).save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return png_bytes


def _draw_wheel_png(c, cx, top_y, max_size, wheel_png_b64: str) -> float | None:
    """Колесо сверху вниз от top_y, вписанное в max_size. Возвращает нижний
    край или None, если картинку прочитать нельзя."""
    try:
        png = _trim_png(base64.b64decode(wheel_png_b64))
        img = ImageReader(io.BytesIO(png))
        iw, ih = img.getSize()
        scale = max_size / max(iw, ih)
        w, h = iw * scale, ih * scale
        c.drawImage(img, cx - w / 2, top_y - h, width=w, height=h, mask="auto")
        return top_y - h
    except Exception:
        return None


def _wheel(c, cx, cy, r, planets=None, ascendant=None, aspects=None):
    """Колесо векторно — когда картинку с сайта не прислали (CRM, портал)."""
    asc_lon = float(_field(ascendant or {}, "longitude", 0.0) or 0.0)
    signs = list(SIGN_GLYPHS)
    elem = [colors.HexColor(x) for x in ("#E74C3C", "#27AE60", "#3498DB", "#2980B9")]  # --color-fire/earth/air/water
    for i, sign in enumerate(signs):
        start = 180 + (i * 30 - asc_lon)
        col = elem[i % 4]
        c.setFillColor(colors.Color(col.red, col.green, col.blue, alpha=0.14))
        c.setStrokeColor(C_LINE)
        c.setLineWidth(0.6)
        c.wedge(cx - r, cy - r, cx + r, cy + r, start, 30, fill=1, stroke=1)
        a = math.radians(start + 15)
        _draw(c, cx + r * 0.93 * math.cos(a), cy + r * 0.93 * math.sin(a) - 4, SIGN_GLYPHS[sign], SANS, 10, col, "center")
    c.setFillColor(C_PAGE)
    c.setStrokeColor(C_LINE)
    c.circle(cx, cy, r * 0.86, fill=1, stroke=1)

    pts = {}
    for pl in planets or []:
        lon = float(_field(pl, "longitude", 0) or 0)
        a = math.radians(180 + (lon - asc_lon))
        pts[_field(pl, "name", "")] = (lon, a)
    for asp in aspects or []:
        p1, p2 = _field(asp, "planet1", ""), _field(asp, "planet2", "")
        if p1 in pts and p2 in pts:
            col = ASPECT_COLORS.get(_field(asp, "aspect_type", ""), C_MUTED)
            c.setStrokeColor(colors.Color(col.red, col.green, col.blue, alpha=0.45))
            c.setLineWidth(0.6)
            (_, a1), (_, a2) = pts[p1], pts[p2]
            c.line(cx + r * 0.6 * math.cos(a1), cy + r * 0.6 * math.sin(a1),
                   cx + r * 0.6 * math.cos(a2), cy + r * 0.6 * math.sin(a2))
    for name, (_, a) in pts.items():
        _draw(c, cx + r * 0.74 * math.cos(a), cy + r * 0.74 * math.sin(a) - 5,
              PLANET_GLYPHS.get(name, "•"), SANS, 13, C_TEXT, "center")


# ── Разбор: секции из текста модели ─────────────────────────

def _parse_interp_string(text: str) -> dict:
    """Parse interpretation text — supports <section name="..."> tags and ### markdown headers."""
    tag_sections = re.findall(r'<section name="([^"]+)">(.*?)</section>', text, re.DOTALL)
    if tag_sections:
        return {name: content.strip() for name, content in tag_sections}

    section_map = {
        "общий": "general", "портрет": "general", "личност": "general", "personality": "general",
        "карьер": "career", "призван": "career", "career": "career",
        "отношен": "relationships", "партнёр": "relationships", "relationship": "relationships",
        "здоров": "health", "энерг": "health", "health": "health",
        "финанс": "finance", "материал": "finance", "finance": "finance",
        "духовн": "spirituality", "внутренн": "spirituality", "spiritual": "spirituality",
    }
    sections: dict = {}
    current_key = "general"
    current_lines: list = []
    for line in text.split("\n"):
        if line.startswith("### ") or line.startswith("## "):
            if current_lines:
                sections[current_key] = "\n\n".join(current_lines).strip()
            title_lower = re.sub(r'#+\s*', '', line).lower()
            current_key = next((v for k, v in section_map.items() if k in title_lower), "general")
            current_lines = []
        else:
            stripped = line.strip()
            if stripped:
                current_lines.append(stripped)
    if current_lines:
        prev = sections.get(current_key, "")
        sections[current_key] = (prev + "\n\n" + "\n\n".join(current_lines)).strip()
    if not sections:
        sections["general"] = text.strip()
    return sections


# «в Льве» → «во Льве»: так пишет модель. Правится здесь, при выводе в PDF:
# общей обработки текста модели перед показом у сайта и приложения нет —
# разбор уходит туда стримом по кускам, и слово может разорваться между ними.
_VO_RE = re.compile(r"(?<![а-яёА-ЯЁ])([вВ]) (?=Льв)")


def _para_markup(text: str, font: str) -> str:
    """Текст модели → разметка Paragraph: экранирование (& и < в тексте ломали
    разбор), **жирный** → <b>, символы вне шрифта — <font> из цепочки."""
    text = _VO_RE.sub(lambda m: m.group(1) + "о ", text or "")
    out = []
    for f, chunk in _runs(text, font):
        esc = _xml_escape(chunk)
        out.append(esc if f == font else f'<font name="{f}">{esc}</font>')
    s = "".join(out)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


# ── Раскладка ──────────────────────────────────────────────

class _Flow:
    """Страницы после обложки: курсор сверху вниз, новая страница, когда
    блок не влезает. Подвал рисуется при закрытии страницы."""

    def __init__(self, c, footer):
        self.c = c
        self.footer = footer
        self.y = TOP

    def need(self, h: float) -> bool:
        if self.y - h < BOTTOM:
            self.new_page()
            return True
        return False

    def new_page(self):
        self.footer(self.c)
        self.c.showPage()
        self.y = TOP

    def title(self, text: str, size: float = 18, gap_after: float = 14):
        self.need(size + gap_after + 60)   # заголовок не остаётся один внизу
        _draw(self.c, MARGIN, self.y - size, text, SERIF_B, size, C_TEXT)
        self.y -= size + gap_after

    def subtitle(self, text: str):
        self.need(40)
        self.y -= 6
        _draw(self.c, MARGIN, self.y - 11, text, SANS_B, 10.5, C_MUTED)
        self.y -= 11 + 8

    def rule(self):
        self.c.setStrokeColor(C_LINE)
        self.c.setLineWidth(0.6)
        self.c.line(MARGIN, self.y, W - MARGIN, self.y)


def _planets_table(fl: _Flow, planets):
    row = 20
    cols = (MARGIN, MARGIN + 150, MARGIN + 300, MARGIN + 400)  # планета · знак · градус · дом
    fl.need(row * 2)
    for x, head in zip(cols, ("Планета", "Знак", "Положение", "Дом")):
        _draw(fl.c, x, fl.y - 10, head, SANS, 8.5, C_MUTED)
    fl.y -= 16
    fl.rule()
    for pl in planets:
        if fl.need(row):
            fl.rule()
        name = _field(pl, "name", "")
        sign = _field(pl, "sign", "")
        base = fl.y - 14
        _draw(fl.c, cols[0], base, PLANET_GLYPHS.get(name, "•"), SANS, 11, C_ACCENT)
        _draw(fl.c, cols[0] + 18, base, planet_ru(name), SANS_B, 10, C_TEXT)
        _draw(fl.c, cols[1], base, SIGN_GLYPHS.get(sign, ""), SANS, 10.5, C_MUTED)
        _draw(fl.c, cols[1] + 16, base, sign_ru(sign), SANS, 10, C_TEXT)
        deg = _field(pl, "degree_in_sign", _field(pl, "degree", 0))
        pos = dms(deg)
        if _field(pl, "retrograde") and name not in _NODES:
            pos += f"  {RETRO}"
        _draw(fl.c, cols[2], base, pos, SANS, 10, C_TEXT)
        house = _field(pl, "house")
        if house:
            _draw(fl.c, cols[3], base, str(house), SANS, 10, C_TEXT)
        fl.y -= row
        fl.rule()
    fl.y -= 6
    has_retro = any(_field(p, "retrograde") and _field(p, "name") not in _NODES for p in planets)
    if has_retro:
        _draw(fl.c, MARGIN, fl.y - 10, f"{RETRO} — ретроградное движение", SANS, 8.5, C_MUTED)
        fl.y -= 16


def _houses_table(fl: _Flow, houses):
    row = 19
    half = (len(houses) + 1) // 2
    fl.need(row * half + 10)
    col_w = CONTENT_W / 2
    for i, h in enumerate(houses):
        col, r = divmod(i, half)
        x = MARGIN + col * col_w
        base = fl.y - 14 - r * row
        sign = _field(h, "sign", "")
        _draw(fl.c, x, base, f"{_field(h, 'number', i + 1)} дом", SANS, 10, C_MUTED)
        _draw(fl.c, x + 52, base, SIGN_GLYPHS.get(sign, ""), SANS, 10.5, C_MUTED)
        _draw(fl.c, x + 68, base, sign_ru(sign), SANS, 10, C_TEXT)
        _draw(fl.c, x + 160, base, dms(_field(h, "degree", 0)), SANS, 10, C_TEXT)
    fl.y -= half * row + 10


def _aspects_table(fl: _Flow, aspects):
    row = 19
    groups = []
    for title, kinds in ASPECT_GROUPS:
        items = [a for a in aspects if _field(a, "aspect_type") in kinds]
        if items:
            groups.append((title, sorted(items, key=lambda a: float(_field(a, "orb", 0) or 0))))
    rest = [a for a in aspects if _field(a, "aspect_type") not in {k for _, ks in ASPECT_GROUPS for k in ks}]
    if rest:
        groups.append(("Прочие", rest))
    x_p1, x_asp, x_p2, x_orb = MARGIN, MARGIN + 150, MARGIN + 290, W - MARGIN
    for title, items in groups:
        fl.subtitle(title)
        for a in items:
            if fl.need(row):
                fl.subtitle(f"{title} (продолжение)")
            base = fl.y - 13
            p1, p2 = _field(a, "planet1", ""), _field(a, "planet2", "")
            kind = _field(a, "aspect_type", "")
            col = ASPECT_COLORS.get(kind, C_MUTED)
            _draw(fl.c, x_p1, base, PLANET_GLYPHS.get(p1, "•"), SANS, 11, C_ACCENT)
            _draw(fl.c, x_p1 + 18, base, planet_ru(p1), SANS, 10, C_TEXT)
            _draw(fl.c, x_asp, base, ASPECT_SYMBOLS.get(kind, "·"), SANS, 11, col)
            _draw(fl.c, x_asp + 18, base, aspect_ru(kind), SANS, 10, col)
            _draw(fl.c, x_p2, base, PLANET_GLYPHS.get(p2, "•"), SANS, 11, C_ACCENT)
            _draw(fl.c, x_p2 + 18, base, planet_ru(p2), SANS, 10, C_TEXT)
            _draw(fl.c, x_orb, base, f"орб {dms(_field(a, 'orb', 0))}", SANS, 9, C_MUTED, "right")
            fl.y -= row
            fl.rule()


def _interpretation(fl: _Flow, interp):
    sections = _parse_interp_string(interp) if isinstance(interp, str) else (interp or {})
    body = ParagraphStyle("body", fontName=SERIF, fontSize=10.5, leading=16.5,
                          textColor=C_TEXT, alignment=TA_LEFT, spaceAfter=0)
    first = True
    for key, title in SECTION_TITLES:
        text = (sections.get(key) or "").strip()
        if not text:
            continue
        if first:
            _section_start(fl, 40 + 32 + 60)   # заголовок, первый подзаголовок, три строки
            fl.title("Разбор карты", 22, 18)
            first = False
        fl.need(90)   # подзаголовок и три строки текста
        _draw(fl.c, MARGIN, fl.y - 14, title, SERIF_B, 14, C_TEXT)
        fl.c.setStrokeColor(C_ACCENT)
        fl.c.setLineWidth(1.2)
        fl.c.line(MARGIN, fl.y - 20, MARGIN + 28, fl.y - 20)
        fl.y -= 32
        for raw in [p.strip() for p in text.split("\n\n") if p.strip()]:
            _flow_para(fl, _para_markup(raw, SERIF), body)
        fl.y -= 10


def _flow_para(fl: _Flow, markup: str, style, gap: float = 8, x: float = MARGIN, width: float = CONTENT_W):
    """Абзац с переносом через страницы."""
    para = Paragraph(markup, style)
    while para is not None:
        avail = fl.y - BOTTOM
        _, h = para.wrap(width, avail)
        if h <= avail:
            para.drawOn(fl.c, x, fl.y - h)
            fl.y -= h + gap
            return
        parts = para.split(width, avail)
        if len(parts) >= 2:
            _, h0 = parts[0].wrap(width, avail)
            parts[0].drawOn(fl.c, x, fl.y - h0)
            fl.new_page()
            para = parts[1]
        else:
            fl.new_page()   # не делится (одна строка) — на следующую


# ── Разделы Веги и Лиры (backend/pdf_reports/sections.py) ───

_BODY = ParagraphStyle("pbody", fontName=SERIF, fontSize=10.5, leading=16.5, textColor=C_TEXT, alignment=TA_LEFT)
_ITEM = ParagraphStyle("pitem", parent=_BODY, fontSize=10, leading=15)
_META = ParagraphStyle("pmeta", fontName=SANS, fontSize=9, leading=13, textColor=C_MUTED, alignment=TA_LEFT)
_BOLD = ParagraphStyle("pbold", fontName=SANS_B, fontSize=10, leading=14, textColor=C_TEXT, alignment=TA_LEFT)


def _entry_head(fl: _Flow, title: str, meta: str, color=C_ACCENT):
    """Заголовок пункта раздела: цветная черта, название, строка дат или орба."""
    fl.need(90)   # заголовок не остаётся без текста внизу страницы
    fl.c.setFillColor(color)
    fl.c.rect(MARGIN, fl.y - 16, 3, 14, fill=1, stroke=0)
    _draw(fl.c, MARGIN + 10, fl.y - 14, title, SERIF_B, 12.5, C_TEXT)
    fl.y -= 22
    if meta:
        _flow_para(fl, _para_markup(meta, SANS), _META, gap=4, x=MARGIN + 10, width=CONTENT_W - 10)
    fl.y -= 2


def _section_start(fl: _Flow, h: float):
    """Раздел продолжает страницу, а не начинает новую (решение владельца
    29.09.2026: при принудительном разрыве оставались страницы с двумя
    строками). `h` — сколько должно поместиться вместе с заголовком, чтобы
    он не остался внизу без текста; не помещается — всё на следующую."""
    if fl.y < TOP:
        fl.y -= 24   # отбивка от предыдущего раздела
    fl.need(h)


def _section_title(fl: _Flow, title: str, lead: str | None = None):
    # Заголовок, вводная в две строки и начало первого пункта (_entry_head).
    _section_start(fl, 34 + 40 + 90)
    fl.title(title, 22, 12)
    if lead:
        _flow_para(fl, _para_markup(lead, SANS), _META, gap=14)


def _aspects_section(fl: _Flow, items):
    _section_title(fl, "Главные аспекты",
                   "Самые точные сочетания планет в твоей карте — они звучат сильнее остальных.")
    for a in items:
        _entry_head(fl, a["title"], f"орб {dms(a.get('orb', 0))}", ASPECT_COLORS.get(a.get("kind"), C_ACCENT))
        _flow_para(fl, _para_markup(a["text"], SERIF), _BODY, gap=14)


def _transits_section(fl: _Flow, items, months: int):
    _section_title(fl, f"Главные транзиты: следующие {months} месяцев",
                   "Медленные планеты задевают точки твоей карты — это темы, которые идут неделями и месяцами.")
    for t in items:
        meta = t["when"] + (f" · точно: {t['exact']}" if t.get("exact") else "")
        _entry_head(fl, t["title"], meta, ASPECT_COLORS.get(t.get("kind"), C_ACCENT))
        if t.get("text"):
            _flow_para(fl, _para_markup(t["text"], SERIF), _BODY, gap=14)


def _longterm_section(fl: _Flow, items):
    _section_title(fl, "Долгосрочные периоды",
                   "Где сейчас идут медленные планеты — темы, которые длятся месяцы и годы.")
    for lt in items:
        _entry_head(fl, lt["title"], lt["when"])
        for line, style in ((lt.get("lead"), _META), (lt.get("theme"), _BOLD), (lt.get("subtitle"), _ITEM)):
            if line:
                _flow_para(fl, _para_markup(line, style.fontName), style, gap=6)
        for note in lt.get("notes") or []:
            _flow_para(fl, _para_markup(note, SERIF), _ITEM, gap=6)
        for g in lt.get("groups") or []:
            if g.get("heading"):
                fl.need(60)   # подзаголовок группы и две строки под ним
                _flow_para(fl, _para_markup(g["heading"], SANS_B), _BOLD, gap=4)
            for item in g.get("items") or []:
                _flow_para(fl, "•&nbsp;&nbsp;" + _para_markup(item, SERIF), _ITEM, gap=3,
                           x=MARGIN + 8, width=CONTENT_W - 8)
            fl.y -= 6
        fl.y -= 10


def _cover(c, d):
    y = H - 64
    name = (d.get("name") or "").strip()
    if name:
        _draw(c, W / 2, y, "НАТАЛЬНАЯ КАРТА", SANS_B, 9, C_MUTED, "center")
        y -= 34
        _draw(c, W / 2, y, name, SERIF_B, 26, C_TEXT, "center")
    else:
        # Имени у карты нет — заголовок ОДИН. До 28.09.2026 здесь стояло
        # «НАТАЛЬНАЯ КАРТА» и под ним имя-заглушка «Натальная карта».
        y -= 20
        _draw(c, W / 2, y, "Натальная карта", SERIF_B, 26, C_TEXT, "center")
    y -= 22
    _draw(c, W / 2, y, _birth_line(d), SANS, 11, C_MUTED, "center")
    y -= 20

    size = CONTENT_W * 0.92
    bottom = None
    if d.get("wheel_png"):
        bottom = _draw_wheel_png(c, W / 2, y, size, d["wheel_png"])
    if bottom is None:
        r = size / 2
        _wheel(c, W / 2, y - r, r, planets=d.get("planets", []),
               ascendant=d.get("ascendant"), aspects=d.get("aspects", []))
        bottom = y - size

    # «Большая тройка»: Солнце, Луна, Асцендент — с чего начинают читать карту.
    by_name = {_field(p, "name"): p for p in d.get("planets", [])}
    trio = []
    for key, label in (("Sun", "Солнце"), ("Moon", "Луна")):
        p = by_name.get(key)
        if p:
            trio.append((label, _field(p, "sign", ""), _field(p, "degree_in_sign", 0)))
    asc = d.get("ascendant")
    if asc and not d.get("time_unknown"):
        trio.append(("Асцендент", _field(asc, "sign", ""), _field(asc, "degree", 0)))
    y = bottom - 30
    if trio:
        col_w = CONTENT_W / len(trio)
        for i, (label, sign, deg) in enumerate(trio):
            cx = MARGIN + col_w * (i + 0.5)
            _draw(c, cx, y, label, SANS, 9, C_MUTED, "center")
            _draw(c, cx, y - 20, f"{SIGN_GLYPHS.get(sign, '')} {SIGN_IN_RU.get(sign, sign)}", SERIF_B, 13, C_TEXT, "center")
            _draw(c, cx, y - 36, dms(deg), SANS, 10, C_MUTED, "center")
        y -= 60
    hs = HOUSE_SYSTEM_RU.get(str(d.get("house_system") or "placidus").lower(), d.get("house_system"))
    if not d.get("time_unknown"):
        _draw(c, W / 2, y, f"Система домов: {hs}", SANS, 9, C_MUTED, "center")


def _render(c, d: dict, total: int | None) -> int:
    """Весь документ; возвращает число страниц. total=None — проход подсчёта."""
    page = [1]
    brand = d.get("astrologer_name") or "Aristea Timeline"

    def footer(cv, last=False):
        cv.setStrokeColor(C_LINE)
        cv.setLineWidth(0.6)
        cv.line(MARGIN, 40, W - MARGIN, 40)
        # Под брендом астролога адреса сервиса нет — это его документ.
        _draw(cv, MARGIN, 26, brand if d.get("astrologer_name") else f"{brand} · aristeatime.ru", SANS, 8.5, C_MUTED)
        if total:
            _draw(cv, W - MARGIN, 26, f"стр. {page[0]} из {total}", SANS, 8.5, C_MUTED, "right")
        if last:
            _draw(cv, W / 2, 48, DISCLAIMER, SANS, 8, C_MUTED, "center")
        page[0] += 1

    c.setFillColor(C_PAGE)
    _cover(c, d)
    footer(c)
    c.showPage()

    fl = _Flow(c, footer)
    fl.title("Планеты")
    _planets_table(fl, d.get("planets", []))
    if d.get("houses") and not d.get("time_unknown"):
        fl.y -= 10
        fl.title("Дома")
        _houses_table(fl, d["houses"])
    if d.get("aspects"):
        fl.y -= 10
        fl.title("Аспекты")
        _aspects_table(fl, d["aspects"])
    _interpretation(fl, d.get("interpretation"))
    extra = d.get("report")
    if extra is not None:
        if extra.aspects:
            _aspects_section(fl, extra.aspects)
        if extra.transits:
            _transits_section(fl, extra.transits, extra.transit_months)
        if extra.longterm:
            _longterm_section(fl, extra.longterm)
    footer(c, last=True)
    c.showPage()
    return page[0] - 1


def generate_pdf_bytes(chart, interpretation: str = "", astrologer_name: str | None = None,
                       wheel_png: str | None = None, report=None) -> bytes:
    """
    Generate a PDF and return it as bytes.

    Args:
        chart: NatalChart SQLAlchemy model instance (or any object/dict with the right fields)
        interpretation: Full interpretation text (markdown string) or dict of sections
        astrologer_name: Premium-only — astrologer display name shown in the footer
        wheel_png: base64 PNG колеса с сайта; нет — колесо рисуется векторно
    """
    if hasattr(chart, "__dict__") and not isinstance(chart, dict):
        ch = chart
        data = {
            "name": getattr(ch, "name", None) or "",
            "birth_date": ch.birth_date or "",
            "birth_time": ch.birth_time or "",
            "birth_place": ch.birth_place or "",
            "time_unknown": bool(getattr(ch, "time_unknown", False)),
            "house_system": ch.house_system or "placidus",
            "ascendant": ch.ascendant,
            "midheaven": ch.midheaven,
            "planets": ch.planets or [],
            "houses": ch.houses or [],
            "aspects": ch.aspects or [],
        }
    else:
        data = dict(chart)
    data["interpretation"] = data.get("interpretation") or interpretation
    data["astrologer_name"] = data.get("astrologer_name") or astrologer_name
    data["wheel_png"] = wheel_png
    # pdf_reports.sections.Report: аспекты, транзиты, долгосрочные периоды
    # Веги и Лиры; None — отчёт как у бесплатного.
    data["report"] = report

    # Проход 1 — только считаем страницы для «стр. N из M».
    total = _render(canvas.Canvas(io.BytesIO(), pagesize=A4), data, None)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    title_name = data.get("name") or _birth_line(data)
    c.setTitle(f"Натальная карта — {title_name}")
    c.setAuthor(astrologer_name or "Aristea Timeline")
    _render(c, data, total)
    c.save()
    return buf.getvalue()
