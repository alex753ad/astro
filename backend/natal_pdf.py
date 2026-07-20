"""
Natal chart PDF generator — backend module.
Called by the /api/v1/chart/{chart_id}/pdf endpoint.

Usage:
    from backend.natal_pdf import generate_pdf_bytes
    pdf_bytes = generate_pdf_bytes(chart_record, interpretation_text)
"""

import base64
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
from reportlab.lib.utils import ImageReader

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os as _os

# Шрифт с астросимволами и кириллицей, лежащий в самом репозитории —
# гарантирует значки планет/знаков/аспектов в PDF на любом сервере.
_ASSET_FONT = _os.path.join(_os.path.dirname(__file__), "assets", "fonts", "DejaVuSans.ttf")


def _register_fonts():
    """Register Unicode fonts for Cyrillic + astrological symbols."""
    # Main font (Cyrillic)
    main_candidates = [
        ("C:/Windows/Fonts/arial.ttf",       "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/calibri.ttf",     "C:/Windows/Fonts/calibrib.ttf"),
        ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
         "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        # Запасной шрифт из репозитория (кириллица) — если системных нет
        (_ASSET_FONT, _ASSET_FONT),
    ]
    font_name = None
    for regular, bold in main_candidates:
        if _os.path.exists(regular):
            try:
                pdfmetrics.registerFont(TTFont("MainFont", regular))
                if _os.path.exists(bold):
                    pdfmetrics.registerFont(TTFont("MainFont-Bold", bold))
                else:
                    pdfmetrics.registerFont(TTFont("MainFont-Bold", regular))
                font_name = "MainFont"
                break
            except Exception:
                continue

    # Символьный шрифт с астро/зодиакальными глифами.
    # Первый кандидат — встроенный в репозиторий DejaVuSans (есть на любом сервере).
    sym_candidates = [
        _ASSET_FONT,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansSymbols-Regular.ttf",
        "C:/Windows/Fonts/seguisym.ttf",
    ]
    global _SYMBOL_FONT
    _SYMBOL_FONT = None
    for path in sym_candidates:
        if _os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("SymFont", path))
                _SYMBOL_FONT = "SymFont"
                break
            except Exception:
                continue

    return font_name

_SYMBOL_FONT = None
_FONT_NAME = _register_fonts() or "Helvetica"
_FONT_BOLD = (_FONT_NAME + "-Bold") if _FONT_NAME != "Helvetica" else "Helvetica-Bold"


def _draw_glyph(c, x, y, glyph, size, color):
    """Draw astrological glyph using symbol font if available, else ASCII fallback."""
    if _SYMBOL_FONT:
        c.setFillColor(color)
        c.setFont(_SYMBOL_FONT, size)
        # ⚹ (U+26B9) отсутствует в DejaVu — рисуем совместимую шестилучевую звезду
        glyph = "✶" if glyph == "⚹" else glyph
        c.drawCentredString(x, y - size * 0.35, glyph)
    else:
        # ASCII fallbacks
        FALLBACK = {
            "☉": "Su", "☽": "Mo", "☿": "Me", "♀": "Ve", "♂": "Ma",
            "♃": "Ju", "♄": "Sa", "♅": "Ur", "♆": "Ne", "♇": "Pl",
            "☊": "NN", "☋": "SN",
            "♈": "Ar", "♉": "Ta", "♊": "Ge", "♋": "Cn", "♌": "Le",
            "♍": "Vi", "♎": "Li", "♏": "Sc", "♐": "Sg", "♑": "Cp",
            "♒": "Aq", "♓": "Pi",
            "☌": "cn", "☍": "op", "△": "tr", "□": "sq", "⚹": "sx",
        }
        text = FALLBACK.get(glyph, glyph)
        c.setFillColor(color)
        c.setFont(_FONT_BOLD, size * 0.7)
        c.drawCentredString(x, y - size * 0.25, text)


W, H = A4

