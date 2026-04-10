"""
Natal chart PDF generator — backend module.
Called by the /api/v1/chart/{chart_id}/pdf endpoint.

Usage:
    from backend.natal_pdf import generate_pdf_bytes
    pdf_bytes = generate_pdf_bytes(chart_record, interpretation_text)
"""

import io
import math
import random

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os as _os

def _register_fonts():
    """Register Unicode fonts for Cyrillic support."""
    # Try Windows fonts first, then fallback options
    font_paths = [
        # Windows
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
        # Linux
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for regular, bold in font_paths:
        if _os.path.exists(regular):
            try:
                pdfmetrics.registerFont(TTFont("MainFont", regular))
                if _os.path.exists(bold):
                    pdfmetrics.registerFont(TTFont("MainFont-Bold", bold))
                else:
                    pdfmetrics.registerFont(TTFont("MainFont-Bold", regular))
                return "MainFont"
            except Exception:
                continue
    return None  # Fall back to Helvetica (no Cyrillic)

_FONT_NAME = _register_fonts() or "Helvetica"
_FONT_BOLD = (_FONT_NAME + "-Bold") if _FONT_NAME != "Helvetica" else "Helvetica-Bold"


W, H = A4

C_BG      = colors.HexColor("#0C0D14")
C_GOLD    = colors.HexColor("#C9A84C")
C_GOLD2   = colors.HexColor("#E8CC7A")
C_SILVER  = colors.HexColor("#A8B0C0")
C_ACCENT  = colors.HexColor("#7B5EA7")
C_TEXT    = colors.HexColor("#DDD5C0")
C_MUTED   = colors.HexColor("#7A7060")
C_BORDER  = colors.HexColor("#2A2438")
C_STAR    = colors.HexColor("#F0E8D0")
C_RETRO   = colors.HexColor("#CC6655")
C_TRINE   = colors.HexColor("#4A9060")
C_SQUARE  = colors.HexColor("#CC5544")
C_SEXTILE = colors.HexColor("#4A7090")
C_CONJ    = colors.HexColor("#C9A84C")

PLANET_GLYPHS = {
    "Sun":"☉","Moon":"☽","Mercury":"☿","Venus":"♀","Mars":"♂",
    "Jupiter":"♃","Saturn":"♄","Uranus":"♅","Neptune":"♆","Pluto":"♇",
    "Солнце":"☉","Луна":"☽","Меркурий":"☿","Венера":"♀","Марс":"♂",
    "Юпитер":"♃","Сатурн":"♄","Уран":"♅","Нептун":"♆","Плутон":"♇",
}
SIGN_GLYPHS = {
    "Aries":"♈","Taurus":"♉","Gemini":"♊","Cancer":"♋","Leo":"♌","Virgo":"♍",
    "Libra":"♎","Scorpio":"♏","Sagittarius":"♐","Capricorn":"♑","Aquarius":"♒","Pisces":"♓",
    "Овен":"♈","Телец":"♉","Близнецы":"♊","Рак":"♋","Лев":"♌","Дева":"♍",
    "Весы":"♎","Скорпион":"♏","Стрелец":"♐","Козерог":"♑","Водолей":"♒","Рыбы":"♓",
}
ASPECT_SYMBOLS = {
    "conjunction":"☌","opposition":"☍","trine":"△","square":"□","sextile":"⚹","quincunx":"⚻",
    "соединение":"☌","оппозиция":"☍","тригон":"△","квадрат":"□","секстиль":"⚹","квинконс":"⚻",
}
ASPECT_COLORS = {
    "conjunction":C_CONJ,"trine":C_TRINE,"sextile":C_SEXTILE,
    "square":C_SQUARE,"opposition":C_SQUARE,"quincunx":C_MUTED,
    "соединение":C_CONJ,"тригон":C_TRINE,"секстиль":C_SEXTILE,
    "квадрат":C_SQUARE,"оппозиция":C_SQUARE,"квинконс":C_MUTED,
}


# ── Drawing helpers ────────────────────────────────────────

def _stars(c, seed, count):
    rng = random.Random(seed)
    for _ in range(count):
        x = rng.uniform(0, W); y = rng.uniform(0, H)
        size = rng.choice([0.4, 0.6, 0.8, 1.0, 1.4, 1.8])
        alpha = rng.uniform(0.15, 0.75)
        col = colors.Color(C_STAR.red, C_STAR.green, C_STAR.blue, alpha=alpha)
        c.setFillColor(col); c.setStrokeColor(col)
        if size >= 1.4:
            arm = size * 2.5; c.setLineWidth(0.4)
            c.line(x-arm, y, x+arm, y); c.line(x, y-arm, x, y+arm)
        c.circle(x, y, size, fill=1, stroke=0)


def _nebula(c, cx, cy, rx, ry, col, alpha=0.04):
    for i in range(6, 0, -1):
        f = i / 6
        g = colors.Color(col.red, col.green, col.blue, alpha=alpha * f * 0.7)
        c.setFillColor(g)
        c.ellipse(cx-rx*f, cy-ry*f, cx+rx*f, cy+ry*f, fill=1, stroke=0)


def _border(c, x, y, w, h, lw=0.6):
    gap = 3
    c.setStrokeColor(C_GOLD); c.setLineWidth(lw)
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.setLineWidth(lw*0.5)
    c.setStrokeColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=0.4))
    c.rect(x+gap, y+gap, w-gap*2, h-gap*2, fill=0, stroke=1)


