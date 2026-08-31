"""Share router — публичные ссылки на карты и PNG-карточки транзитов.

Endpoints:
  GET  /share/{token}           — HTML с OG-мета-тегами (превью в мессенджерах)
  GET  /share/{token}/card.png  — PNG 1200×630 для Stories
  POST /api/v1/charts/{id}/share — генерация / обновление public_token
"""
from __future__ import annotations

import io
import json
import logging
import os
import secrets
import textwrap
from datetime import date as date_type, timedelta
from backend.time_utils import utcnow
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from backend.auth.rate_limits import share_card_key
from backend.database import get_db
from backend.limiter import limiter
from backend.models import NatalChart
from backend.auth.dependencies import get_current_user
from backend.redis_client import get_redis

logger = logging.getLogger("astro.share")

router = APIRouter(tags=["share"])

APP_URL = os.getenv("APP_URL", "https://astreatime.ru")

# ── TTL публичных токенов шаринга ─────────────────────────────────────────────
# Срок живёт в natal_charts.public_token_expires_at. Раньше он хранился только в
# Redis, и проверка при недоступном кэше пропускала запрос (fail-open).
# NULL в колонке = бессрочная legacy-ссылка, выданная до миграции 041.
SHARE_TTL_SECONDS = 90 * 24 * 3600


def _ensure_chart_not_expired(chart: NatalChart) -> None:
    """Срок ссылки из БД. NULL = legacy-ссылка без срока (не ломаем старые).

    Проверка именно в БД, а не только в Redis: прежняя реализация при недоступном
    кэше молча пропускала запрос (fail-open), то есть истёкшие ссылки снова
    открывались вместе с падением Redis.
    """
    expires_at = getattr(chart, "public_token_expires_at", None)
    if expires_at is not None and expires_at < utcnow():
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


_QUOTE_TTL = 30 * 24 * 3600  # 30 дней