C_BG      = colors.HexColor("#FDFBFF")
C_GOLD    = colors.HexColor("#7B5EA7")
C_GOLD2   = colors.HexColor("#5B3E87")
C_SILVER  = colors.HexColor("#8890A0")
C_ACCENT  = colors.HexColor("#7B5EA7")
C_TEXT    = colors.HexColor("#1A1230")
C_MUTED   = colors.HexColor("#6B6080")
C_BORDER  = colors.HexColor("#D8D0F0")
C_STAR    = colors.HexColor("#7B5EA7")
C_RETRO   = colors.HexColor("#CC6655")
C_TRINE   = colors.HexColor("#4A9060")
C_SQUARE  = colors.HexColor("#CC5544")
C_SEXTILE = colors.HexColor("#4A7090")
C_CONJ    = colors.HexColor("#C9A84C")

PLANET_GLYPHS = {
    "Sun":"☉","Moon":"☽","Mercury":"☿","Venus":"♀","Mars":"♂",
    "Jupiter":"♃","Saturn":"♄","Uranus":"♅","Neptune":"♆","Pluto":"♇",
    "North Node":"☊","South Node":"☋",
    "Солнце":"☉","Луна":"☽","Меркурий":"☿","Венера":"♀","Марс":"♂",
    "Юпитер":"♃","Сатурн":"♄","Уран":"♅","Нептун":"♆","Плутон":"♇",
    "Северный узел":"☊","Южный узел":"☋",
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


def _wheel(c, cx, cy, r, planets=None, ascendant=None, aspects=None):
    """Draw zodiac wheel. If planets provided, place them at real positions."""
    sign_glyphs = list(SIGN_GLYPHS.values())[:12]
    # Brighter element colours: Fire / Earth / Air / Water
    seg_colors = [
        colors.HexColor("#C04040"), colors.HexColor("#6CA840"),
        colors.HexColor("#3A80C8"), colors.HexColor("#8050B8"),
    ] * 3
    # Ascendant longitude — rotate wheel so ASC is on left (180°)
    asc_lon = 0.0
    if ascendant and isinstance(ascendant, dict):
        asc_lon = ascendant.get("longitude", 0.0) or 0.0

    # Outer ring (r*0.88 – r): sign glyphs live here
    # Middle ring (r*0.65 – r*0.88): planet glyphs live here
    # Inner circle (0 – r*0.62): aspect lines + centre fill
    for i in range(12):
        sign_start_lon = i * 30
        start_angle = 180 + (sign_start_lon - asc_lon)
        seg = colors.Color(seg_colors[i].red, seg_colors[i].green, seg_colors[i].blue, alpha=0.48)
        c.setFillColor(seg)
        c.setStrokeColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=0.70))
        c.setLineWidth(0.6)
        c.wedge(cx-r, cy-r, cx+r, cy+r, start_angle, 30, fill=1, stroke=1)
        # Sign glyph in outer ring at r*0.94
        mid_a = math.radians(start_angle + 15)
        gx = cx + r*0.94*math.cos(mid_a); gy = cy + r*0.94*math.sin(mid_a)
        _draw_glyph(c, gx, gy, sign_glyphs[i], 11, colors.HexColor("#FFFFFF"))

    for radius, alpha in [(r*0.65, 0.55), (r*0.88, 0.75), (r, 1.0)]:
        c.setStrokeColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=alpha))
        c.setLineWidth(0.8 if radius < r else 1.4)
        c.circle(cx, cy, radius, fill=0, stroke=1)
    c.setFillColor(colors.Color(C_BG.red, C_BG.green, C_BG.blue, alpha=0.94))
    c.circle(cx, cy, r*0.62, fill=1, stroke=0)

    # Draw aspect lines inside inner circle (before planets so glyphs appear on top)
    if aspects and planets:
        r_asp = r * 0.56
        aspect_pts = {}
        for pl in planets:
            lon = pl.get("longitude", 0) if isinstance(pl, dict) else getattr(pl, "longitude", 0)
            name = pl.get("name", "") if isinstance(pl, dict) else getattr(pl, "name", "")
            ang = math.radians(180 + (lon - asc_lon))
            aspect_pts[name] = (cx + r_asp * math.cos(ang), cy + r_asp * math.sin(ang))
        for asp in aspects[:30]:
            p1 = asp.get("planet1", "")
            p2 = asp.get("planet2", "")
            at = asp.get("aspect_type", asp.get("aspect", ""))
            col = ASPECT_COLORS.get(at, C_MUTED)
            if p1 in aspect_pts and p2 in aspect_pts:
                x1, y1 = aspect_pts[p1]
                x2, y2 = aspect_pts[p2]
                c.setStrokeColor(colors.Color(col.red, col.green, col.blue, alpha=0.50))
                c.setLineWidth(0.9)
                c.line(x1, y1, x2, y2)

    # Draw planets at real positions
    if planets:
        planet_colors_map = {
            "Sun": C_GOLD2, "Moon": colors.HexColor("#A0B0C8"),
            "Mercury": colors.HexColor("#A090D0"), "Venus": colors.HexColor("#D08090"),
            "Mars": colors.HexColor("#D06050"), "Jupiter": colors.HexColor("#6090D0"),
            "Saturn": colors.HexColor("#909080"), "Uranus": colors.HexColor("#60A8B8"),
            "Neptune": colors.HexColor("#8880C0"), "Pluto": colors.HexColor("#B03030"),
            "North Node": colors.HexColor("#60B878"),
        }
        r_planet = r * 0.76  # middle ring between r*0.65 and r*0.88
        # Spread overlapping planets
        positions = []
        for pl in planets:
            lon = pl.get("longitude", 0) if isinstance(pl, dict) else getattr(pl, "longitude", 0)
            name = pl.get("name", "") if isinstance(pl, dict) else getattr(pl, "name", "")
            positions.append({"name": name, "lon": lon, "disp": lon})
        # Simple push-apart
        for _ in range(30):
            moved = False
            for i in range(len(positions)):
                for j in range(i+1, len(positions)):
                    diff = positions[j]["disp"] - positions[i]["disp"]
                    while diff > 180: diff -= 360
                    while diff < -180: diff += 360
                    if abs(diff) < 7:
                        push = (7 - abs(diff)) / 2 + 0.1
                        if diff >= 0:
                            positions[i]["disp"] -= push; positions[j]["disp"] += push
                        else:
                            positions[i]["disp"] += push; positions[j]["disp"] -= push
                        moved = True
            if not moved:
                break

        for pos in positions:
            draw_angle = math.radians(180 + (pos["disp"] - asc_lon))
            px = cx + r_planet * math.cos(draw_angle)
            py = cy + r_planet * math.sin(draw_angle)
            col = planet_colors_map.get(pos["name"], C_GOLD2)
            # Circle background
            c.setFillColor(colors.Color(C_BG.red, C_BG.green, C_BG.blue, alpha=0.85))
            c.circle(px, py, 8, fill=1, stroke=0)
            c.setStrokeColor(colors.Color(col.red, col.green, col.blue, alpha=0.7))
            c.setLineWidth(0.7)
            c.circle(px, py, 8, fill=0, stroke=1)
            # Glyph
            glyph = PLANET_GLYPHS.get(pos["name"], "?")
            _draw_glyph(c, px, py, glyph, 10, col)


