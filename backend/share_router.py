"""Share router — публичные ссылки на карты и PNG-карточки транзитов.

Endpoints:
  GET  /share/{token}           — HTML с OG-мета-тегами (превью в мессенджерах)
  GET  /share/{token}/card.png  — PNG 1200×630 для Stories
  POST /api/v1/charts/{id}/share — генерация / обновление public_token
"""
from __future__ import annotations

import io
import logging
import os
import secrets
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import NatalChart
from backend.auth.dependencies import get_current_user

logger = logging.getLogger("astro.share")

router = APIRouter(tags=["share"])

APP_URL = os.getenv("APP_URL", "https://astreatime.ru")

# ── знаки ────────────────────────────────────────────────────────────────────
SIGN_RU = {
    "Aries": "Овен", "Taurus": "Телец", "Gemini": "Близнецы",
    "Cancer": "Рак", "Leo": "Лев", "Virgo": "Дева",
    "Libra": "Весы", "Scorpio": "Скорпион", "Sagittarius": "Стрелец",
    "Capricorn": "Козерог", "Aquarius": "Водолей", "Pisces": "Рыбы",
}
SIGN_EMOJI = {
    "Aries": "♈", "Taurus": "♉", "Gemini": "♊", "Cancer": "♋",
    "Leo": "♌", "Virgo": "♍", "Libra": "♎", "Scorpio": "♏",
    "Sagittarius": "♐", "Capricorn": "♑", "Aquarius": "♒", "Pisces": "♓",
}


def _get_planet(planets: list[dict], name: str) -> dict | None:
    return next((p for p in planets if p.get("name") == name), None)


def _sign_label(planets: list[dict], name: str) -> str:
    p = _get_planet(planets, name)
    if not p:
        return ""
    sign = p.get("sign", "")
    emoji = SIGN_EMOJI.get(sign, "")
    ru = SIGN_RU.get(sign, sign)
    return f"{emoji} {ru}"


# ── генерация токена ──────────────────────────────────────────────────────────

