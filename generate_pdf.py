"""
Luxurious natal chart PDF generator with astrology aesthetics.
Dark parchment, stars, planet glyphs, ornamental borders.
"""

import math
import random
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY

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
    "Солнце":"☉","Луна":"☽","Меркурий":"☿","Венера":"♀",
    "Марс":"♂","Юпитер":"♃","Сатурн":"♄","Уран":"♅","Нептун":"♆","Плутон":"♇",
}
SIGN_GLYPHS = {
    "Овен":"♈","Телец":"♉","Близнецы":"♊","Рак":"♋","Лев":"♌","Дева":"♍",
    "Весы":"♎","Скорпион":"♏","Стрелец":"♐","Козерог":"♑","Водолей":"♒","Рыбы":"♓",
}
ASPECT_SYMBOLS = {
    "соединение":"☌","оппозиция":"☍","тригон":"△","квадрат":"□","секстиль":"⚹","квинконс":"⚻",
}
ASPECT_COLORS = {
    "соединение":C_CONJ,"тригон":C_TRINE,"секстиль":C_SEXTILE,
    "квадрат":C_SQUARE,"оппозиция":C_SQUARE,"квинконс":C_MUTED,
}

CHART_DATA = {
    "name": "Иван Иванов",
    "birth_date": "15 марта 1990",
    "birth_time": "14:30",
    "birth_place": "Москва, Россия",
    "house_system": "Placidus",
    "ascendant": {"sign": "Рак", "degree": 12.4},
    "midheaven": {"sign": "Овен", "degree": 8.7},
    "planets": [
        {"name":"Солнце",  "sign":"Рыбы",     "degree":24.3,"house":9, "retrograde":False},
        {"name":"Луна",    "sign":"Скорпион", "degree":7.1, "house":5, "retrograde":False},
        {"name":"Меркурий","sign":"Рыбы",     "degree":10.8,"house":9, "retrograde":False},
        {"name":"Венера",  "sign":"Овен",     "degree":3.2, "house":10,"retrograde":False},
        {"name":"Марс",    "sign":"Козерог",  "degree":19.6,"house":7, "retrograde":False},
        {"name":"Юпитер",  "sign":"Рак",      "degree":2.9, "house":1, "retrograde":False},
        {"name":"Сатурн",  "sign":"Козерог",  "degree":22.4,"house":7, "retrograde":False},
        {"name":"Уран",    "sign":"Козерог",  "degree":6.1, "house":7, "retrograde":False},
        {"name":"Нептун",  "sign":"Козерог",  "degree":13.7,"house":7, "retrograde":False},
        {"name":"Плутон",  "sign":"Скорпион", "degree":16.2,"house":5, "retrograde":True},
    ],
    "houses": [
        {"number":1,"sign":"Рак"},{"number":2,"sign":"Лев"},{"number":3,"sign":"Дева"},
        {"number":4,"sign":"Весы"},{"number":5,"sign":"Скорпион"},{"number":6,"sign":"Стрелец"},
        {"number":7,"sign":"Козерог"},{"number":8,"sign":"Водолей"},{"number":9,"sign":"Рыбы"},
        {"number":10,"sign":"Овен"},{"number":11,"sign":"Телец"},{"number":12,"sign":"Близнецы"},
    ],
    "aspects": [
        {"planet1":"Солнце", "aspect":"соединение","planet2":"Меркурий","orb":0.4},
        {"planet1":"Луна",   "aspect":"тригон",    "planet2":"Марс",    "orb":1.2},
        {"planet1":"Венера", "aspect":"секстиль",  "planet2":"Юпитер",  "orb":0.3},
        {"planet1":"Марс",   "aspect":"соединение","planet2":"Сатурн",  "orb":2.8},
        {"planet1":"Юпитер", "aspect":"квадрат",   "planet2":"Плутон",  "orb":1.6},
        {"planet1":"Сатурн", "aspect":"соединение","planet2":"Уран",    "orb":3.7},
        {"planet1":"Солнце", "aspect":"тригон",    "planet2":"Плутон",  "orb":2.1},
        {"planet1":"Луна",   "aspect":"оппозиция", "planet2":"Юпитер",  "orb":4.2},
    ],
    "interpretation": {
        "general": "Ваша натальная карта отражает глубокую, многогранную личность с сильным интуитивным началом. Солнце в Рыбах наделяет вас развитой эмпатией, творческим воображением и способностью воспринимать тонкие энергии окружающего мира. Юпитер в Раке в первом доме усиливает природную заботливость и создаёт ауру душевной теплоты, которая притягивает людей. Стеллиум планет в Козероге формирует мощный противовес — стремление к структуре, достижениям и долгосрочному планированию.",
        "career": "Венера в Овне на куспиде десятого дома указывает на призвание к лидерству и творческим профессиям. Вы способны зажигать других своим энтузиазмом и первопроходческим духом. Стеллиум в Козероге в седьмом доме говорит о стратегическом мышлении и умении выстраивать долгосрочные партнёрства, работающие на профессиональный успех.",
        "relationships": "Луна в Скорпионе в пятом доме наделяет вас глубокой эмоциональностью и страстностью в любви. Вы ищете трансформирующих, духовно насыщенных отношений. Тригон Луны и Марса создаёт гармоничное сочетание чувств и воли — вы умеете действовать в отношениях решительно, не теряя чуткости.",
        "spirituality": "Солнце и Меркурий в Рыбах в девятом доме — мощный указатель на духовный путь через познание и философию. Вы склонны к мистицизму и интуитивному постижению истины. Тригон Солнца и Плутона придаёт глубину трансформациям — каждый жизненный кризис становится ступенью к мудрости.",
    },
}