def _bg(c):
    c.setFillColor(C_BG); c.rect(0, 0, W, H, fill=1, stroke=0)


# ── Pages ─────────────────────────────────────────────────

def _page_cover(c, d):
    c.saveState()
    _bg(c)

    m = 12*mm
    _border(c, m, m, W-2*m, H-2*m, lw=0.7)
    o = m+4
    for cx2, cy2 in [(o,o),(W-o,o),(o,H-o),(W-o,H-o)]: _corner(c, cx2, cy2, 8)

    # Заголовок и данные сверху
    ty = H - m - 22
    c.setFillColor(C_GOLD2); c.setFont(_FONT_BOLD, 9)
    c.drawCentredString(W/2, ty, "НАТАЛЬНАЯ КАРТА")
    _divider(c, W*0.2, ty-8, W*0.6)

    c.setFillColor(C_TEXT); c.setFont(_FONT_BOLD, 22)
    c.drawCentredString(W/2, ty-32, d["name"])

    c.setFillColor(C_MUTED); c.setFont(_FONT_NAME, 8)
    parts = [d["birth_date"]]
    if d.get("birth_time"): parts.append(d["birth_time"])
    parts.append(d["birth_place"])
    c.drawCentredString(W/2, ty-50, "  ·  ".join(parts))

    # Колесо крупнее — рисуем родной функцией (светлое, под стиль PDF),
    # не используем wheel_png с фронта, т.к. он тёмный.
    wheel_size = min(W, H) * 0.72
    wr = wheel_size / 2
    wcx = W / 2
    wcy = H * 0.46
    _wheel(c, wcx, wcy, wr, planets=d.get("planets", []), ascendant=d.get("ascendant"), aspects=d.get("aspects", []))

    # ASC / MC — чистый текст без рамок, по центру
    by = wcy - wr - 14
    for i, (label, key) in enumerate([("ASC", "ascendant"), ("MC", "midheaven")]):
        val = d.get(key) or {}
        sign = val.get("sign", "")
        deg = val.get("degree", 0)
        g = SIGN_GLYPHS.get(sign, "")
        # symmetrical around W/2: left item at -70, right at +70
        item_x = W / 2 + (i * 2 - 1) * 70
        c.setFillColor(C_GOLD2); c.setFont(_FONT_BOLD, 7.5)
        c.drawString(item_x, by, label)
        _draw_glyph(c, item_x + 22, by + 4, g, 10, C_GOLD)
        c.setFillColor(C_TEXT); c.setFont(_FONT_NAME, 7.5)
        c.drawString(item_x + 32, by, f"{sign} {deg:.1f}\u00b0")
    # centre dot separator
    c.setFillColor(C_MUTED)
    c.circle(W / 2, by + 3, 1.5, fill=1, stroke=0)

    _divider(c, W*0.25, by - 20, W*0.5)
    c.setFillColor(C_MUTED); c.setFont(_FONT_NAME, 7.5)
    hs = d.get("house_system", "Placidus").capitalize()
    astrologer = d.get("astrologer_name")
    footer_text = (
        f"Система домов: {hs}  ·  Подготовлено: {astrologer}"
        if astrologer
        else f"Система домов: {hs}  ·  Astrea Timeline"
    )
    c.drawCentredString(W/2, by - 32, footer_text)

    c.restoreState()


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
        _draw_glyph(c, bx+br, py, PLANET_GLYPHS.get(pl["name"],"?"), 10, C_GOLD2)
        c.setFillColor(C_TEXT); c.setFont(_FONT_BOLD, 8)
        c.drawString(bx+br*2+5, py-3, pl["name"])
        sg = SIGN_GLYPHS.get(pl["sign"],"")
        deg = pl.get("degree_in_sign", pl.get("degree", 0))
        _draw_glyph(c, bx+95, py+3, sg, 9, C_GOLD)
        c.setFillColor(C_TEXT); c.setFont(_FONT_NAME, 8)
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
        _draw_glyph(c, cl+36, py+5, SIGN_GLYPHS.get(h1["sign"],""), 9, C_GOLD)
        c.setFillColor(C_TEXT); c.drawString(cl+44, py, h1["sign"])
        c.setFillColor(C_MUTED); c.drawString(cl+cw/2+4, py, f"Дом {h2['number']:2d}")
        _draw_glyph(c, cl+cw/2+40, py+5, SIGN_GLYPHS.get(h2["sign"],""), 9, C_GOLD)
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
        _draw_glyph(c, cr+5, ay+4, PLANET_GLYPHS.get(p1,"?"), 10, C_GOLD2)
        c.setFillColor(C_TEXT); c.setFont(_FONT_NAME, 7.5)
        c.drawString(cr+11, ay, p1)
        _draw_glyph(c, cr+88, ay+4, sym, 10, acol)
        c.setFillColor(C_SILVER); c.setFont(_FONT_NAME, 7)
        c.drawCentredString(cr+88, ay-9, at)
        _draw_glyph(c, cr+108, ay+4, PLANET_GLYPHS.get(p2,"?"), 10, C_GOLD2)
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

    c.restoreState()