def _corner(c, cx, cy, size):
    c.setFillColor(C_GOLD); c.setLineWidth(0.4)
    for angle in range(0, 360, 90):
        rad = math.radians(angle + 45)
        ex = cx + math.cos(rad)*size; ey = cy + math.sin(rad)*size
        c.setStrokeColor(C_GOLD); c.line(cx, cy, ex, ey)
        c.circle(ex, ey, size*0.15, fill=1, stroke=0)
    c.circle(cx, cy, size*0.2, fill=1, stroke=0)


def _divider(c, x, y, width, alpha=1.0):
    col = colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=alpha)
    mid = x + width/2
    c.setStrokeColor(col); c.setLineWidth(0.5)
    c.line(x, y, mid-6, y); c.line(mid+6, y, x+width, y)
    c.setFillColor(col)
    p = c.beginPath()
    p.moveTo(mid, y+3); p.lineTo(mid+3, y); p.lineTo(mid, y-3); p.lineTo(mid-3, y); p.close()
    c.drawPath(p, fill=1, stroke=0)
    for dx in [-10, 10]: c.circle(mid+dx, y, 1, fill=1, stroke=0)


def _section_header(c, x, y, title, width):
    c.setFillColor(colors.Color(C_ACCENT.red, C_ACCENT.green, C_ACCENT.blue, alpha=0.12))
    c.roundRect(x, y-4, width, 16, 4, fill=1, stroke=0)
    c.setFillColor(C_GOLD); c.rect(x, y-4, 2.5, 16, fill=1, stroke=0)
    c.setFillColor(C_GOLD2); c.setFont(_FONT_BOLD, 9)
    c.drawString(x+8, y+2, title.upper())


def _page_num(c, n, total):
    c.setFillColor(C_MUTED); c.setFont(_FONT_NAME, 7)
    c.drawCentredString(W/2, 14*mm, f"— {n} / {total} —")