async def _get_share_quote(
    token: str,
    sun_sign: str,
    moon_sign: str,
    asc_sign: str,
) -> str:
    """Возвращает юмористическую фразу из кэша или генерирует через LLM."""
    redis = get_redis()
    cache_key = f"share:quote:v2:{token}"

    try:
        cached = await redis.get(cache_key)
        if cached:
            return cached.decode("utf-8") if isinstance(cached, bytes) else cached
    except Exception as exc:
        logger.warning("share quote cache get failed: %s", exc)

    # Генерируем через DeepSeek (дешевле GPT-4o, достаточно для юмора)
    parts = []
    if sun_sign:
        parts.append(f"Солнце в {sun_sign}")
    if moon_sign:
        parts.append(f"Луна в {moon_sign}")
    if asc_sign:
        parts.append(f"Асцендент в {asc_sign}")
    combo = ", ".join(parts) if parts else "неизвестная карта"

    prompt = (
        f"Натальная карта: {combo}.\n"
        "Напиши ровно 2 коротких законченных предложения (вместе не больше 25 слов) — "
        "смешное хвастовство от первого лица, с самоиронией. "
        "Каждое предложение доведи до конца и поставь точку. "
        "Без вступлений и пояснений, только сами предложения. "
        "Пример стиля: «Мой мозг работает в пяти измерениях, а вы пока застряли в трёх. "
        "Зато когда я разбогатею, вы все сможете гордиться, что терпеливо кивали.»"
    )

    quote = ""
    try:
        import httpx as _httpx
        from backend.config import get_settings as _get_settings
        _settings = _get_settings()
        async with _httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {_settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 120,
                    "temperature": 0.9,
                    "stream": False,
                    # 20.08.2026: третье место, вызывающее DeepSeek — see
                    # interpretation/deepseek.py и interpretation/rag_router.py.
                    # Модель здесь другая (deepseek-chat, не V4), но поле
                    # безвредно, если reasoning неприменим, и защищает на
                    # случай смены модели на V4-совместимую.
                    "thinking": {"type": "disabled"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            quote = data["choices"][0]["message"]["content"].strip()
            # оставляем не больше 2 законченных предложений
            import re as _re
            sentences = [s.strip() for s in _re.findall(r"[^.!?]+[.!?]+", quote)]
            if sentences:
                quote = " ".join(sentences[:2]).strip()
            # гарантируем завершающий знак, если ответ оборвался
            if quote and quote[-1] not in ".!?":
                quote += "."
    except Exception as exc:
        logger.error("share quote LLM failed: %s", exc)
        quote = f"С {combo} скучно точно не бывает — я это гарантирую. Астрология предупреждала, но кто её слушает!"

    try:
        await redis.set(cache_key, quote, ex=_QUOTE_TTL)
    except Exception as exc:
        logger.warning("share quote cache set failed: %s", exc)

    return quote


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
    """Генерирует public_token для карты. Повторный вызов возвращает тот же токен,
    пока он не истёк — не продлевая при этом срок и не выдавая новый.
    """
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    # Allow: own chart OR anonymous chart (user_id=None)
    if chart.user_id is not None and chart.user_id != user.id:
        raise HTTPException(status_code=404, detail="Chart not found")

    # Новый токен — только если его нет вообще или прежний уже истёк. Живой
    # токен возвращаем как есть, без продления: иначе ссылка становится
    # вечной, пока по ней хоть изредка «делятся» повторно — ровно то, чем
    # раньше был этот же безусловный сдвиг expires_at на каждый вызов.
    token_expired = (
        chart.public_token_expires_at is not None
        and chart.public_token_expires_at <= utcnow()
    )
    if not chart.public_token or token_expired:
        chart.public_token = secrets.token_urlsafe(32)
        chart.public_token_expires_at = utcnow() + timedelta(seconds=SHARE_TTL_SECONDS)

    if share_name:
        chart.share_name = share_name[:100]

    db.commit()
    db.refresh(chart)

    # share_url ведёт на /share/{token} — серверный HTML с OG-тегами (share_page
    # ниже), а НЕ на SPA-маршрут /chart/share/{token}. Разница видна только в
    # мессенджере: краулер JS не исполняет, поэтому с SPA-пути он забирал общие
    # теги из index.html и превью выходило безликим у всех карт сразу. На
    # /share/{token} он получает имя, знаки Солнца/Луны/Асцендента и картинку
    # 1080x1920. Человека эта страница через 3 секунды сама уводит на SPA, где
    # рисуется настоящая карта, так что конечный экран прежний.
    #
    # Побочно закрывает расхождение с robots.txt: /chart/ там в Disallow, то
    # есть ссылка, которую мы сами же выдаём на шаринг, была запрещена к обходу.
    #
    # Оба пути были заведены одним коммитом 695a9b2, и share_url с самого начала
    # указывал мимо страницы, ради которой всё это писалось.
    return {
        "share_url": f"{APP_URL}/share/{chart.public_token}",
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
    _ensure_chart_not_expired(chart)
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


# Аварийный путь у /share/{token} раньше отдавал голый JSON исключения
# ({"detail": "..."}) — человек, перешедший по ссылке из мессенджера, видел
# текст ошибки вместо страницы. На старом SPA-пути тот же случай выглядел
# прилично («Карта не найдена» + кнопка на главную). Отдаём HTML в том же
# тёмном стиле, что у заставки, вместо HTTPException — но статус 404
# сохраняем: это не тот случай, что нужно чинить общим обработчиком
# HTTPException в main.py (он тронул бы всё приложение), здесь нужен
# ровно один путь.
def _share_not_found_html() -> HTMLResponse:
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <meta name="robots" content="noindex, nofollow"/>
  <title>Ссылка недействительна · Astrea Timeline</title>
</head>
<body style="background:#0e0c1a;color:#fff;font-family:sans-serif;
             display:flex;align-items:center;justify-content:center;
             height:100vh;margin:0;">
  <div style="text-align:center;max-width:480px;padding:0 24px;">
    <div style="font-size:32px;margin-bottom:12px;">☽ ✦ ☾</div>
    <div style="font-size:20px;font-weight:700;color:#c9a8ff;">Astrea Timeline</div>
    <p style="color:#9080b0;font-size:15px;line-height:1.6;margin:20px 0 24px;">Ссылка больше не действует.</p>
    <a href="/" style="
      display:inline-block;background:linear-gradient(135deg,#8b5cf6,#a855f7);
      color:#fff;text-decoration:none;border-radius:14px;
      padding:14px 32px;font-size:16px;font-weight:600;
      font-family:inherit;letter-spacing:0.02em;">
      На главную
    </a>
  </div>
</body>
</html>"""
    return HTMLResponse(
        content=html,
        status_code=404,
        headers={
            "Content-Security-Policy": (
                "default-src 'none'; img-src 'self' https:; "
                "style-src 'unsafe-inline'; "
                "base-uri 'none'; frame-ancestors 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.get("/share/{token}", response_class=HTMLResponse)
async def share_page(token: str, db: Session = Depends(get_db)):
    """Публичная страница карты с Open Graph мета-тегами.

    Мессенджеры читают OG-теги и показывают красивое превью.
    После этого JS редиректит пользователя на SPA.
    """
    chart = db.query(NatalChart).filter(NatalChart.public_token == token).first()
    if not chart:
        return _share_not_found_html()
    try:
        _ensure_chart_not_expired(chart)
    except HTTPException:
        return _share_not_found_html()

    planets = chart.planets or []
    sun = _sign_label(planets, "Sun")
    moon = _sign_label(planets, "Moon")
    asc_data = chart.ascendant or {}
    asc_sign = asc_data.get("sign", "")
    asc_label = f"{SIGN_EMOJI.get(asc_sign, '')} {SIGN_RU.get(asc_sign, asc_sign)}" if asc_sign else ""

    sun_sign_ru  = SIGN_RU.get((_get_planet(planets, "Sun") or {}).get("sign", ""), "")
    moon_sign_ru = SIGN_RU.get((_get_planet(planets, "Moon") or {}).get("sign", ""), "")
    asc_sign_ru  = SIGN_RU.get(asc_sign, "")
    quote = await _get_share_quote(token, sun_sign_ru, moon_sign_ru, asc_sign_ru)
    safe_quote = escape(quote, quote=True)

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
    #
    # 31.08.2026: раньше title был `f"Натальная карта · {chart.share_name or
    # 'Натальная карта'}"` — при отсутствии share_name (а его сегодня не
    # передаёт НИ ОДИН вызывающий на фронте, ни один POST .../share не шлёт
    # этот параметр) заголовок дублировался в «Натальная карта · Натальная
    # карта». chart.name (реальное имя человека) сюда специально не
    # подставляем — это отдельное приватное поле, share_name существует
    # именно как его opt-in замена для публичной страницы (комментарий у
    # поля в models.py). Вместо дубля — солнечный знак, который и так уже
    # считается для описания ниже: он публичный, узнаваемый и не пустой
    # почти никогда (нет знака только если Sun не нашёлся в planets).
    title_suffix = chart.share_name or sun or None
    og_title = (
        escape(f"Натальная карта · {title_suffix}", quote=True)
        if title_suffix else "Натальная карта"
    )
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
  <!-- Персональные данные (имя, знаки) третьего лица, ссылка живёт 90 дней —
       индексировать нельзя. robots.txt при этом не трогаем: Disallow запретил
       бы скачивание страницы и убил бы превью в мессенджерах, ради которого
       она и существует. noindex разрешает скачать, запрещает индексировать. -->
  <meta name="robots" content="noindex, nofollow"/>

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
  <div style="text-align:center;max-width:480px;padding:0 24px;">
    <div style="font-size:32px;margin-bottom:12px;">☽ ✦ ☾</div>
    <div style="font-size:20px;font-weight:700;color:#c9a8ff;">Astrea Timeline</div>
    <p style="color:#9080b0;font-size:15px;line-height:1.6;margin:20px 0 24px;">{safe_quote}</p>
    <button onclick="shareCard()" style="
      background:linear-gradient(135deg,#8b5cf6,#a855f7);
      color:#fff;border:none;border-radius:14px;
      padding:14px 32px;font-size:16px;font-weight:600;
      cursor:pointer;font-family:inherit;letter-spacing:0.02em;">
      ✦ Поделиться картой
    </button>
  </div>
  <script>
    const SHARE_URL = "{spa_url}";
    const CARD_URL  = "{og_image}";
    async function shareCard() {{
      if (navigator.share) {{
        try {{
          await navigator.share({{
            title: "{og_title}",
            text: "{safe_quote}",
            url: SHARE_URL,
          }});
          return;
        }} catch (e) {{ /* отменили — падаем в fallback */ }}
      }}
      try {{ await navigator.clipboard.writeText(SHARE_URL); }}
      catch (e) {{ }}
      alert("Ссылка скопирована!");
    }}
    setTimeout(() => {{ window.location.href = SHARE_URL; }}, 3000);
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


# ── PNG карточка 1080×1920 (формат Stories) ───────────────────────────────────

@router.get("/share/{token}/card.png")
@limiter.limit("30/minute", key_func=share_card_key)
async def share_card_png(request: Request, token: str, db: Session = Depends(get_db)):
    """Генерирует вертикальную PNG-карточку 1080×1920 для Stories / мессенджеров.

    Лимит по IP: ручка публичная, рендерит изображение и на первый запрос по
    каждому токену дополнительно ходит в LLM за подписью.
    """
    chart = db.query(NatalChart).filter(NatalChart.public_token == token).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    _ensure_chart_not_expired(chart)

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

    quote = await _get_share_quote(token, sun_sign, moon_sign, asc_sign)

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
    font_quote  = load_font(32, bold=False)

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

    # ── юмористическая фраза (по центру свободной зоны между местом и CTA) ──
    bar_h = 150
    quote_lines = textwrap.wrap(quote, width=32)
    line_h = 52
    quote_block_h = len(quote_lines) * line_h
    zone_top = info_y + 60          # сразу под датой/местом
    zone_bottom = H - bar_h - 60    # отступ над CTA-полоской
    quote_y = zone_top + max(0, (zone_bottom - zone_top - quote_block_h) // 2)
    for line in quote_lines:
        draw.text((ML, quote_y), line, font=font_quote, fill=C_DARK)
        quote_y += line_h

    # ── CTA-полоска внизу ──
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