def _interp_page_begin(c, page_num_placeholder):
    """Draw background + header for an interpretation page. Returns (cx, cw, iy)."""
    m = 12*mm
    _bg(c)
    _nebula(c, W*0.5, H*0.5, 250, 300, C_ACCENT, alpha=0.03)
    _stars(c, 99 + page_num_placeholder, 80)
    _border(c, m, m, W-2*m, H-2*m, lw=0.6)
    o = m+4
    for cx2, cy2 in [(o,o),(W-o,o),(o,H-o),(W-o,H-o)]:
        _corner(c, cx2, cy2, 6)
    c.setFillColor(C_GOLD2); c.setFont(_FONT_BOLD, 10)
    c.drawCentredString(W/2, H-m-10, "ИНТЕРПРЕТАЦИЯ НАТАЛЬНОЙ КАРТЫ")
    _divider(c, m+10, H-m-18, W-2*m-20)
    return m+10, W-2*m-20, H-m-34


def _page_wheel(c, d):
    """Dedicated full-page zodiac wheel with planets and aspects."""
    c.saveState()
    _bg(c)

    m = 12 * mm
    _border(c, m, m, W - 2 * m, H - 2 * m, lw=0.6)
    o = m + 4
    for cx2, cy2 in [(o, o), (W - o, o), (o, H - o), (W - o, H - o)]:
        _corner(c, cx2, cy2, 6)

    # Title
    c.setFillColor(C_GOLD2)
    c.setFont(_FONT_BOLD, 10)
    c.drawCentredString(W / 2, H - m - 10, "НАТАЛЬНАЯ КАРТА — ЗОДИАКАЛЬНЫЙ КРУГ")
    _divider(c, m + 10, H - m - 18, W - 2 * m - 20)

    # Big wheel centred on page
    wcx, wcy = W / 2, H / 2 - 10 * mm
    wr = min(W, H) * 0.36
    if not (d.get("wheel_png") and _draw_wheel_png(c, wcx, wcy, wr * 2, d["wheel_png"])):
        _wheel(c, wcx, wcy, wr, planets=d.get("planets", []), ascendant=d.get("ascendant"))

    # Draw aspect lines inside inner circle
    planets = d.get("planets", [])
    aspects = d.get("aspects", [])
    asc_lon = (d.get("ascendant") or {}).get("longitude", 0.0) or 0.0
    r_inner = wr * 0.62
    r_asp = wr * 0.55

    planet_angles = {}
    for pl in planets:
        lon = pl.get("longitude", 0) if isinstance(pl, dict) else 0
        name = pl.get("name", "") if isinstance(pl, dict) else ""
        draw_angle = math.radians(180 + (lon - asc_lon))
        planet_angles[name] = (
            wcx + r_inner * math.cos(draw_angle),
            wcy + r_inner * math.sin(draw_angle),
        )

    for asp in aspects[:30]:
        p1 = asp.get("planet1", "")
        p2 = asp.get("planet2", "")
        at = asp.get("aspect_type", "")
        col = ASPECT_COLORS.get(at, C_MUTED)
        if p1 in planet_angles and p2 in planet_angles:
            x1, y1 = planet_angles[p1]
            x2, y2 = planet_angles[p2]
            c.setStrokeColor(colors.Color(col.red, col.green, col.blue, alpha=0.25))
            c.setLineWidth(0.5)
            c.line(x1, y1, x2, y2)

    # Planet table at bottom
    table_x = m + 8
    table_y = m + 12 * mm
    col_w = (W - 2 * m - 16) / 5
    c.setFillColor(C_GOLD2)
    c.setFont(_FONT_BOLD, 7)
    for i, header in enumerate(["Планета", "Знак", "Градус", "Дом", "R"]):
        c.drawString(table_x + i * col_w, table_y + 4, header)
    c.setStrokeColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=0.3))
    c.setLineWidth(0.4)
    c.line(table_x, table_y, table_x + (W - 2 * m - 16), table_y)
    row_y = table_y - 11
    for pl in planets:
        name = pl.get("name", "")
        sign = pl.get("sign", "")
        deg = pl.get("degree_in_sign", pl.get("degree", 0))
        house = pl.get("house", "")
        retro = "℞" if pl.get("retrograde") else ""
        glyph = PLANET_GLYPHS.get(name, "")
        _draw_glyph(c, table_x + 5, row_y + 4, glyph, 8, C_GOLD2)
        c.setFillColor(C_TEXT)
        c.setFont(_FONT_NAME, 7)
        c.drawString(table_x + 13, row_y, name)
        sg = SIGN_GLYPHS.get(sign, "")
        _draw_glyph(c, table_x + col_w + 5, row_y + 4, sg, 8, C_GOLD)
        c.setFillColor(C_TEXT)
        c.drawString(table_x + col_w + 14, row_y, sign[:3])
        c.drawString(table_x + col_w * 2, row_y, f"{deg:.1f}°")
        c.drawString(table_x + col_w * 3, row_y, str(house) if house else "—")
        if retro:
            c.setFillColor(C_RETRO)
            c.drawString(table_x + col_w * 4, row_y, retro)
        row_y -= 11
        if row_y < m + 4 * mm:
            break

    c.restoreState()