@router.post("/api/v1/charts/{chart_id}/share")
async def create_share_link(
    chart_id: str,
    share_name: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Генерирует public_token для карты. Повторный вызов возвращает тот же токен."""
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    # Allow: own chart OR anonymous chart (user_id=None)
    if chart.user_id is not None and chart.user_id != user.id:
        raise HTTPException(status_code=404, detail="Chart not found")

    if not chart.public_token:
        chart.public_token = secrets.token_urlsafe(32)

    if share_name:
        chart.share_name = share_name[:100]

    db.commit()
    db.refresh(chart)

    return {
        "share_url": f"{APP_URL}/chart/share/{chart.public_token}",
        "card_url":  f"{APP_URL}/share/{chart.public_token}/card.png",
        "token":     chart.public_token,
    }


# ── HTML с OG-тегами ──────────────────────────────────────────────────────────

@router.get("/api/v1/share/{token}/data")
async def share_data(token: str, db: Session = Depends(get_db)):
    """JSON-данные карты для SPA SharePage."""
    chart = db.query(NatalChart).filter(NatalChart.public_token == token).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return {
        "share_name":  chart.share_name,
        "birth_date":  chart.birth_date,
        "birth_place": chart.birth_place,
        "time_unknown": chart.time_unknown,
        "planets":     chart.planets,
        "houses":      chart.houses,
        "aspects":     chart.aspects,
        "ascendant":   chart.ascendant,
        "midheaven":   chart.midheaven,
    }


@router.get("/share/{token}", response_class=HTMLResponse)
async def share_page(token: str, db: Session = Depends(get_db)):
    """Публичная страница карты с Open Graph мета-тегами.

    Мессенджеры читают OG-теги и показывают красивое превью.
    После этого JS редиректит пользователя на SPA.
    """
    chart = db.query(NatalChart).filter(NatalChart.public_token == token).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    planets = chart.planets or []
    name = chart.share_name or "Натальная карта"
    sun = _sign_label(planets, "Sun")
    moon = _sign_label(planets, "Moon")
    asc_data = chart.ascendant or {}
    asc_sign = asc_data.get("sign", "")
    asc_label = f"{SIGN_EMOJI.get(asc_sign, '')} {SIGN_RU.get(asc_sign, asc_sign)}" if asc_sign else ""

    description_parts = []
    if sun:
        description_parts.append(f"☀ Солнце: {sun}")
    if moon:
        description_parts.append(f"☽ Луна: {moon}")
    if asc_label:
        description_parts.append(f"↑ Асцендент: {asc_label}")
    description = " · ".join(description_parts) or "Персональный астрологический анализ"

    og_title       = f"Натальная карта · {name}"
    og_description = description
    og_image       = f"{APP_URL}/share/{token}/card.png"
    og_url         = f"{APP_URL}/chart/share/{token}"
    spa_url        = f"{APP_URL}/chart/share/{token}"

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{og_title}</title>

  <!-- Open Graph -->
  <meta property="og:type"        content="website"/>
  <meta property="og:url"         content="{og_url}"/>
  <meta property="og:title"       content="{og_title}"/>
  <meta property="og:description" content="{og_description}"/>
  <meta property="og:image"       content="{og_image}"/>
  <meta property="og:image:width"  content="1200"/>
  <meta property="og:image:height" content="630"/>
  <meta property="og:site_name"   content="Astrea Timeline"/>

  <!-- Twitter Card -->
  <meta name="twitter:card"        content="summary_large_image"/>
  <meta name="twitter:title"       content="{og_title}"/>
  <meta name="twitter:description" content="{og_description}"/>
  <meta name="twitter:image"       content="{og_image}"/>

  <meta name="description" content="{og_description}"/>
</head>
<body style="background:#0e0c1a;color:#fff;font-family:sans-serif;
             display:flex;align-items:center;justify-content:center;
             height:100vh;margin:0;">
  <div style="text-align:center;">
    <div style="font-size:32px;margin-bottom:12px;">☽ ✦ ☾</div>
    <div style="font-size:20px;font-weight:700;color:#c9a8ff;">Astrea Timeline</div>
    <p style="color:#9080b0;margin:12px 0;">Переход к карте...</p>
  </div>
  <script>
    window.location.href = "{spa_url}";
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


# ── PNG карточка 1200×630 ─────────────────────────────────────────────────────

@router.get("/share/{token}/card.png")
async def share_card_png(token: str, db: Session = Depends(get_db)):
    """Генерирует PNG 1200×630 для Stories / мессенджеров."""
    chart = db.query(NatalChart).filter(NatalChart.public_token == token).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise HTTPException(status_code=503, detail="Pillow not installed")

    planets = chart.planets or []
    name = chart.share_name or "Натальная карта"
    sun    = _get_planet(planets, "Sun")
    moon   = _get_planet(planets, "Moon")
    asc    = chart.ascendant or {}

    sun_sign   = SIGN_RU.get(sun.get("sign", ""), "")   if sun  else ""
    moon_sign  = SIGN_RU.get(moon.get("sign", ""), "")  if moon else ""
    asc_sign   = SIGN_RU.get(asc.get("sign", ""), "")

    sun_emoji  = SIGN_EMOJI.get(sun.get("sign", ""), "")   if sun  else ""
    moon_emoji = SIGN_EMOJI.get(moon.get("sign", ""), "")  if moon else ""
    asc_emoji  = SIGN_EMOJI.get(asc.get("sign", ""), "")

    today_str = date_type.today().strftime("%-d %B %Y")

    W, H = 1200, 630
    img = Image.new("RGB", (W, H), color=(14, 12, 26))
    draw = ImageDraw.Draw(img)

    # ── градиентный фон (простой) ──
    for y in range(H):
        ratio = y / H
        r = int(14  + (45  - 14)  * ratio)
        g = int(12  + (27  - 12)  * ratio)
        b = int(26  + (78  - 26)  * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # ── декоративные круги ──
    draw.ellipse([-80, -80, 280, 280], outline=(112, 80, 200, 60), width=1)
    draw.ellipse([-140, -140, 340, 340], outline=(112, 80, 200, 30), width=1)
    draw.ellipse([920, 350, 1380, 810], outline=(192, 96, 160, 40), width=1)

    # ── шрифты ──
    CJK_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    def load_font(size: int) -> ImageFont.FreeTypeFont:
        for path in [CJK_FONT, FALLBACK]:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    font_logo   = load_font(22)
    font_title  = load_font(52)
    font_label  = load_font(20)
    font_planet = load_font(34)
    font_small  = load_font(18)

    # ── логотип ──
    draw.text((60, 44), "☽ ✦ ☾", font=font_logo, fill=(201, 168, 255))
    draw.text((60, 74), "ASTREA TIMELINE", font=font_small, fill=(128, 100, 180))

    # ── имя / заголовок ──
    draw.text((60, 140), name, font=font_title, fill=(240, 230, 255))

    # ── планеты ──
    y_row = 260
    pairs = [
        (f"☀ Солнце", f"{sun_emoji} {sun_sign}" if sun_sign else "—"),
        (f"☽ Луна",   f"{moon_emoji} {moon_sign}" if moon_sign else "—"),
        (f"↑ Асц.",   f"{asc_emoji} {asc_sign}" if asc_sign else "—"),
    ]
    col_x = [60, 420, 780]
    for i, (label, value) in enumerate(pairs):
        x = col_x[i]
        # разделитель
        draw.rectangle([x, y_row - 8, x + 280, y_row - 7], fill=(112, 80, 200, 80))
        draw.text((x, y_row),      label, font=font_label,  fill=(160, 130, 220))
        draw.text((x, y_row + 30), value, font=font_planet, fill=(240, 220, 255))

    # ── дата + birth_place ──
    place = (chart.birth_place or "")[:40]
    draw.text((60, 420), chart.birth_date or "", font=font_small, fill=(100, 85, 150))
    if place:
        draw.text((60, 446), place, font=font_small, fill=(100, 85, 150))

    # ── CTA-полоска внизу ──
    draw.rectangle([0, H - 80, W, H], fill=(45, 27, 78))
    draw.text((60, H - 56), "astreatime.ru · Узнай свою карту →",
              font=font_small, fill=(201, 168, 255))
    draw.text((W - 300, H - 56), today_str, font=font_small, fill=(128, 100, 180))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
