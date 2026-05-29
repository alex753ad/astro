"""Email service via Resend API — Astrea Timeline.

Templates:
  send_welcome_email        — сразу после регистрации
  send_retention_day2       — день 2, актуальный транзит
  send_retention_day7       — день 7, апгрейд-нудж
  send_trial_ending_email   — за 2 дня до конца триала
  send_weekly_digest_email  — еженедельный дайджест транзитов
  send_transit_alert_email  — точечное уведомление о важном транзите
"""

from __future__ import annotations
import logging
import os
import httpx

logger = logging.getLogger("astro.email")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL     = os.getenv("FROM_EMAIL", "noreply@astreatime.ru")
APP_URL        = os.getenv("APP_URL", "https://astreatime.ru")

# ───────────────────────────── base template ─────────────────────────────────

def _base(title: str, preview: str, body: str) -> str:
    """Универсальный базовый шаблон: хедер + контент + футер."""
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{title}</title>
  <meta name="x-apple-message-highlight-color" content="#9060C8"/>
</head>
<body style="margin:0;padding:0;background:#0e0c1a;font-family:'Segoe UI',Arial,sans-serif;">
  <!-- preview text -->
  <span style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{preview}</span>

  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0e0c1a;">
    <tr><td align="center" style="padding:32px 16px;">
      <table width="560" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;width:100%;">

        <!-- HEADER -->
        <tr>
          <td style="background:linear-gradient(135deg,#2d1b4e 0%,#1a1030 100%);
                     border-radius:16px 16px 0 0;padding:32px 40px;text-align:center;">
            <div style="font-size:28px;letter-spacing:4px;margin-bottom:8px;">
              ☽ ✦ ☾
            </div>
            <div style="color:#c9a8ff;font-size:20px;font-weight:700;letter-spacing:1px;">
              Astrea Timeline
            </div>
            <div style="color:rgba(201,168,255,0.55);font-size:12px;margin-top:4px;letter-spacing:2px;">
              АСТРОЛОГИЯ · AI · ТРАНЗИТЫ
            </div>
          </td>
        </tr>

        <!-- BODY -->
        <tr>
          <td style="background:#f8f5ff;padding:36px 40px;border-radius:0 0 16px 16px;">
            {body}

            <!-- FOOTER -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0"
                   style="margin-top:32px;border-top:1px solid #e8e0f4;padding-top:20px;">
              <tr>
                <td style="text-align:center;font-size:11px;color:#a090c0;line-height:1.7;">
                  <a href="{APP_URL}" style="color:#9060C8;text-decoration:none;font-weight:600;">
                    Astrea Timeline
                  </a>
                  &nbsp;·&nbsp;astreatime.ru<br/>
                  <a href="{APP_URL}/unsubscribe" style="color:#b0a0d0;text-decoration:none;">
                    Отписаться
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _btn(text: str, url: str) -> str:
    """Кнопка CTA."""
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="margin:28px 0;">
      <tr><td align="center">
        <a href="{url}"
           style="display:inline-block;background:linear-gradient(135deg,#9060C8,#C060A0);
                  color:#fff;padding:14px 36px;border-radius:12px;
                  text-decoration:none;font-weight:700;font-size:15px;
                  letter-spacing:0.3px;">
          {text}
        </a>
      </td></tr>
    </table>"""


def _h2(text: str) -> str:
    return f'<h2 style="color:#2D2540;font-size:20px;margin:0 0 16px;font-weight:700;">{text}</h2>'


def _p(text: str) -> str:
    return f'<p style="color:#3d3060;font-size:15px;line-height:1.75;margin:0 0 16px;">{text}</p>'


# ───────────────────────────── transport ─────────────────────────────────────

async def _send(to: str, subject: str, html: str) -> bool:
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — skipping email to %s", to)
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={"from": FROM_EMAIL, "to": [to], "subject": subject, "html": html},
            )
            if resp.status_code not in (200, 201):
                logger.error("Resend error %s: %s", resp.status_code, resp.text)
                return False
            return True
    except Exception as e:
        logger.error("Email send failed: %s", e)
        return False


# ───────────────────────────── templates ─────────────────────────────────────

# Инсайты по Солнцу — одно предложение на знак
_SUN_INSIGHTS: dict[str, str] = {
    "Aries":       "Вы рождены действовать первым — ваша энергия заражает и двигает людей вперёд.",
    "Taurus":      "Вы строите надёжное и красивое — терпение и вкус это ваши суперсилы.",
    "Gemini":      "Вы мыслите быстро и умеете находить связи там, где другие видят хаос.",
    "Cancer":      "Вы чувствуете глубже других — и именно это делает вас незаменимым для близких.",
    "Leo":         "Вы рождены светить — ваша щедрость и харизма притягивают людей.",
    "Virgo":       "Вы видите детали, которые меняют всё — ваша точность создаёт настоящее качество.",
    "Libra":       "Вы умеете находить баланс и гармонию — это редкий дар в мире крайностей.",
    "Scorpio":     "Вы видите суть вещей — за вашей интенсивностью стоит невероятная глубина.",
    "Sagittarius": "Вы ищете смысл и горизонт — ваш оптимизм открывает двери там, где другие сдаются.",
    "Capricorn":   "Вы строите на годы вперёд — ваша дисциплина превращает амбиции в реальность.",
    "Aquarius":    "Вы думаете иначе — и именно это делает вас источником идей, которые меняют мир.",
    "Pisces":      "Вы чувствуете невидимое — интуиция и сострадание ваши главные инструменты.",
}

_SIGN_RU: dict[str, str] = {
    "Aries": "Овен", "Taurus": "Телец", "Gemini": "Близнецы",
    "Cancer": "Рак", "Leo": "Лев", "Virgo": "Дева",
    "Libra": "Весы", "Scorpio": "Скорпион", "Sagittarius": "Стрелец",
    "Capricorn": "Козерог", "Aquarius": "Водолей", "Pisces": "Рыбы",
}


def _get_sun_sign(planets: list[dict]) -> str | None:
    """Извлекает знак Солнца из списка планет."""
    for p in planets:
        if p.get("name") == "Sun":
            return p.get("sign")
    return None


async def send_welcome_email(to: str, planets: list[dict] | None = None, name: str | None = None) -> bool:
    """Welcome — отправляется после расчёта первой карты.

    Если planets переданы — включает инсайт по Солнцу.
    """
    greeting = f"Привет, {name}!" if name else "Добро пожаловать в Astrea Timeline ✦"

    if planets:
        sun_sign = _get_sun_sign(planets)
        sun_sign_ru = _SIGN_RU.get(sun_sign, sun_sign) if sun_sign else None
        insight = _SUN_INSIGHTS.get(sun_sign, "") if sun_sign else ""
    else:
        sun_sign_ru = None
        insight = ""

    if sun_sign_ru and insight:
        sun_block = (
            f'<div style="background:#f0ebff;border-left:3px solid #9060C8;border-radius:8px;'
            f'padding:16px 20px;margin:16px 0 24px;">'
            f'  <div style="color:#9060C8;font-size:12px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">'
            f'    ☀ Ваше Солнце · {sun_sign_ru}'
            f'  </div>'
            f'  <div style="color:#2D2540;font-size:15px;line-height:1.7;">{insight}</div>'
            f'</div>'
        )
        subject_line = f"☀ Ваша натальная карта готова — Солнце в {sun_sign_ru}"
        preview = f"Солнце в {sun_sign_ru}: {insight[:60]}..."
    else:
        sun_block = ""
        subject_line = "✨ Добро пожаловать в Astrea Timeline"
        preview = "Ваша натальная карта ждёт — откройте её прямо сейчас"

    body = (
        _h2(greeting)
        + _p("Ваша натальная карта рассчитана. Вот первый инсайт — специально для вас:")
        + sun_block
        + _p("Откройте карту, чтобы увидеть все планеты, дома и AI-интерпретацию.")
        + _btn("✦ Открыть мою карту", APP_URL)
    )
    return await _send(
        to,
        subject_line,
        _base("Ваша карта готова", preview, body),
    )


async def send_retention_day2(to: str, transit_text: str) -> bool:
    """Retention Day 2 — актуальный транзит для карты пользователя."""
    body = (
        _h2("🌙 Ваш транзит на сегодня")
        + f'<div style="background:#f0ebff;border-left:3px solid #9060C8;border-radius:8px;'
          f'padding:16px 20px;margin:0 0 20px;color:#2D2540;font-size:15px;line-height:1.75;">'
          f'{transit_text}</div>'
        + _p("Откройте Astrea Timeline, чтобы увидеть все активные транзиты и AI-интерпретацию.")
        + _btn("Смотреть полный прогноз", APP_URL)
    )
    return await _send(
        to,
        "🌙 Ваш астрологический прогноз на сегодня",
        _base("Прогноз на сегодня", "Персональный транзит по вашей карте", body),
    )


# Обратная совместимость
send_retention_email = send_retention_day2


async def send_retention_day7(to: str, locked_count: int) -> bool:
    """Retention Day 7 — апгрейд-нудж для free-пользователей."""
    body = (
        _h2("⭐ Не пропустите важные периоды")
        + _p(
            f"В ближайший месяц для вашей карты активно "
            f"<strong>{locked_count} транзитов</strong> — периоды, влияющие на карьеру, "
            f"отношения и финансы."
        )
        + _p(
            "С планом <strong>Pro</strong> вы видите полный прогноз и получаете "
            "AI-интерпретацию каждого периода."
        )
        + _btn("Попробовать Pro", f"{APP_URL}/pricing")
    )
    return await _send(
        to,
        f"⭐ Вы пропускаете {locked_count} активных транзитов",
        _base("Важные транзиты закрыты", "Откройте полный прогноз на месяц", body),
    )


# Обратная совместимость
send_upgrade_nudge_email = send_retention_day7


async def send_trial_ending_email(to: str, days_left: int, plan: str = "Pro") -> bool:
    """Trial Ending — за 1–2 дня до окончания триала."""
    days_str = "завтра" if days_left == 1 else f"через {days_left} дня"
    body = (
        _h2(f"⏳ Ваш триал заканчивается {days_str}")
        + _p(
            f"Вы пользуетесь <strong>Astrea Timeline {plan}</strong>. "
            f"Триальный период заканчивается {days_str}."
        )
        + _p(
            "Чтобы сохранить доступ к полным транзитам, AI-интерпретациям и еженедельным "
            "дайджестам — продлите подписку сейчас."
        )
        + f'<div style="background:#fff8e1;border:1px solid #ffc107;border-radius:10px;'
          f'padding:14px 18px;margin:0 0 20px;color:#5d4000;font-size:14px;line-height:1.6;">'
          f'💡 Подпишитесь сегодня и получите первый месяц без перебоев в прогнозах.</div>'
        + _btn(f"Продолжить {plan}", f"{APP_URL}/pricing")
    )
    return await _send(
        to,
        f"⏳ Ваш триал Astrea Timeline заканчивается {days_str}",
        _base("Триал заканчивается", f"Продлите доступ к Pro — осталось {days_left} дн.", body),
    )


async def send_weekly_digest_email(
    to: str,
    week_label: str,
    highlights: list[dict],
) -> bool:
    """Weekly Digest — топ-3 транзита на предстоящую неделю.

    highlights: [{"date": "2 июня", "planet": "Венера", "aspect": "трин", "natal": "Луна",
                   "text": "...короткое описание..."}]
    """
    items_html = ""
    for h in highlights[:3]:
        items_html += f"""
        <tr>
          <td style="padding:12px 0;border-bottom:1px solid #ece7f8;vertical-align:top;">
            <div style="color:#9060C8;font-size:12px;font-weight:700;
                        text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">
              {h.get("date", "")}
            </div>
            <div style="color:#2D2540;font-size:15px;font-weight:600;margin-bottom:4px;">
              {h.get("planet", "")} {h.get("aspect", "")} → {h.get("natal", "")}
            </div>
            <div style="color:#5a4a7a;font-size:14px;line-height:1.6;">
              {h.get("text", "")}
            </div>
          </td>
        </tr>"""

    body = (
        _h2(f"🔭 Ваш дайджест на {week_label}")
        + _p("Главные астрологические события предстоящей недели по вашей карте:")
        + f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
          f' style="margin:0 0 20px;">{items_html}</table>'
        + _btn("Открыть полный календарь", f"{APP_URL}/calendar")
    )
    return await _send(
        to,
        f"🔭 Астро-дайджест на {week_label} · Astrea Timeline",
        _base(f"Дайджест {week_label}", "Ваши главные транзиты на неделю", body),
    )


async def send_transit_alert_email(
    to: str,
    planet: str,
    aspect: str,
    natal_planet: str,
    date_str: str,
    description: str,
    is_peak: bool = True,
) -> bool:
    """Transit Alert — точечное уведомление об важном транзите (пик или начало)."""
    badge = (
        '<span style="background:#9060C8;color:#fff;font-size:11px;font-weight:700;'
        'padding:2px 8px;border-radius:4px;margin-left:8px;">ПИК</span>'
        if is_peak else ""
    )
    body = (
        _h2(f"🌟 Важный транзит{' — сегодня пик' if is_peak else ''}")
        + f'<div style="background:#f0ebff;border-radius:12px;padding:20px 24px;margin:0 0 20px;">'
          f'  <div style="color:#9060C8;font-size:13px;font-weight:700;margin-bottom:8px;">'
          f'    {date_str}{badge}'
          f'  </div>'
          f'  <div style="color:#2D2540;font-size:17px;font-weight:700;margin-bottom:10px;">'
          f'    {planet} {aspect} {natal_planet}'
          f'  </div>'
          f'  <div style="color:#5a4a7a;font-size:14px;line-height:1.7;">{description}</div>'
          f'</div>'
        + _p("Откройте приложение, чтобы получить полную AI-интерпретацию этого транзита.")
        + _btn("Читать интерпретацию →", APP_URL)
    )
    return await _send(
        to,
        f"🌟 {planet} {aspect} {natal_planet} — {date_str} · Astrea Timeline",
        _base("Важный транзит", f"{planet} {aspect} {natal_planet} — {date_str}", body),
    )


async def send_weekly_digest(user, db) -> bool:
    """Weekly digest для Pro/Premium — транзиты + лунные фазы + лучшие дни + совет недели + A/B тема."""
    import random
    from datetime import timedelta, date as date_type
    from backend.transit.engine import calculate_transits
    from backend.models import NatalChart

    now = date_type.today()
    week_end = now + timedelta(days=7)

    # Транзиты недели
    try:
        chart = db.query(NatalChart).filter_by(user_id=user.id)\
            .order_by(NatalChart.created_at.desc()).first()
        if not chart:
            return False
        events = calculate_transits(natal_planets=chart.planets, from_date=now, to_date=week_end)
    except Exception as e:
        logger.warning("Weekly digest transit fetch failed: %s", e)
        return False

    PLANET_RU = {"Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
                 "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн",
                 "Uranus": "Уран", "Neptune": "Нептун", "Pluto": "Плутон"}
    ASP_RU = {"conjunction": "соединение", "sextile": "секстиль",
              "square": "квадрат", "trine": "трин", "opposition": "оппозиция"}
    SPHERE_RU = {"Venus": "отношений и творчества", "Jupiter": "роста и новых возможностей",
                 "Sun": "самовыражения и карьеры", "Mars": "действий и инициатив",
                 "Mercury": "коммуникации и планирования"}
    POSITIVE_ASP = {"trine", "sextile", "conjunction"}
    POSITIVE_PLAN = {"Venus", "Jupiter", "Sun"}

    # Топ-3 транзита (позитивные в приоритете)
    sorted_events = sorted(
        events,
        key=lambda e: (
            0 if (getattr(e, "transit_planet", "") in POSITIVE_PLAN
                  and getattr(e, "aspect_type", "") in POSITIVE_ASP) else 1,
            getattr(e, "peak_orb", None) or getattr(e, "orb", 9),
        )
    )

    highlights = []
    for e in sorted_events[:3]:
        tp  = getattr(e, "transit_planet", "")
        np_ = getattr(e, "natal_planet", "")
        at  = getattr(e, "aspect_type", "")
        peak = str(getattr(e, "peak_date", None) or getattr(e, "date", str(now)))
        is_pos = tp in POSITIVE_PLAN and at in POSITIVE_ASP
        text = ("Благоприятный период — используйте энергию для важных дел."
                if is_pos else
                "Период требует осознанности и внимательности.")
        highlights.append({
            "date": peak,
            "planet": PLANET_RU.get(tp, tp),
            "aspect": ASP_RU.get(at, at),
            "natal": PLANET_RU.get(np_, np_),
            "text": text,
            "_tp": tp,
            "_at": at,
        })

    # ── Совет недели от планировщика ──
    tip_block = ""
    first_positive = next(
        (e for e in sorted_events if getattr(e, "transit_planet", "") in POSITIVE_PLAN
         and getattr(e, "aspect_type", "") in POSITIVE_ASP),
        sorted_events[0] if sorted_events else None,
    )
    if first_positive:
        tp = getattr(first_positive, "transit_planet", "")
        at = getattr(first_positive, "aspect_type", "")
        peak = str(getattr(first_positive, "peak_date", None) or getattr(first_positive, "date", ""))
        sphere = SPHERE_RU.get(tp, "важных дел")
        tip_text = f"{peak}, когда {PLANET_RU.get(tp, tp)} {ASP_RU.get(at, at)} — хороший момент для {sphere}"
        tip_block = (
            f'<div style="background:#fffbeb;border-left:4px solid #f59e0b;border-radius:0 10px 10px 0;'
            f'padding:14px 18px;margin:0 0 20px;">'
            f'<div style="color:#92400e;font-weight:700;font-size:13px;margin-bottom:6px;">💡 Совет недели от планировщика</div>'
            f'<div style="color:#78350f;font-size:14px;line-height:1.6;">{tip_text}</div>'
            f'</div>'
        )

    # Лунные фазы недели
    lunar_block = ""
    try:
        from backend.calendar.lunar_engine import get_moon_phases
        phases = get_moon_phases(now.year, now.month)
        week_phases = [
            p for p in phases
            if now <= date_type.fromisoformat(p.to_dict()["date"]) <= week_end
        ]
        if week_phases:
            phase_lines = "".join(
                f'<li style="margin:4px 0;color:#5a4a7a;font-size:14px;">'
                f'{p.to_dict()["date"]} — {p.to_dict()["title"]}</li>'
                for p in week_phases
            )
            lunar_block = (
                f'<div style="background:#f5f0ff;border-radius:10px;padding:14px 18px;margin:0 0 20px;">'
                f'<div style="color:#9060C8;font-weight:700;font-size:13px;margin-bottom:8px;">🌙 Лунные фазы недели</div>'
                f'<ul style="margin:0;padding-left:18px;">{phase_lines}</ul>'
                f'</div>'
            )
    except Exception as e:
        logger.warning("Lunar phases fetch failed: %s", e)

    # Лучшие дни
    best_days_block = ""
    best = [e for e in sorted_events
            if getattr(e, "transit_planet", "") in POSITIVE_PLAN
            and getattr(e, "aspect_type", "") in POSITIVE_ASP][:3]
    if best:
        rows = "".join(
            f'<li style="margin:4px 0;color:#5a4a7a;font-size:14px;">'
            f'{str(getattr(e, "peak_date", None) or getattr(e, "date", ""))} — '
            f'{PLANET_RU.get(getattr(e, "transit_planet", ""), "")} '
            f'{ASP_RU.get(getattr(e, "aspect_type", ""), "")}</li>'
            for e in best
        )
        best_days_block = (
            f'<div style="background:#f0fff4;border-radius:10px;padding:14px 18px;margin:0 0 20px;">'
            f'<div style="color:#2e7d52;font-weight:700;font-size:13px;margin-bottom:8px;">⭐ Лучшие дни недели</div>'
            f'<ul style="margin:0;padding-left:18px;">{rows}</ul>'
            f'</div>'
        )

    week_label = f"{now.strftime('%d %b')}–{week_end.strftime('%d %b')}"

    items_html = ""
    for h in highlights:
        items_html += (
            f'<tr><td style="padding:12px 0;border-bottom:1px solid #ece7f8;vertical-align:top;">'
            f'<div style="color:#9060C8;font-size:12px;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:1px;margin-bottom:4px;">{h["date"]}</div>'
            f'<div style="color:#2D2540;font-size:15px;font-weight:600;margin-bottom:4px;">'
            f'{h["planet"]} {h["aspect"]} → {h["natal"]}</div>'
            f'<div style="color:#5a4a7a;font-size:14px;line-height:1.6;">{h["text"]}</div>'
            f'</td></tr>'
        )

    body = (
        _h2(f"🔭 Ваш дайджест на {week_label}")
        + _p("Главные астрологические события предстоящей недели по вашей карте:")
        + f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 20px;">{items_html}</table>'
        + tip_block
        + best_days_block
        + lunar_block
        + _btn("Открыть полный календарь", f"{APP_URL}/calendar")
    )

    # ── A/B тест темы письма ──
    week_iso = now.strftime("%Y-W%V")
    ab_key = f"digest_ab:{user.id}:{week_iso}"
    variant = "A"
    try:
        from backend.cache import interpretation_cache
        redis = interpretation_cache._redis
        if redis:
            stored = redis.get(ab_key)
            if stored:
                variant = stored
            else:
                variant = random.choice(["A", "B"])
                redis.setex(ab_key, 8 * 24 * 3600, variant)
    except Exception:
        variant = random.choice(["A", "B"])

    # Вариант A — персонализированный транзит, Вариант B — общий заголовок
    if variant == "A" and highlights:
        h0 = highlights[0]
        subject = f"{h0['planet']} активен в вашей карте на этой неделе · Astrea"
    else:
        subject = f"🔭 Астро-дайджест на {week_label} · Astrea Timeline"

    return await _send(
        user.email,
        subject,
        _base(f"Дайджест {week_label}", "Ваши главные транзиты на неделю", body),
    )


async def send_payment_failed_email(to: str, portal_url: str) -> bool:
    """Payment Failed — предупреждение об оплате, ссылка на Stripe Portal."""
    body = (
        _h2("⚠️ Не удалось списать оплату")
        + _p(
            "Мы попытались списать оплату за вашу подписку Astrea Timeline, "
            "но платёж не прошёл. Скорее всего, истёк срок карты или недостаточно средств."
        )
        + _p(
            "<strong>У вас есть 3 дня</strong>, чтобы обновить способ оплаты. "
            "После этого доступ к платным функциям будет ограничен."
        )
        + _btn("Обновить карту →", portal_url)
        + _p(
            "Если вы хотите отменить подписку — это тоже можно сделать по ссылке выше. "
            "Мы не будем списывать деньги без вашего согласия."
        )
    )
    return await _send(
        to,
        "⚠️ Не удалось списать оплату — обновите карту за 3 дня · Astrea Timeline",
        _base("Проблема с оплатой", "Не удалось списать оплату за подписку", body),
    )


async def send_gift_code_email(
    to: str,
    code: str,
    tier: str,
    duration_months: int,
) -> bool:
    """Email gift code to the buyer after successful payment."""
    redeem_url = f"https://astreatime.ru/gift/redeem?code={code}"
    tier_name = {"lite": "Lite", "pro": "Pro", "premium": "Premium"}.get(tier, tier.capitalize())
    body = (
        _h2(f"🎁 Ваш подарочный код Astrea {tier_name}")
        + _p(f"Спасибо за покупку! Вот подарочный код на <strong>{duration_months} мес.</strong> подписки {tier_name}:")
        + f'<div style="text-align:center;margin:24px 0">'
        + f'<code style="font-size:22px;font-weight:700;letter-spacing:3px;color:#7C6CFF;background:#1e1b4b;padding:12px 24px;border-radius:8px">{code}</code>'
        + f'</div>'
        + _p("Передайте этот код получателю — он введёт его в разделе «Подписка» личного кабинета.")
        + _btn("Активировать подарок →", redeem_url)
        + _p("Код действителен бессрочно и может быть использован один раз.")
    )
    return await _send(
        to,
        f"🎁 Ваш подарочный код Astrea {tier_name} на {duration_months} мес.",
        _base(f"Подарочная подписка {tier_name}", f"Код для активации {duration_months} мес. {tier_name}", body),
    )


async def send_lunar_return_email(user, lunar_return_date) -> bool:
    """Notify user when Moon returns to their natal sign."""
    date_str = lunar_return_date.strftime("%d %B %Y") if hasattr(lunar_return_date, "strftime") else str(lunar_return_date)
    body = (
        _h2("🌙 Луна вернулась в ваш знак")
        + _p(
            f"Сегодня, <strong>{date_str}</strong>, Луна вернулась в ваш натальный знак. "
            "Особый день для того, чтобы уделить время внедрению того, что вы хотите в своё жизненное пространство."
        )
        + _p(
            "Это хороший момент для рефлексии, новых намерений и создания ритуалов. "
            "Ваши эмоции сейчас особенно чувствительны к тому, что действительно важно."
        )
        + _btn("Открыть мою карту →", "https://astreatime.ru/profile")
    )
    return await _send(
        user.email,
        "Луна вернулась в ваш знак 🌙",
        _base("Лунное возвращение", "Особый день для новых намерений", body),
    )


# ═══════════════════════════════════════════════════════════
# RETENTION DAY 14 — шаблон (Free → Lite, купон 30%)
# ═══════════════════════════════════════════════════════════

async def send_retention_day14(to: str, checkout_url: str) -> bool:
    """Retention Day 14 — купон 30% на годовой план Lite (24 часа)."""
    body = (
        _h2("🎁 Специальное предложение — 30% скидка на годовой план")
        + _p(
            "Мы подготовили для вас персональное предложение: "
            "<strong>скидка 30%</strong> на годовой план Lite."
        )
        + f'<div style="background:#fff8e1;border:1px solid #ffc107;border-radius:10px;'
          f'padding:14px 18px;margin:0 0 20px;color:#5d4000;font-size:14px;line-height:1.6;">'
          f'⏰ Предложение действует <strong>24 часа</strong>. После — исчезнет навсегда.</div>'
        + _btn("Получить скидку 30% →", checkout_url)
        + _p(
            '<span style="font-size:12px;color:#a090c0;">'
            "Отмена в любой момент · Без обязательств"
            "</span>"
        )
    )
    return await _send(
        to,
        "🎁 Специальное предложение — 30% скидка на годовой план · Astrea",
        _base("Скидка 30%", "Специальное предложение истекает через 24 часа", body),
    )


# ═══════════════════════════════════════════════════════════
# LITE EMAIL CHAIN
# ═══════════════════════════════════════════════════════════

async def send_lite_welcome(to: str, name: str | None = None) -> bool:
    """Lite — День 1: транзиты ждут объяснения."""
    greeting = f"Привет, {name}! 🎉" if name else "Добро пожаловать в Lite! 🎉"
    body = (
        _h2(greeting)
        + _p(
            "Ваша подписка Lite активирована. Теперь вам доступны:"
        )
        + f'<table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px;">'
          f'<tr><td style="padding:8px 0;border-bottom:1px solid #ece7f8;">'
          f'<span style="color:#9060C8;font-weight:700;">📅</span>'
          f'<span style="color:#3d3060;font-size:15px;margin-left:10px;">Лунный календарь на год вперёд</span></td></tr>'
          f'<tr><td style="padding:8px 0;border-bottom:1px solid #ece7f8;">'
          f'<span style="color:#9060C8;font-weight:700;">🔭</span>'
          f'<span style="color:#3d3060;font-size:15px;margin-left:10px;">Транзиты на 12 месяцев</span></td></tr>'
          f'<tr><td style="padding:8px 0;">'
          f'<span style="color:#9060C8;font-weight:700;">✨</span>'
          f'<span style="color:#3d3060;font-size:15px;margin-left:10px;">Виральная карточка карты для Stories</span></td></tr>'
          f'</table>'
        + _p("Ваши транзиты уже рассчитаны — откройте карту и исследуйте ближайшие периоды.")
        + _btn("Открыть мои транзиты →", f"{APP_URL}/profile")
    )
    return await _send(
        to,
        "✨ Добро пожаловать в Astrea Lite",
        _base("Lite активирован", "Транзиты и лунный календарь ждут вас", body),
    )


async def send_lite_day14(to: str, name: str | None = None) -> bool:
    """Lite — День 14: identity + тизер RAG-чата."""
    greeting = f"{name}, вы исследуете себя серьёзнее других" if name else "Вы исследуете себя серьёзнее других"
    body = (
        _h2(f"🌟 {greeting}")
        + _p(
            "За две недели вы изучили свою натальную карту, транзиты и лунный календарь. "
            "Это уже больше, чем делают 95% людей."
        )
        + _p(
            "Но есть следующий уровень: <strong>задавать вопросы своей карте</strong>. "
            "«Почему мне сложно с деньгами?», «Когда лучший момент для смены работы?», "
            "«Что говорит Сатурн о моих отношениях?» — и получать персональные ответы с учётом именно вашей карты."
        )
        + f'<div style="background:#f0ebff;border-left:3px solid #9060C8;border-radius:8px;'
          f'padding:16px 20px;margin:16px 0 24px;">'
          f'<div style="color:#9060C8;font-size:12px;font-weight:700;text-transform:uppercase;'
          f'letter-spacing:1px;margin-bottom:6px;">💬 RAG-чат доступен в Pro</div>'
          f'<div style="color:#2D2540;font-size:15px;line-height:1.7;">'
          f'AI-ассистент, который знает вашу карту наизусть. Задайте любой вопрос — ответ будет про вас, не про всех Тельцов.</div>'
          f'</div>'
        + _btn("Попробовать Pro →", f"{APP_URL}/pricing")
        + _p(
            '<span style="font-size:12px;color:#a090c0;">'
            "Отмена в любой момент · Без обязательств"
            "</span>"
        )
    )
    return await _send(
        to,
        "🌟 Вы исследуете себя серьёзнее других",
        _base("14 дней с Astrea", "Следующий уровень — задавать вопросы своей карте", body),
    )


# ═══════════════════════════════════════════════════════════
# PRO EMAIL CHAIN
# ═══════════════════════════════════════════════════════════

async def send_pro_welcome(to: str, name: str | None = None) -> bool:
    """Pro — День 1: онбординг, как использовать всё."""
    greeting = f"Привет, {name}! Добро пожаловать в глубину 🪐" if name else "Добро пожаловать в глубину 🪐"
    body = (
        _h2(greeting)
        + _p("Ваша подписка Pro активирована. Вот что теперь доступно:")
        + f'<table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px;">'
          f'<tr><td style="padding:8px 0;border-bottom:1px solid #ece7f8;">'
          f'<span style="color:#9060C8;font-weight:700;">💬</span>'
          f'<span style="color:#3d3060;font-size:15px;margin-left:10px;"><strong>RAG-чат</strong> — AI знает вашу карту, задайте любой вопрос</span></td></tr>'
          f'<tr><td style="padding:8px 0;border-bottom:1px solid #ece7f8;">'
          f'<span style="color:#9060C8;font-weight:700;">🪐</span>'
          f'<span style="color:#3d3060;font-size:15px;margin-left:10px;"><strong>AI-транзиты</strong> — персональная расшифровка каждого периода</span></td></tr>'
          f'<tr><td style="padding:8px 0;border-bottom:1px solid #ece7f8;">'
          f'<span style="color:#9060C8;font-weight:700;">📄</span>'
          f'<span style="color:#3d3060;font-size:15px;margin-left:10px;"><strong>PDF-отчёты</strong> — 5 в месяц, для скачивания и печати</span></td></tr>'
          f'<tr><td style="padding:8px 0;">'
          f'<span style="color:#9060C8;font-weight:700;">🔭</span>'
          f'<span style="color:#3d3060;font-size:15px;margin-left:10px;"><strong>15 AI-интерпретаций</strong> в месяц на GPT-4o</span></td></tr>'
          f'</table>'
        + _p("Совет: начните с вкладки «Транзиты» на вашей карте — нажмите на любой период, чтобы получить AI-расшифровку.")
        + _btn("Открыть мою карту →", f"{APP_URL}/profile")
    )
    return await _send(
        to,
        "🪐 Добро пожаловать в Astrea Pro",
        _base("Pro активирован", "RAG-чат, AI-транзиты и PDF ждут вас", body),
    )


async def send_pro_day30(to: str, name: str | None = None) -> bool:
    """Pro — День 30: результат + мягкий вопрос про клиентов → Premium."""
    greeting = f"{name}, уже 30 дней с вашей картой ✦" if name else "Уже 30 дней с вашей картой ✦"
    body = (
        _h2(greeting)
        + _p(
            "Месяц с Astrea Pro — это не просто подписка. "
            "Это месяц глубокого знакомства с собой через транзиты, планировщик и AI-ассистента."
        )
        + _p("Вопрос к вам: вы занимаетесь астрологией только для себя или уже консультируете других?")
        + f'<div style="background:#f0ebff;border-left:3px solid #9060C8;border-radius:8px;'
          f'padding:16px 20px;margin:16px 0 24px;">'
          f'<div style="color:#9060C8;font-size:12px;font-weight:700;text-transform:uppercase;'
          f'letter-spacing:1px;margin-bottom:6px;">👥 Для астрологов — Premium</div>'
          f'<div style="color:#2D2540;font-size:15px;line-height:1.7;">'
          f'CRM клиентов, 100 AI-интерпретаций в месяц, брендированные PDF-отчёты. '
          f'Один клиент окупает подписку.</div>'
          f'</div>'
        + _btn("Посмотреть Premium →", f"{APP_URL}/pricing")
        + _p(
            '<span style="font-size:12px;color:#a090c0;">'
            "Если работаете только для себя — Pro идеален. Переходите, только если нужен CRM."
            "</span>"
        )
    )
    return await _send(
        to,
        "✦ Уже 30 дней с вашей астрологической картой",
        _base("30 дней с Astrea", "Результат + взгляд вперёд", body),
    )


# ═══════════════════════════════════════════════════════════
# PREMIUM EMAIL CHAIN
# ═══════════════════════════════════════════════════════════

async def send_premium_welcome(to: str, name: str | None = None) -> bool:
    """Premium — День 1: CRM-онбординг, первый PDF-шаблон."""
    greeting = f"Привет, {name}! Ваш профессиональный инструмент готов 🖥️" if name else "Ваш профессиональный инструмент готов 🖥️"
    body = (
        _h2(greeting)
        + _p("Подписка Premium активирована. Вот с чего начать:")
        + f'<table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 8px;">'
          f'<tr><td style="padding:10px 0;border-bottom:1px solid #ece7f8;vertical-align:top;">'
          f'<div style="color:#9060C8;font-size:13px;font-weight:700;margin-bottom:4px;">Шаг 1 — CRM клиентов</div>'
          f'<div style="color:#5a4a7a;font-size:14px;line-height:1.6;">Откройте /dashboard/clients → добавьте первого клиента. '
          f'Введите дату и место рождения — карта рассчитается автоматически.</div></td></tr>'
          f'<tr><td style="padding:10px 0;border-bottom:1px solid #ece7f8;vertical-align:top;">'
          f'<div style="color:#9060C8;font-size:13px;font-weight:700;margin-bottom:4px;">Шаг 2 — PDF с вашим именем</div>'
          f'<div style="color:#5a4a7a;font-size:14px;line-height:1.6;">Откройте карточку клиента → «Создать отчёт». '
          f'На обложке будет указано ваше имя как автора.</div></td></tr>'
          f'<tr><td style="padding:10px 0;vertical-align:top;">'
          f'<div style="color:#9060C8;font-size:13px;font-weight:700;margin-bottom:4px;">Шаг 3 — AI без лимитов</div>'
          f'<div style="color:#5a4a7a;font-size:14px;line-height:1.6;">100 AI-интерпретаций в месяц на GPT-4o — '
          f'хватит на всех активных клиентов.</div></td></tr>'
          f'</table>'
        + _btn("Открыть CRM клиентов →", f"{APP_URL}/dashboard/clients")
    )
    return await _send(
        to,
        "🖥️ Ваш профессиональный инструмент Astrea Premium готов",
        _base("Premium активирован", "CRM клиентов и брендированные PDF ждут вас", body),
    )