def _page_interp(c, d, first_page_num=3):
    """Render interpretation — auto-expands to as many pages as needed."""
    interp = d.get("interpretation", {})
    if isinstance(interp, str):
        sections = _parse_interp_string(interp)
    else:
        sections = interp or {}

    section_titles = [
        ("general",       "✦  Общий портрет личности"),
        ("career",        "✦  Карьера и призвание"),
        ("relationships", "✦  Отношения и партнёрство"),
        ("health",        "✦  Здоровье и энергия"),
        ("finance",       "✦  Финансы"),
        ("spirituality",  "✦  Духовное развитие"),
    ]

    style = ParagraphStyle(
        "body", fontName=_FONT_NAME, fontSize=8.5, leading=13.5,
        textColor=C_TEXT, alignment=TA_JUSTIFY, spaceAfter=4,
    )
    head_style = ParagraphStyle(
        "head", fontName=_FONT_BOLD, fontSize=9, leading=14,
        textColor=C_GOLD2, spaceAfter=4,
    )

    m = 12*mm
    page_idx = 0
    cx_col, cw_col, iy = _interp_page_begin(c, page_idx)
    bottom_margin = m + 22

    def new_page():
        nonlocal page_idx, cx_col, cw_col, iy
        # footer on current page
        c.setFillColor(C_MUTED); c.setFont(_FONT_NAME, 6.5)
        c.drawCentredString(W/2, m+6,
            "Астрея — навигатор решений. Астрология описывает тенденции, а не определяет судьбу.")
        c.showPage()
        page_idx += 1
        cx_col, cw_col, iy = _interp_page_begin(c, page_idx)

    for key, title in section_titles:
        text = sections.get(key, "")
        if not text:
            continue

        # Section header — 20pt height
        if iy - 20 < bottom_margin:
            new_page()

        _section_header(c, cx_col, iy, title, cw_col)
        iy -= 22

        # Split text into paragraphs and flow across pages
        raw_paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not raw_paras:
            raw_paras = [text]

        for raw in raw_paras:
            para = Paragraph(raw, style)
            _pw, ph = para.wrap(cw_col, iy - bottom_margin)

            if ph > iy - bottom_margin and ph < (H - 2*m - 60):
                # Paragraph fits on a fresh page but not here → new page
                new_page()
                _pw, ph = para.wrap(cw_col, iy - bottom_margin)

            if ph > iy - bottom_margin:
                # Paragraph is larger than a full page — split manually
                words = raw.split()
                chunk_words = []
                for w in words:
                    chunk_words.append(w)
                    test = Paragraph(" ".join(chunk_words), style)
                    _tw, th = test.wrap(cw_col, iy - bottom_margin)
                    if th > iy - bottom_margin:
                        chunk_words.pop()
                        if chunk_words:
                            chunk_para = Paragraph(" ".join(chunk_words), style)
                            _cw2, ch = chunk_para.wrap(cw_col, iy - bottom_margin)
                            chunk_para.drawOn(c, cx_col, iy - ch)
                            iy -= ch + 4
                        new_page()
                        chunk_words = [w]
                if chunk_words:
                    chunk_para = Paragraph(" ".join(chunk_words), style)
                    _cw2, ch = chunk_para.wrap(cw_col, iy - bottom_margin)
                    chunk_para.drawOn(c, cx_col, iy - ch)
                    iy -= ch + 4
            else:
                para.drawOn(c, cx_col, iy - ph)
                iy -= ph + 4

        # Divider between sections
        if iy - 14 > bottom_margin:
            _divider(c, cx_col + cw_col*0.3, iy, cw_col*0.4, alpha=0.35)
            iy -= 14

    # Footer on last page
    c.setFillColor(C_MUTED); c.setFont(_FONT_NAME, 6.5)
    c.drawCentredString(W/2, m+6,
        "Астрея — навигатор решений. Астрология описывает тенденции, а не определяет судьбу.")

    return page_idx  # number of extra interp pages added