# ── Helpers ──

def draw_starfield(c, seed=42, count=180):
    rng = random.Random(seed)
    for _ in range(count):
        x = rng.uniform(0, W)
        y = rng.uniform(0, H)
        size = rng.choice([0.4, 0.6, 0.8, 1.0, 1.4, 1.8])
        alpha = rng.uniform(0.15, 0.75)
        col = colors.Color(C_STAR.red, C_STAR.green, C_STAR.blue, alpha=alpha)
        c.setFillColor(col)
        c.setStrokeColor(col)
        if size >= 1.4:
            arm = size * 2.5
            c.setLineWidth(0.4)
            c.line(x-arm, y, x+arm, y)
            c.line(x, y-arm, x, y+arm)
        c.circle(x, y, size, fill=1, stroke=0)


def draw_nebula(c, cx, cy, rx, ry, col, alpha=0.04):
    for i in range(6, 0, -1):
        f = i / 6
        a = alpha * f * 0.7
        g = colors.Color(col.red, col.green, col.blue, alpha=a)
        c.setFillColor(g)
        c.ellipse(cx-rx*f, cy-ry*f, cx+rx*f, cy+ry*f, fill=1, stroke=0)


def draw_ornament_border(c, x, y, w, h, col=None, lw=0.6):
    if col is None: col = C_GOLD
    gap = 3
    c.setStrokeColor(col); c.setLineWidth(lw)
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.setLineWidth(lw*0.5)
    c.setStrokeColor(colors.Color(col.red, col.green, col.blue, alpha=0.4))
    c.rect(x+gap, y+gap, w-gap*2, h-gap*2, fill=0, stroke=1)


def draw_corner_ornament(c, cx, cy, size, angle_offset=0):
    c.setFillColor(C_GOLD); c.setLineWidth(0.5)
    for angle in range(0, 360, 90):
        rad = math.radians(angle + angle_offset)
        ex = cx + math.cos(rad)*size; ey = cy + math.sin(rad)*size
        c.setStrokeColor(C_GOLD); c.setLineWidth(0.4)
        c.line(cx, cy, ex, ey)
        c.setFillColor(C_GOLD); c.circle(ex, ey, size*0.15, fill=1, stroke=0)
    c.circle(cx, cy, size*0.2, fill=1, stroke=0)


