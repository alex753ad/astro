"""Email service via Resend API."""

from __future__ import annotations
import logging
import os
import httpx

logger = logging.getLogger("astro.email")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "onboarding@resend.dev")
APP_URL = os.getenv("APP_URL", "https://astro-qnbq.vercel.app")


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
            if resp.status_code != 200:
                logger.error("Resend error %s: %s", resp.status_code, resp.text)
                return False
            return True
    except Exception as e:
        logger.error("Email send failed: %s", e)
        return False


async def send_welcome_email(to: str) -> bool:
    """Welcome-письмо сразу после регистрации."""
    subject = "✨ Добро пожаловать в Astro"
    html = f"""
    <div style="font-family: sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a2e;">
      <div style="background: linear-gradient(135deg, #9060C8, #C060A0); padding: 32px; border-radius: 16px 16px 0 0; text-align: center;">
        <h1 style="color: #fff; margin: 0; font-size: 24px;">✦ Добро пожаловать</h1>
        <p style="color: rgba(255,255,255,0.8); margin: 8px 0 0;">Ваша натальная карта ждёт</p>
      </div>
      <div style="background: #f8f5ff; padding: 32px; border-radius: 0 0 16px 16px;">
        <p style="font-size: 15px; line-height: 1.7; margin: 0 0 20px;">
          Вы только что получили доступ к персональному астрологическому анализу на основе AI.
          Рассчитайте свою натальную карту и откройте ключевые темы своей жизни.
        </p>
        <div style="text-align: center; margin: 28px 0;">
          <a href="{APP_URL}" style="background: linear-gradient(135deg, #9060C8, #C060A0); color: #fff; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 15px;">
            ✦ Открыть мою карту
          </a>
        </div>
        <p style="font-size: 12px; color: #9080B0; margin: 24px 0 0; text-align: center;">
          Astro · <a href="{APP_URL}" style="color: #9080B0;">{APP_URL}</a>
        </p>
      </div>
    </div>
    """
    return await _send(to, subject, html)


async def send_retention_email(to: str, transit_text: str) -> bool:
    """Retention-письмо на день 2 — актуальный транзит."""
    subject = "🌙 Ваш астрологический прогноз на сегодня"
    html = f"""
    <div style="font-family: sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a2e;">
      <div style="background: linear-gradient(135deg, #1a1a2e, #2d1b4e); padding: 32px; border-radius: 16px 16px 0 0; text-align: center;">
        <h1 style="color: #fff; margin: 0; font-size: 22px;">🌙 Активный транзит</h1>
        <p style="color: rgba(255,255,255,0.7); margin: 8px 0 0; font-size: 13px;">Персонально для вашей карты</p>
      </div>
      <div style="background: #f8f5ff; padding: 32px; border-radius: 0 0 16px 16px;">
        <p style="font-size: 15px; line-height: 1.75; margin: 0 0 24px; color: #2D2540;">
          {transit_text}
        </p>
        <div style="text-align: center; margin: 24px 0;">
          <a href="{APP_URL}" style="background: linear-gradient(135deg, #9060C8, #C060A0); color: #fff; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 15px;">
            Смотреть полный прогноз
          </a>
        </div>
        <p style="font-size: 12px; color: #9080B0; margin: 24px 0 0; text-align: center;">
          Astro · <a href="{APP_URL}" style="color: #9080B0;">{APP_URL}</a>
        </p>
      </div>
    </div>
    """
    return await _send(to, subject, html)


async def send_upgrade_nudge_email(to: str, locked_count: int) -> bool:
    """Письмо на день 7 — если не перешёл в Pro."""
    subject = f"⭐ Вы пропускаете {locked_count} активных транзитов"
    html = f"""
    <div style="font-family: sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a2e;">
      <div style="background: linear-gradient(135deg, #9060C8, #E080B0); padding: 32px; border-radius: 16px 16px 0 0; text-align: center;">
        <h1 style="color: #fff; margin: 0; font-size: 22px;">⭐ Не пропустите важные периоды</h1>
      </div>
      <div style="background: #f8f5ff; padding: 32px; border-radius: 0 0 16px 16px;">
        <p style="font-size: 15px; line-height: 1.75; margin: 0 0 16px; color: #2D2540;">
          В ближайший месяц для вашей карты активно <strong>{locked_count} транзитов</strong> — периоды, которые влияют на карьеру, отношения и финансы.
        </p>
        <p style="font-size: 15px; line-height: 1.75; margin: 0 0 24px; color: #2D2540;">
          С планом Pro вы видите полный прогноз и получаете AI-интерпретацию каждого периода.
        </p>
        <div style="text-align: center; margin: 24px 0;">
          <a href="{APP_URL}/pricing" style="background: linear-gradient(135deg, #9060C8, #C060A0); color: #fff; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 15px;">
            Попробовать Pro
          </a>
        </div>
        <p style="font-size: 12px; color: #9080B0; margin: 24px 0 0; text-align: center;">
          Astro · <a href="{APP_URL}" style="color: #9080B0;">{APP_URL}</a>
        </p>
      </div>
    </div>
    """
    return await _send(to, subject, html)