def _parse_interp_string(text: str) -> dict:
    """Parse interpretation text — supports <section name="..."> tags and ### markdown headers."""
    import re

    # Format 1: <section name="general">...</section>
    tag_sections = re.findall(r'<section name="([^"]+)">(.*?)</section>', text, re.DOTALL)
    if tag_sections:
        return {name: content.strip() for name, content in tag_sections}

    # Format 2: ### Heading markdown
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
        if line.startswith("### ") or line.startswith("## "):
            if current_lines:
                sections[current_key] = "\n\n".join(current_lines).strip()
            title_lower = re.sub(r'#+\s*', '', line).lower()
            current_key = next(
                (v for k, v in section_map.items() if k in title_lower), "general"
            )
            current_lines = []
        else:
            stripped = line.strip()
            if stripped:
                current_lines.append(stripped)

    if current_lines:
        prev = sections.get(current_key, "")
        sections[current_key] = (prev + "\n\n" + "\n\n".join(current_lines)).strip()

    # Format 3: no markers — treat entire text as "general"
    if not sections:
        sections["general"] = text.strip()

    return sections


# ── Public API ─────────────────────────────────────────────

def _draw_wheel_png(c, cx, cy, size, wheel_png_b64: str) -> bool:
    """Вставляет PNG колеса по центру (cx, cy) с заданным size.
    Возвращает True при успехе, False при ошибке."""
    try:
        png_bytes = base64.b64decode(wheel_png_b64)
        img_reader = ImageReader(io.BytesIO(png_bytes))
        x = cx - size / 2
        y = cy - size / 2
        c.drawImage(img_reader, x, y, width=size, height=size, mask='auto')
        return True
    except Exception:
        return False


def generate_pdf_bytes(chart, interpretation: str = "", astrologer_name: str | None = None, wheel_png: str | None = None) -> bytes:
    """
    Generate a PDF and return it as bytes.

    Args:
        chart: NatalChart SQLAlchemy model instance (or any object/dict with the right fields)
        interpretation: Full interpretation text (markdown string) or dict of sections
        astrologer_name: Premium-only — astrologer display name shown on cover page

    Returns:
        PDF file as bytes
    """
    # Normalise chart to dict
    if hasattr(chart, "__dict__"):
        ch = chart
        data = {
            "name": "Натальная карта",
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
            "astrologer_name": astrologer_name,
            "wheel_png": wheel_png,
        }
    else:
        data = dict(chart)
        data.setdefault("interpretation", interpretation)
        data.setdefault("astrologer_name", astrologer_name)
        data["wheel_png"] = wheel_png

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Натальная карта — {data['birth_place']}")
    author = astrologer_name or "Astrea Timeline"
    c.setAuthor(author)

    _page_cover(c, data)
    c.showPage()
    _page_data(c, data)
    c.showPage()
    _page_interp(c, data)
    # _page_interp calls c.showPage() internally for extra pages;
    # the last interp page is NOT followed by showPage, so we add it here.
    c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()