def draw_divider(c, x, y, width, col=None):
    if col is None: col = C_GOLD
    mid = x + width/2
    c.setStrokeColor(col); c.setLineWidth(0.5)
    c.line(x, y, mid-6, y); c.line(mid+6, y, x+width, y)
    c.setFillColor(col)
    size = 3
    p = c.beginPath()
    p.moveTo(mid, y+size); p.lineTo(mid+size, y)
    p.lineTo(mid, y-size); p.lineTo(mid-size, y); p.close()
    c.drawPath(p, fill=1, stroke=0)
    for dx in [-10, 10]: c.circle(mid+dx, y, 1, fill=1, stroke=0)


def draw_zodiac_wheel(c, cx, cy, r):
    signs = list(SIGN_GLYPHS.keys())
    seg_colors = [
        colors.HexColor("#8B3A3A"), colors.HexColor("#5C7A3A"),
        colors.HexColor("#3A5C8B"), colors.HexColor("#7A5C3A"),
    ] * 3
    for i in range(12):
        start_angle = 90 - i*30
        seg = colors.Color(seg_colors[i].red, seg_colors[i].green, seg_colors[i].blue, alpha=0.13)
        c.setFillColor(seg)
        c.setStrokeColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=0.3))
        c.setLineWidth(0.4)
        c.wedge(cx-r, cy-r, cx+r, cy+r, start_angle-30, 30, fill=1, stroke=1)
        mid_angle = math.radians(start_angle - 15)
        gx = cx + (r*0.78)*math.cos(mid_angle)
        gy = cy + (r*0.78)*math.sin(mid_angle)
        c.setFillColor(C_GOLD2); c.setFont("Helvetica", 7)
        c.drawCentredString(gx, gy-2.5, SIGN_GLYPHS.get(signs[i], ""))
    for radius, alpha in [(r*0.65, 0.25), (r*0.9, 0.4), (r, 0.6)]:
        c.setStrokeColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=alpha))
        c.setLineWidth(0.5 if radius < r else 0.8)
        c.circle(cx, cy, radius, fill=0, stroke=1)
    draw_nebula(c, cx, cy, r*0.5, r*0.5, C_ACCENT, alpha=0.08)
    c.setFillColor(colors.Color(C_ACCENT.red, C_ACCENT.green, C_ACCENT.blue, alpha=0.15))
    c.circle(cx, cy, r*0.62, fill=1, stroke=0)


def section_header(c, x, y, title, width):
    c.setFillColor(colors.Color(C_ACCENT.red, C_ACCENT.green, C_ACCENT.blue, alpha=0.12))
    c.roundRect(x, y-4, width, 16, 4, fill=1, stroke=0)
    c.setFillColor(C_GOLD); c.rect(x, y-4, 2.5, 16, fill=1, stroke=0)
    c.setFillColor(C_GOLD2); c.setFont("Helvetica-Bold", 9)
    c.drawString(x+8, y+2, title.upper())


def draw_page_number(c, page_num, total):
    c.setFillColor(C_MUTED); c.setFont("Helvetica", 7)
    c.drawCentredString(W/2, 14*mm, f"— {page_num} / {total} —")


# ══════════════════════════════════════════════════════════
# PAGE 1: COVER
# ══════════════════════════════════════════════════════════

