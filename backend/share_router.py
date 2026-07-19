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
import time
from datetime import date as date_type
from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import NatalChart
from backend.auth.dependencies import get_current_user
from backend.redis_client import get_redis

logger = logging.getLogger("astro.share")

router = APIRouter(tags=["share"])

APP_URL = os.getenv("APP_URL", "https://astreatime.ru")

# ── TTL публичных токенов шаринга ─────────────────────────────────────────────
# Срок хранится в Redis (без миграции БД). Токены, созданные до включения TTL,
# не имеют ключа и считаются бессрочными (legacy) — чтобы не ломать старые ссылки.
SHARE_TTL_SECONDS = 90 * 24 * 3600


async def _register_share_token(token: str) -> None:
    try:
        expiry = int(time.time()) + SHARE_TTL_SECONDS
        # ключ живёт дольше логического срока, чтобы отличать «истёк» от «legacy»
        await get_redis().setex(f"share:exp:{token}", SHARE_TTL_SECONDS + 30 * 24 * 3600, str(expiry))
    except Exception as exc:  # noqa: BLE001
        logger.error("share token TTL register failed: %s", exc)


async def _ensure_not_expired(token: str) -> None:
    try:
        raw = await get_redis().get(f"share:exp:{token}")
    except Exception as exc:  # noqa: BLE001
        logger.error("share token TTL check failed (fail-open): %s", exc)
        return
    if raw is None:
        return  # legacy-токен без срока
    if int(raw) < int(time.time()):
        raise HTTPException(status_code=404, detail="Share link expired")

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
    await _register_share_token(chart.public_token)

    return {
        "share_url": f"{APP_URL}/chart/share/{chart.public_token}",
        "card_url":  f"{APP_URL}/share/{chart.public_token}/card.png",
        "token":     chart.public_token,
    }


# ── HTML с OG-тегами ──────────────────────────────────────────────────────────