def _wheel(c, cx, cy, r):
    signs = list(SIGN_GLYPHS.keys())[:12]
    seg_colors = [
        colors.HexColor("#8B3A3A"), colors.HexColor("#5C7A3A"),
        colors.HexColor("#3A5C8B"), colors.HexColor("#7A5C3A"),
    ] * 3
    for i in range(12):
        start = 90 - i*30
        seg = colors.Color(seg_colors[i].red, seg_colors[i].green, seg_colors[i].blue, alpha=0.13)
        c.setFillColor(seg)
        c.setStrokeColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=0.3))
        c.setLineWidth(0.4)
        c.wedge(cx-r, cy-r, cx+r, cy+r, start-30, 30, fill=1, stroke=1)
        mid_a = math.radians(start - 15)
        gx = cx + r*0.78*math.cos(mid_a); gy = cy + r*0.78*math.sin(mid_a)
        c.setFillColor(C_GOLD2); c.setFont(_FONT_NAME, 7)
        c.drawCentredString(gx, gy-2.5, list(SIGN_GLYPHS.values())[i])
    for radius, alpha in [(r*0.65, 0.25), (r*0.9, 0.4), (r, 0.6)]:
        c.setStrokeColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=alpha))
        c.setLineWidth(0.5 if radius < r else 0.8)
        c.circle(cx, cy, radius, fill=0, stroke=1)
    _nebula(c, cx, cy, r*0.5, r*0.5, C_ACCENT, alpha=0.08)
    c.setFillColor(colors.Color(C_ACCENT.red, C_ACCENT.green, C_ACCENT.blue, alpha=0.15))
    c.circle(cx, cy, r*0.62, fill=1, stroke=0)


def _bg(c):
    c.setFillColor(C_BG); c.rect(0, 0, W, H, fill=1, stroke=0)


# ── Pages ─────────────────────────────────────────────────

def _page_cover(c, d):
    c.saveState()
    _bg(c)
    _nebula(c, W*0.2, H*0.8, 160, 100, C_ACCENT, alpha=0.06)
    _nebula(c, W*0.8, H*0.2, 140, 90, colors.HexColor("#3A2060"), alpha=0.07)
    _nebula(c, W*0.5, H*0.5, 200, 200, C_ACCENT, alpha=0.03)
    _stars(c, 7, 220)

    m = 12*mm
    _border(c, m, m, W-2*m, H-2*m, lw=0.7)
    o = m+4
    for cx2, cy2 in [(o,o),(W-o,o),(o,H-o),(W-o,H-o)]: _corner(c, cx2, cy2, 8)

    wcx, wcy, wr = W/2, H*0.62, 88
    _wheel(c, wcx, wcy, wr)

    for i, pl in enumerate(d["planets"][:8]):
        angle = math.radians(90 - i*45)
        px = wcx + wr*1.22*math.cos(angle); py = wcy + wr*1.22*math.sin(angle)
        c.setFillColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=0.12))
        c.circle(px, py, 9, fill=1, stroke=0)
        c.setFillColor(C_GOLD2); c.setFont(_FONT_NAME, 12)
        c.drawCentredString(px, py-4, PLANET_GLYPHS.get(pl["name"], "★"))

    ty = H*0.915
    c.setFillColor(C_GOLD2); c.setFont(_FONT_BOLD, 9)
    c.drawCentredString(W/2, ty, "✦  НАТАЛЬНАЯ КАРТА  ✦")
    _divider(c, W*0.2, ty-8, W*0.6)

    c.setFillColor(C_TEXT); c.setFont(_FONT_BOLD, 22)
    c.drawCentredString(W/2, ty-30, d["name"])

    c.setFillColor(C_MUTED); c.setFont(_FONT_NAME, 8)
    parts = [d["birth_date"]]
    if d.get("birth_time"): parts.append(d["birth_time"])
    parts.append(d["birth_place"])
    c.drawCentredString(W/2, ty-48, "  ·  ".join(parts))

    by = wcy - wr - 18
    for label, key, bx in [("ASC","ascendant",W/2-55),("MC","midheaven",W/2+10)]:
        val = d.get(key) or {}
        sign = val.get("sign",""); deg = val.get("degree",0)
        g = SIGN_GLYPHS.get(sign,"")
        c.setFillColor(colors.Color(C_ACCENT.red, C_ACCENT.green, C_ACCENT.blue, alpha=0.2))
        c.roundRect(bx, by-6, 45, 18, 4, fill=1, stroke=0)
        c.setStrokeColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=0.4))
        c.setLineWidth(0.4); c.roundRect(bx, by-6, 45, 18, 4, fill=0, stroke=1)
        c.setFillColor(C_GOLD); c.setFont(_FONT_BOLD, 7)
        c.drawString(bx+4, by+5, label)
        c.setFillColor(C_TEXT); c.setFont(_FONT_NAME, 7.5)
        c.drawString(bx+18, by+5, f"{g} {sign} {deg:.1f}")

    _divider(c, W*0.25, by-16, W*0.5)
    c.setFillColor(C_MUTED); c.setFont(_FONT_NAME, 7.5)
    hs = d.get("house_system","Placidus").capitalize()
    c.drawCentredString(W/2, by-28, f"Система домов: {hs}  ·  Astro SPA")

    c.restoreState(); _page_num(c, 1, 3)