def draw_cover(c, data):
    c.saveState()
    c.setFillColor(C_BG); c.rect(0, 0, W, H, fill=1, stroke=0)
    draw_nebula(c, W*0.2, H*0.8, 160, 100, C_ACCENT, alpha=0.06)
    draw_nebula(c, W*0.8, H*0.2, 140, 90, colors.HexColor("#3A2060"), alpha=0.07)
    draw_nebula(c, W*0.5, H*0.5, 200, 200, C_ACCENT, alpha=0.03)
    draw_starfield(c, seed=7, count=220)

    margin = 12*mm
    draw_ornament_border(c, margin, margin, W-2*margin, H-2*margin, C_GOLD, lw=0.7)
    o = margin+4
    for cx2, cy2 in [(o,o),(W-o,o),(o,H-o),(W-o,H-o)]:
        draw_corner_ornament(c, cx2, cy2, 8, angle_offset=45)

    # Zodiac wheel
    wheel_cx = W/2; wheel_cy = H*0.62; wheel_r = 88
    draw_zodiac_wheel(c, wheel_cx, wheel_cy, wheel_r)

    # Planet glyphs orbiting wheel
    for i, pl in enumerate(data["planets"][:8]):
        angle = math.radians(90 - i*(360/8))
        orbit_r = wheel_r*1.22
        px = wheel_cx + orbit_r*math.cos(angle)
        py = wheel_cy + orbit_r*math.sin(angle)
        c.setFillColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=0.12))
        c.circle(px, py, 9, fill=1, stroke=0)
        c.setFillColor(C_GOLD2); c.setFont("Helvetica", 12)
        c.drawCentredString(px, py-4, PLANET_GLYPHS.get(pl["name"], "★"))

    # Title
    title_y = H*0.915
    c.setFillColor(C_GOLD2); c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(W/2, title_y, "✦  НАТАЛЬНАЯ КАРТА  ✦")
    draw_divider(c, W*0.2, title_y-8, W*0.6, C_GOLD)

    c.setFillColor(C_TEXT); c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(W/2, title_y-30, data["name"])

    info_y = title_y-48
    c.setFillColor(C_MUTED); c.setFont("Helvetica", 8)
    c.drawCentredString(W/2, info_y,
        f"{data['birth_date']}  ·  {data['birth_time']}  ·  {data['birth_place']}")

    # ASC / MC badges
    badge_y = wheel_cy - wheel_r - 18
    for label, key, bx in [("ASC","ascendant", W/2-55), ("MC","midheaven", W/2+10)]:
        val = data[key]; glyph = SIGN_GLYPHS.get(val["sign"],"")
        c.setFillColor(colors.Color(C_ACCENT.red, C_ACCENT.green, C_ACCENT.blue, alpha=0.2))
        c.roundRect(bx, badge_y-6, 45, 18, 4, fill=1, stroke=0)
        c.setStrokeColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=0.4))
        c.setLineWidth(0.4)
        c.roundRect(bx, badge_y-6, 45, 18, 4, fill=0, stroke=1)
        c.setFillColor(C_GOLD); c.setFont("Helvetica-Bold", 7)
        c.drawString(bx+4, badge_y+5, label)
        c.setFillColor(C_TEXT); c.setFont("Helvetica", 7.5)
        c.drawString(bx+18, badge_y+5, f"{glyph} {val['sign']} {val['degree']:.1f}")

    draw_divider(c, W*0.25, badge_y-16, W*0.5, C_GOLD)
    c.setFillColor(C_MUTED); c.setFont("Helvetica", 7.5)
    c.drawCentredString(W/2, badge_y-28,
        f"Система домов: {data['house_system'].capitalize()}  ·  Astrea Timeline")

    c.restoreState()
    draw_page_number(c, 1, 3)


# ══════════════════════════════════════════════════════════
# PAGE 2: PLANETS + HOUSES + ASPECTS
# ══════════════════════════════════════════════════════════