@router.get("/api/v1/share/{token}/data")
async def share_data(token: str, db: Session = Depends(get_db)):
    """JSON-данные карты для SPA SharePage."""
    await _ensure_not_expired(token)
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
    await _ensure_not_expired(token)
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

    # XSS: любое пользовательское значение (share_name) экранируется перед
    # вставкой в HTML/мета-теги. Токен — из secrets.token_urlsafe (безопасный
    # алфавит), но экранируем и его для единообразия.
    safe_name = escape(name, quote=True)
    og_title       = f"Натальная карта · {safe_name}"
    og_description = escape(description, quote=True)
    safe_token     = escape(token, quote=True)
    og_image       = f"{APP_URL}/share/{safe_token}/card.png"
    og_url         = f"{APP_URL}/chart/share/{safe_token}"
    spa_url        = f"{APP_URL}/chart/share/{safe_token}"

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
    return HTMLResponse(
        content=html,
        headers={
            "Content-Security-Policy": (
                "default-src 'none'; img-src 'self' https:; "
                "style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                "base-uri 'none'; frame-ancestors 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )


# ── PNG карточка 1200×630 ─────────────────────────────────────────────────────

@router.get("/share/{token}/card.png")
async def share_card_png(token: str, db: Session = Depends(get_db)):
    """Генерирует PNG 1200×630 для Stories / мессенджеров."""
    await _ensure_not_expired(token)
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

# ── PNG карточка 1080×1920 (формат Stories) ───────────────────────────────────

@router.get("/share/{token}/card.png")
async def share_card_png(token: str, db: Session = Depends(get_db)):
    """Генерирует вертикальную PNG-карточку 1080×1920 для Stories / мессенджеров."""
    await _ensure_not_expired(token)
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

    W, H = 1080, 1920
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # ── фон: диагональный градиент как на лендинге ──
    # linear-gradient(135deg, #f8f0ff 0%, #f0e8ff 20%, #fce8f4 45%, #e8f0ff 70%, #f0f8ff 100%)
    stops = [
        (0.00, (0xF8, 0xF0, 0xFF)),
        (0.20, (0xF0, 0xE8, 0xFF)),
        (0.45, (0xFC, 0xE8, 0xF4)),
        (0.70, (0xE8, 0xF0, 0xFF)),
        (1.00, (0xF0, 0xF8, 0xFF)),
    ]

    def gradient_color(t: float) -> tuple[int, int, int]:
        t = max(0.0, min(1.0, t))
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0) if t1 > t0 else 0
                return tuple(int(c0[k] + (c1[k] - c0[k]) * f) for k in range(3))
        return stops[-1][1]

    diag = W + H
    small_w, small_h = 2, H
    tmp = Image.new("RGB", (small_w, small_h))
    tdraw = ImageDraw.Draw(tmp)
    for y in range(small_h):
        tdraw.point((0, y), fill=gradient_color((0 + y) / diag))
        tdraw.point((1, y), fill=gradient_color((W + y) / diag))
    img = tmp.resize((W, H))
    draw = ImageDraw.Draw(img)

    # ── декоративные дуги (полупрозрачные, как на лендинге) ──
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.ellipse([-260, -260, 520, 520], outline=(139, 92, 246, 70), width=2)
    odraw.ellipse([-360, -360, 620, 620], outline=(139, 92, 246, 35), width=2)
    odraw.ellipse([680, 1500, 1400, 2220], outline=(236, 72, 153, 60), width=2)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── шрифт: DejaVu Sans, поддерживает кириллицу и астросимволы, лежит в репо ──
    ASSET_FONT = os.path.join(os.path.dirname(__file__), "assets", "fonts", "DejaVuSans.ttf")
    FONT_CANDIDATES_BOLD = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ASSET_FONT,
    ]
    FONT_CANDIDATES_REGULAR = [
        ASSET_FONT,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        candidates = FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REGULAR
        for path in candidates:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def fit_font(text: str, base_size: int, max_width: int, bold: bool = True, min_size: int = 40):
        size = base_size
        while size > min_size:
            f = load_font(size, bold)
            if draw.textlength(text, font=f) <= max_width:
                return f
            size -= 3
        return load_font(min_size, bold)

    C_PURPLE = (139, 92, 246)
    C_DARK   = (0x1A, 0x12, 0x30)
    C_MUTED  = (0x6B, 0x68, 0x85)
    ML = 90
    CONTENT_W = W - ML * 2

    font_logo   = load_font(28, bold=True)
    font_title  = fit_font(name, 72, CONTENT_W, bold=True)
    font_label  = load_font(26, bold=False)
    font_planet = load_font(58, bold=True)
    font_small  = load_font(28, bold=False)

    # ── логотип ──
    draw.text((ML, 80), "ASTREA TIMELINE", font=font_logo, fill=C_PURPLE)

    # ── имя / заголовок ──
    draw.text((ML, 150), name, font=font_title, fill=C_DARK)

    # ── планеты (стек вертикально) ──
    y_row = 420
    row_h = 210
    pairs = [
        ("Солнце",    f"{sun_emoji} {sun_sign}"   if sun_sign   else "—"),
        ("Луна",      f"{moon_emoji} {moon_sign}" if moon_sign  else "—"),
        ("Асцендент", f"{asc_emoji} {asc_sign}"   if asc_sign   else "—"),
    ]
    for label, value in pairs:
        draw.rectangle([ML, y_row - 14, ML + CONTENT_W, y_row - 11], fill=C_PURPLE)
        draw.text((ML, y_row), label, font=font_label, fill=C_PURPLE)
        draw.text((ML, y_row + 42), value, font=font_planet, fill=C_DARK)
        y_row += row_h

    # ── дата + место ──
    place = (chart.birth_place or "")[:60]
    birth = chart.birth_date or ""
    info_y = y_row + 20
    if birth:
        draw.text((ML, info_y), birth, font=font_small, fill=C_MUTED)
        info_y += 40
    if place:
        draw.text((ML, info_y), place, font=font_small, fill=C_MUTED)

    # ── CTA-полоска внизу ──
    bar_h = 150
    draw.rectangle([0, H - bar_h, W, H], fill=C_DARK)
    draw.text((ML, H - bar_h // 2 - 44), "astreatime.ru", font=font_small, fill=(0xEA, 0xE0, 0xFF))
    draw.text((ML, H - bar_h // 2 - 4), "Узнай свою карту", font=font_small, fill=(0xC9, 0xA8, 0xFF))
    draw.text((ML, H - bar_h // 2 + 46), today_str, font=load_font(22), fill=(0xA0, 0x90, 0xC0))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
