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
FRONTEND_URL   = os.getenv("FRONTEND_URL", "https://astreatime.ru")
# Публичный адрес API (для ссылки отписки в письмах). Если API не на APP_URL — задайте env.
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", APP_URL)
LOGO_URL       = "data:image/png;base64,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"

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
            <div style="display:inline-block;margin-bottom:12px;
                        border-radius:50%;
                        box-shadow:0 0 32px 10px rgba(144,96,200,0.5),
                                   0 0 64px 20px rgba(144,96,200,0.2);">
              <img src="{LOGO_URL}" width="72" height="72" alt="Astrea Timeline"
                   style="display:block;border-radius:50%;"/>
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
                json={"from": f"Astrea Timeline <{FROM_EMAIL}>", "to": [to], "subject": subject, "html": html},
            )
            if resp.status_code not in (200, 201):
                logger.error("Resend error %s: %s", resp.status_code, resp.text)
                return False
            return True
    except Exception as e:
        logger.error("Email send failed: %s", e)
        return False


# ─────────────────────── branded client broadcast (021) ──────────────────────

_PLANET_RU: dict[str, str] = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
    "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн", "Uranus": "Уран",
    "Neptune": "Нептун", "Pluto": "Плутон",
}

_MONTHS_RU = [
    "", "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]


def ru_month_label(d) -> str:
    """'август 2026' по объекту date/datetime."""
    return f"{_MONTHS_RU[d.month]} {d.year}"


def _base_branded(brand_name: str, title: str, preview: str, body: str, unsubscribe_url: str | None = None) -> str:
    """Базовый шаблон под брендом астролога: его имя в шапке, мелкий кредит Astrea в футере."""
    safe_brand = (brand_name or "Ваш астролог").strip()
    unsub_html = (
        f'<br/><a href="{unsubscribe_url}" style="color:#b0a0d0;text-decoration:none;">Отписаться от рассылки</a>'
        if unsubscribe_url else ""
    )
    return f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>{title}</title></head>
<body style="margin:0;padding:0;background:#0e0c1a;font-family:'Segoe UI',Arial,sans-serif;">
  <span style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{preview}</span>
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0e0c1a;">
    <tr><td align="center" style="padding:32px 16px;">
      <table width="560" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;width:100%;">
        <tr>
          <td style="background:linear-gradient(135deg,#2d1b4e 0%,#1a1030 100%);border-radius:16px 16px 0 0;padding:32px 40px;text-align:center;">
            <div style="color:#c9a8ff;font-size:22px;font-weight:700;letter-spacing:0.5px;">{safe_brand}</div>
            <div style="color:rgba(201,168,255,0.55);font-size:12px;margin-top:6px;letter-spacing:2px;">ПЕРСОНАЛЬНЫЙ АСТРОПРОГНОЗ</div>
          </td>
        </tr>
        <tr>
          <td style="background:#f8f5ff;padding:36px 40px;border-radius:0 0 16px 16px;">
            {body}
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:32px;border-top:1px solid #e8e0f4;padding-top:20px;">
              <tr><td style="text-align:center;font-size:11px;color:#a090c0;line-height:1.7;">
                работает на <a href="{APP_URL}" style="color:#9060C8;text-decoration:none;font-weight:600;">Astrea</a> &nbsp;·&nbsp; astreatime.ru{unsub_html}
              </td></tr>
            </table>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


async def _send_as(from_name: str, to: str, subject: str, html: str) -> bool:
    """Как _send, но с именем отправителя = бренд астролога (адрес остаётся FROM_EMAIL)."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — skipping email to %s", to)
        return False
    safe_from = (from_name or "Astrea Timeline").replace('"', "").replace("<", "").replace(">", "").strip() or "Astrea Timeline"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={"from": f"{safe_from} <{FROM_EMAIL}>", "to": [to], "subject": subject, "html": html},
            )
            if resp.status_code not in (200, 201):
                logger.error("Resend error %s: %s", resp.status_code, resp.text)
                return False
            return True
    except Exception as e:
        logger.error("Email send failed: %s", e)
        return False


def build_client_broadcast(
    brand_name: str,
    period_label: str,
    transits: list[dict],
    unsubscribe_url: str | None = None,
    ai_text: str | None = None,
) -> tuple[str, str]:
    """Собирает (subject, html) брендового письма-прогноза на месяц.

    ai_text задан → тело из AI-текста (гибрид); иначе шаблонный список транзитов.
    """
    subject = f"Ваш астропрогноз на {period_label}"
    if ai_text:
        paras = "".join(_p(line) for line in ai_text.strip().split("\n\n") if line.strip())
        body = _h2(f"Ваш прогноз на {period_label}") + paras
    elif transits:
        rows = []
        for t in transits:
            tp = _PLANET_RU.get(t.get("transit_planet", ""), t.get("transit_planet", ""))
            npl = _PLANET_RU.get(t.get("natal_planet", ""), t.get("natal_planet", ""))
            asp = t.get("aspect_type", "")
            when = str(t.get("peak_date") or t.get("exact_date") or "")[:10]
            when_html = f' &nbsp;·&nbsp; {when}' if when else ""
            rows.append(
                '<tr><td style="padding:9px 0;border-bottom:1px solid #ece5f7;color:#3d3060;font-size:14px;">'
                f'<b>{tp}</b> {asp} <b>{npl}</b>{when_html}</td></tr>'
            )
        body = (
            _h2(f"Ваш прогноз на {period_label}")
            + _p("Ключевые астрологические события месяца по вашей натальной карте:")
            + '<table width="100%" cellpadding="0" cellspacing="0" border="0">'
            + "".join(rows)
            + "</table>"
        )
    else:
        body = (
            _h2(f"Ваш прогноз на {period_label}")
            + _p("В этом месяце крупных транзитных событий по вашей карте не выделяется — спокойный, ресурсный период. Хорошее время для планомерных дел.")
        )
    html = _base_branded(brand_name, subject, subject, body, unsubscribe_url=unsubscribe_url)
    return subject, html


def build_broadcast_ai_prompt(period_label: str, transits: list[dict]) -> str:
    """Промпт для AI-версии письма-прогноза (гибрид)."""
    if transits:
        lines = []
        for t in transits:
            tp = _PLANET_RU.get(t.get("transit_planet", ""), t.get("transit_planet", ""))
            npl = _PLANET_RU.get(t.get("natal_planet", ""), t.get("natal_planet", ""))
            lines.append(f"- {tp} {t.get('aspect_type','')} {npl}")
        transit_block = "\n".join(lines)
    else:
        transit_block = "Значимых транзитов в этом месяце нет."
    return (
        f"Напиши тёплый персональный астрологический прогноз на {period_label} для клиента, "
        "от лица его астролога, по-русски, 150–220 слов, без списков и заголовков, живым языком. "
        "Опирайся только на транзиты ниже, не выдумывай. Заверши мягким приглашением на консультацию.\n\n"
        f"ТРАНЗИТЫ МЕСЯЦА:\n{transit_block}"
    )


async def send_client_broadcast(
    to: str,
    brand_name: str,
    period_label: str,
    transits: list[dict],
    unsubscribe_url: str | None = None,
    ai_text: str | None = None,
) -> bool:
    subject, html = build_client_broadcast(
        brand_name, period_label, transits, unsubscribe_url=unsubscribe_url, ai_text=ai_text
    )
    return await _send_as(brand_name, to, subject, html)


# ───────────────────────────── templates ─────────────────────────────────────
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
        chart = None
        if user.primary_chart_id:
            chart = db.query(NatalChart).filter(
                NatalChart.id == user.primary_chart_id,
                NatalChart.user_id == user.id,
            ).first()
        if not chart:
            chart = db.query(NatalChart).filter(NatalChart.user_id == user.id)\
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


# ═══════════════════════════════════════════════════════════
# OTP — ПОДТВЕРЖДЕНИЕ EMAIL ПРИ РЕГИСТРАЦИИ
# ═══════════════════════════════════════════════════════════

async def send_otp_email(to: str, code: str) -> bool:
    """Отправить 6-значный OTP-код для подтверждения email при регистрации."""
    body = (
        _h2("Код подтверждения")
        + _p(
            "Для завершения регистрации в <strong>Astrea Timeline</strong> введите код:"
        )
        + (
            '<div style="text-align:center;margin:28px 0;">'
            f'<span style="font-size:40px;font-weight:800;letter-spacing:14px;'
            f'color:#7C6CFF;font-family:monospace;background:rgba(124,108,255,0.08);'
            f'padding:16px 28px;border-radius:12px;display:inline-block;">'
            f'{code}</span></div>'
        )
        + _p(
            "Код действителен <strong>10 минут</strong>. "
            "Если вы не регистрировались — просто проигнорируйте это письмо."
        )
    )
    return await _send(
        to,
        f"Ваш код: {code} — Astrea Timeline",
        _base("Подтверждение регистрации", f"Код подтверждения: {code}", body),
    )