def draw_data_page(c, data):
    c.saveState()
    c.setFillColor(C_BG); c.rect(0, 0, W, H, fill=1, stroke=0)
    draw_nebula(c, W*0.1, H*0.9, 120, 80, C_ACCENT, alpha=0.04)
    draw_nebula(c, W*0.9, H*0.1, 100, 70, C_ACCENT, alpha=0.04)
    draw_starfield(c, seed=13, count=120)

    margin = 12*mm
    draw_ornament_border(c, margin, margin, W-2*margin, H-2*margin, C_GOLD, lw=0.6)
    o = margin+4
    for cx2, cy2 in [(o,o),(W-o,o),(o,H-o),(W-o,H-o)]:
        draw_corner_ornament(c, cx2, cy2, 6, angle_offset=45)

    c.setFillColor(C_GOLD2); c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(W/2, H-margin-10, "ПЛАНЕТЫ · ДОМА · АСПЕКТЫ")
    draw_divider(c, margin+10, H-margin-18, W-2*margin-20)

    col_w = (W-2*margin-16)/2 - 6
    col_left = margin+8
    col_right = W/2+4

    # ── Planets ──
    py = H-margin-34
    section_header(c, col_left, py, "Положение планет", col_w)
    py -= 22

    for pl in data["planets"]:
        badge_r = 7
        glyph = PLANET_GLYPHS.get(pl["name"], "★")
        sign_g = SIGN_GLYPHS.get(pl["sign"], "")
        bx = col_left

        c.setFillColor(colors.Color(C_ACCENT.red, C_ACCENT.green, C_ACCENT.blue, alpha=0.18))
        c.circle(bx+badge_r, py, badge_r, fill=1, stroke=0)
        c.setStrokeColor(colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=0.5))
        c.setLineWidth(0.5); c.circle(bx+badge_r, py, badge_r, fill=0, stroke=1)
        c.setFillColor(C_GOLD2); c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(bx+badge_r, py-3, glyph)

        c.setFillColor(C_TEXT); c.setFont("Helvetica-Bold", 8)
        c.drawString(bx+badge_r*2+5, py-3, pl["name"])
        c.setFillColor(C_GOLD); c.setFont("Helvetica", 8)
        c.drawString(bx+95, py-3, sign_g)
        c.setFillColor(C_TEXT)
        c.drawString(bx+105, py-3, f"{pl['sign']}  {pl['degree']:.1f}")
        c.setFillColor(C_MUTED); c.setFont("Helvetica", 7.5)
        c.drawString(bx+195, py-3, f"Дом {pl['house']}")
        if pl["retrograde"]:
            c.setFillColor(C_RETRO); c.setFont("Helvetica-Bold", 7)
            c.drawString(bx+235, py-3, "R")

        c.setStrokeColor(colors.Color(C_BORDER.red, C_BORDER.green, C_BORDER.blue, alpha=0.6))
        c.setLineWidth(0.3); c.line(col_left, py-9, col_left+col_w, py-9)
        py -= 20

    # ── Houses ──
    py -= 6
    section_header(c, col_left, py, "Дома", col_w)
    py -= 16
    houses = data["houses"]; half = len(houses)//2
    for i in range(half):
        h1 = houses[i]; h2 = houses[i+half]
        c.setFillColor(C_MUTED); c.setFont("Helvetica", 7.5)
        c.drawString(col_left, py, f"Дом {h1['number']:2d}")
        c.setFillColor(C_GOLD); c.drawString(col_left+34, py, SIGN_GLYPHS.get(h1["sign"],""))
        c.setFillColor(C_TEXT); c.drawString(col_left+44, py, h1["sign"])
        c.setFillColor(C_MUTED); c.drawString(col_left+col_w/2+4, py, f"Дом {h2['number']:2d}")
        c.setFillColor(C_GOLD); c.drawString(col_left+col_w/2+38, py, SIGN_GLYPHS.get(h2["sign"],""))
        c.setFillColor(C_TEXT); c.drawString(col_left+col_w/2+48, py, h2["sign"])
        py -= 13

    # ── Aspects ──
    ay = H-margin-34
    section_header(c, col_right, ay, "Аспекты", col_w)
    ay -= 22

    for asp in data["aspects"]:
        sym = ASPECT_SYMBOLS.get(asp["aspect"], "·")
        asp_col = ASPECT_COLORS.get(asp["aspect"], C_MUTED)
        g1 = PLANET_GLYPHS.get(asp["planet1"], "★")
        g2 = PLANET_GLYPHS.get(asp["planet2"], "★")

        c.setFillColor(C_GOLD2); c.setFont("Helvetica", 8.5)
        c.drawString(col_right, ay, g1)
        c.setFillColor(C_TEXT); c.setFont("Helvetica", 7.5)
        c.drawString(col_right+11, ay, asp["planet1"])
        c.setFillColor(asp_col); c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(col_right+88, ay, sym)
        c.setFillColor(C_SILVER); c.setFont("Helvetica", 7)
        c.drawCentredString(col_right+88, ay-9, asp["aspect"])
        c.setFillColor(C_GOLD2); c.setFont("Helvetica", 8.5)
        c.drawString(col_right+103, ay, g2)
        c.setFillColor(C_TEXT); c.setFont("Helvetica", 7.5)
        c.drawString(col_right+114, ay, asp["planet2"])
        c.setFillColor(C_MUTED); c.setFont("Helvetica", 7)
        c.drawRightString(col_right+175, ay, f"орб {asp['orb']:.1f}")

        c.setStrokeColor(colors.Color(C_BORDER.red, C_BORDER.green, C_BORDER.blue, alpha=0.5))
        c.setLineWidth(0.3); c.line(col_right, ay-13, col_right+col_w, ay-13)
        ay -= 26

    # ── Legend ──
    ay -= 8
    section_header(c, col_right, ay, "Условные обозначения", col_w)
    ay -= 16
    legend = [
        ("соединение ☌", C_CONJ), ("тригон △", C_TRINE),
        ("секстиль ⚹", C_SEXTILE), ("квадрат □", C_SQUARE),
        ("оппозиция ☍", C_SQUARE), ("R — ретроградность", C_RETRO),
    ]
    for i, (label, col) in enumerate(legend):
        rx = col_right + (i%2)*(col_w/2+2)
        ry = ay - (i//2)*13
        c.setFillColor(col); c.circle(rx+3, ry+2, 2.5, fill=1, stroke=0)
        c.setFillColor(C_TEXT); c.setFont("Helvetica", 7)
        c.drawString(rx+9, ry-1, label)

    c.restoreState()
    draw_page_number(c, 2, 3)


# ══════════════════════════════════════════════════════════
# PAGE 3: INTERPRETATION
# ══════════════════════════════════════════════════════════

def draw_interpretation_page(c, data):
    c.saveState()
    c.setFillColor(C_BG); c.rect(0, 0, W, H, fill=1, stroke=0)
    draw_nebula(c, W*0.5, H*0.5, 250, 300, C_ACCENT, alpha=0.03)
    draw_starfield(c, seed=99, count=100)

    margin = 12*mm
    draw_ornament_border(c, margin, margin, W-2*margin, H-2*margin, C_GOLD, lw=0.6)
    o = margin+4
    for cx2, cy2 in [(o,o),(W-o,o),(o,H-o),(W-o,H-o)]:
        draw_corner_ornament(c, cx2, cy2, 6, angle_offset=45)

    c.setFillColor(C_GOLD2); c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(W/2, H-margin-10, "ИНТЕРПРЕТАЦИЯ НАТАЛЬНОЙ КАРТЫ")
    draw_divider(c, margin+10, H-margin-18, W-2*margin-20)

    body_style = ParagraphStyle(
        "body", fontName="Helvetica", fontSize=8, leading=13,
        textColor=C_TEXT, alignment=TA_JUSTIFY, spaceAfter=4,
    )

    sections = {
        "general":      "✦  Общий портрет личности",
        "career":       "✦  Карьера и призвание",
        "relationships":"✦  Отношения и партнёрство",
        "spirituality": "✦  Духовное развитие",
    }

    col_x = margin+10
    col_w = W-2*margin-20
    iy = H-margin-34

    for key, title in sections.items():
        text = data["interpretation"].get(key, "")
        if not text or iy < margin+40:
            break

        section_header(c, col_x, iy, title, col_w)
        iy -= 20

        para = Paragraph(text, body_style)
        pw, ph = para.wrap(col_w, iy-margin-20)
        para.drawOn(c, col_x, iy-ph)
        iy -= ph+12

        draw_divider(c, col_x+col_w*0.3, iy,
                     col_w*0.4, colors.Color(C_GOLD.red, C_GOLD.green, C_GOLD.blue, alpha=0.35))
        iy -= 14

    c.setFillColor(C_MUTED); c.setFont("Helvetica", 6.5)
    c.drawCentredString(W/2, margin+6,
        "Данный документ носит ознакомительный характер. Астрология — язык символов и архетипов.")

    c.restoreState()
    draw_page_number(c, 3, 3)


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def generate(output_path="natal_chart.pdf", data=None):
    if data is None:
        data = CHART_DATA
    c = canvas.Canvas(output_path, pagesize=A4)
    c.setTitle(f"Натальная карта — {data['name']}")
    c.setAuthor("Astrea Timeline")
    draw_cover(c, data)
    c.showPage()
    draw_data_page(c, data)
    c.showPage()
    draw_interpretation_page(c, data)
    c.showPage()
    c.save()
    print(f"PDF saved: {output_path}")


if __name__ == "__main__":
    generate("/mnt/user-data/outputs/natal_chart.pdf")