def _page_data(c, d):
    c.saveState()
    _bg(c)
    _nebula(c, W*0.1, H*0.9, 120, 80, C_ACCENT, alpha=0.04)
    _nebula(c, W*0.9, H*0.1, 100, 70, C_ACCENT, alpha=0.04)
    _stars(c, 13, 120)

    m = 12*mm
    _border(c, m, m, W-2*m, H-2*m, lw=0.6)
    o = m+4
    for cx2, cy2 in [(o,o),(W-o,o),(o,H-o),(W-o,H-o)]: _corner(c, cx2, cy2, 6)

    c.setFillColor(C_GOLD2); c.setFont(_FONT_BOLD, 10)
    c.drawCentredString(W/2, H-m-10, "ПЛАНЕТЫ · ДОМА · АСПЕКТЫ")
    _divider(c, m+10, H-m-18, W-2*m-20)

    cw = (W-2*m-16)/2 - 6
    cl = m+8; cr = W/2+4

    # Planets
    py = H-m-34
    _section_header(c, cl, py, "Положение планет", cw); py -= 22
    for pl in d["planets"]:
        br = 7; bx = cl
        c.setFillColor(colors.Color(C_ACCENT.red, C_ACCENT.green, C_ACCENT.blue, alpha=0.18))
        c.circle(bx+br, py, br, fill=1, stroke=0)
        c.setStrokeColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=0.5))
        c.setLineWidth(0.5); c.circle(bx+br, py, br, fill=0, stroke=1)
        c.setFillColor(C_GOLD2); c.setFont(_FONT_BOLD, 9)
        c.drawCentredString(bx+br, py-3, PLANET_GLYPHS.get(pl["name"],"★"))
        c.setFillColor(C_TEXT); c.setFont(_FONT_BOLD, 8)
        c.drawString(bx+br*2+5, py-3, pl["name"])
        sg = SIGN_GLYPHS.get(pl["sign"],"")
        c.setFillColor(C_GOLD); c.setFont(_FONT_NAME, 8)
        c.drawString(bx+95, py-3, sg)
        c.setFillColor(C_TEXT)
        deg = pl.get("degree_in_sign", pl.get("degree", 0))
        c.drawString(bx+105, py-3, f"{pl['sign']}  {deg:.1f}")
        c.setFillColor(C_MUTED); c.setFont(_FONT_NAME, 7.5)
        if pl.get("house"): c.drawString(bx+195, py-3, f"Дом {pl['house']}")
        if pl.get("retrograde"):
            c.setFillColor(C_RETRO); c.setFont(_FONT_BOLD, 7)
            c.drawString(bx+235, py-3, "R")
        c.setStrokeColor(colors.Color(C_BORDER.red, C_BORDER.green, C_BORDER.blue, alpha=0.6))
        c.setLineWidth(0.3); c.line(cl, py-9, cl+cw, py-9); py -= 20

    # Houses
    py -= 6
    _section_header(c, cl, py, "Дома", cw); py -= 16
    houses = d.get("houses", []); half = len(houses)//2
    for i in range(half):
        h1 = houses[i]; h2 = houses[i+half]
        c.setFillColor(C_MUTED); c.setFont(_FONT_NAME, 7.5)
        c.drawString(cl, py, f"Дом {h1['number']:2d}")
        c.setFillColor(C_GOLD); c.drawString(cl+34, py, SIGN_GLYPHS.get(h1["sign"],""))
        c.setFillColor(C_TEXT); c.drawString(cl+44, py, h1["sign"])
        c.setFillColor(C_MUTED); c.drawString(cl+cw/2+4, py, f"Дом {h2['number']:2d}")
        c.setFillColor(C_GOLD); c.drawString(cl+cw/2+38, py, SIGN_GLYPHS.get(h2["sign"],""))
        c.setFillColor(C_TEXT); c.drawString(cl+cw/2+48, py, h2["sign"]); py -= 13

    # Aspects
    ay = H-m-34
    _section_header(c, cr, ay, "Аспекты", cw); ay -= 22
    for asp in d.get("aspects", []):
        p1 = asp.get("planet1",""); p2 = asp.get("planet2","")
        at = asp.get("aspect_type", asp.get("aspect",""))
        orb = asp.get("orb", 0)
        sym = ASPECT_SYMBOLS.get(at,"·")
        acol = ASPECT_COLORS.get(at, C_MUTED)
        c.setFillColor(C_GOLD2); c.setFont(_FONT_NAME, 8.5)
        c.drawString(cr, ay, PLANET_GLYPHS.get(p1,"★"))
        c.setFillColor(C_TEXT); c.setFont(_FONT_NAME, 7.5)
        c.drawString(cr+11, ay, p1)
        c.setFillColor(acol); c.setFont(_FONT_BOLD, 9)
        c.drawCentredString(cr+88, ay, sym)
        c.setFillColor(C_SILVER); c.setFont(_FONT_NAME, 7)
        c.drawCentredString(cr+88, ay-9, at)
        c.setFillColor(C_GOLD2); c.setFont(_FONT_NAME, 8.5)
        c.drawString(cr+103, ay, PLANET_GLYPHS.get(p2,"★"))
        c.setFillColor(C_TEXT); c.setFont(_FONT_NAME, 7.5)
        c.drawString(cr+114, ay, p2)
        c.setFillColor(C_MUTED); c.setFont(_FONT_NAME, 7)
        c.drawRightString(cr+175, ay, f"орб {orb:.1f}")
        c.setStrokeColor(colors.Color(C_BORDER.red, C_BORDER.green, C_BORDER.blue, alpha=0.5))
        c.setLineWidth(0.3); c.line(cr, ay-13, cr+cw, ay-13); ay -= 26

    # Legend
    ay -= 8
    _section_header(c, cr, ay, "Условные обозначения", cw); ay -= 16
    legend = [
        ("соединение ☌", C_CONJ), ("тригон △", C_TRINE),
        ("секстиль ⚹", C_SEXTILE), ("квадрат □", C_SQUARE),
        ("оппозиция ☍", C_SQUARE), ("R — ретроградность", C_RETRO),
    ]
    for i, (label, col) in enumerate(legend):
        rx = cr + (i%2)*(cw/2+2); ry = ay - (i//2)*13
        c.setFillColor(col); c.circle(rx+3, ry+2, 2.5, fill=1, stroke=0)
        c.setFillColor(C_TEXT); c.setFont(_FONT_NAME, 7)
        c.drawString(rx+9, ry-1, label)

    c.restoreState(); _page_num(c, 2, 3)


def _page_interp(c, d):
    c.saveState()
    _bg(c)
    _nebula(c, W*0.5, H*0.5, 250, 300, C_ACCENT, alpha=0.03)
    _stars(c, 99, 100)

    m = 12*mm
    _border(c, m, m, W-2*m, H-2*m, lw=0.6)
    o = m+4
    for cx2, cy2 in [(o,o),(W-o,o),(o,H-o),(W-o,H-o)]: _corner(c, cx2, cy2, 6)

    c.setFillColor(C_GOLD2); c.setFont(_FONT_BOLD, 10)
    c.drawCentredString(W/2, H-m-10, "ИНТЕРПРЕТАЦИЯ НАТАЛЬНОЙ КАРТЫ")
    _divider(c, m+10, H-m-18, W-2*m-20)

    style = ParagraphStyle(
        "body", fontName=_FONT_NAME, fontSize=8, leading=13,
        textColor=C_TEXT, alignment=TA_JUSTIFY, spaceAfter=4,
    )

    cx = m+10; cw = W-2*m-20; iy = H-m-34

    interp = d.get("interpretation", {})

    # If interpretation is a plain string (full text), split by ### sections
    if isinstance(interp, str):
        sections = _parse_interp_string(interp)
    else:
        sections = interp

    section_titles = {
        "general":       "✦  Общий портрет личности",
        "career":        "✦  Карьера и призвание",
        "relationships": "✦  Отношения и партнёрство",
        "health":        "✦  Здоровье и энергия",
        "finance":       "✦  Финансы",
        "spirituality":  "✦  Духовное развитие",
    }

    for key, title in section_titles.items():
        text = sections.get(key, "")
        if not text or iy < m+40: continue

        _section_header(c, cx, iy, title, cw); iy -= 20
        para = Paragraph(text, style)
        pw, ph = para.wrap(cw, iy-m-20)
        para.drawOn(c, cx, iy-ph); iy -= ph+12
        _divider(c, cx+cw*0.3, iy, cw*0.4, alpha=0.35); iy -= 14

    c.setFillColor(C_MUTED); c.setFont(_FONT_NAME, 6.5)
    c.drawCentredString(W/2, m+6,
        "Данный документ носит ознакомительный характер. Астрология — язык символов и архетипов.")

    c.restoreState(); _page_num(c, 3, 3)


def _parse_interp_string(text: str) -> dict:
    """Parse a markdown-formatted interpretation string into sections dict."""
    section_map = {
        "общий": "general", "портрет": "general", "личност": "general", "personality": "general",
        "карьер": "career", "призван": "career", "career": "career",
        "отношен": "relationships", "партнёр": "relationships", "relationship": "relationships",
        "здоров": "health", "энерг": "health", "health": "health",
        "финанс": "finance", "материал": "finance", "finance": "finance",
        "духовн": "spirituality", "внутренн": "spirituality", "spiritual": "spirituality",
    }
    sections = {}
    current_key = "general"
    current_lines = []

    for line in text.split("\n"):
        if line.startswith("### "):
            if current_lines:
                sections[current_key] = " ".join(current_lines).strip()
            title_lower = line[4:].lower()
            current_key = next(
                (v for k, v in section_map.items() if k in title_lower), "general"
            )
            current_lines = []
        else:
            stripped = line.strip()
            if stripped:
                current_lines.append(stripped)

    if current_lines:
        sections[current_key] = " ".join(current_lines).strip()

    return sections


# ── Public API ─────────────────────────────────────────────

def generate_pdf_bytes(chart, interpretation: str = "") -> bytes:
    """
    Generate a PDF and return it as bytes.

    Args:
        chart: NatalChart SQLAlchemy model instance (or any object/dict with the right fields)
        interpretation: Full interpretation text (markdown string) or dict of sections

    Returns:
        PDF file as bytes
    """
    # Normalise chart to dict
    if hasattr(chart, "__dict__"):
        ch = chart
        data = {
            "name": f"Натальная карта",
            "birth_date": ch.birth_date or "",
            "birth_time": ch.birth_time or "",
            "birth_place": ch.birth_place or "",
            "house_system": ch.house_system or "Placidus",
            "ascendant": ch.ascendant,
            "midheaven": ch.midheaven,
            "planets": ch.planets or [],
            "houses": ch.houses or [],
            "aspects": ch.aspects or [],
            "interpretation": interpretation,
        }
    else:
        data = dict(chart)
        data.setdefault("interpretation", interpretation)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Натальная карта — {data['birth_place']}")
    c.setAuthor("Astro SPA")

    _page_cover(c, data)
    c.showPage()
    _page_data(c, data)
    c.showPage()
    _page_interp(c, data)
    c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()
