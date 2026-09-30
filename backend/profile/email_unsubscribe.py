"""Отписка от информационных писем по ссылке из письма — без входа.

GET  /api/v1/email/unsubscribe/{token} — страница с кнопкой «Отписаться»
POST /api/v1/email/unsubscribe/{token} — отписывает; сюда же шлёт почтовый
     клиент по кнопке «Отписаться» из заголовка List-Unsubscribe-Post
     (RFC 8058, email_service._send). Тело запроса не читаем.

Прежний путь `/api/v1/email/digest/unsubscribe/{token}` стоял в письмах
дайджеста до 068 — обслуживается так же, иначе старые письма дали бы 404.

⚠️ Отписывает POST, а не сам переход по ссылке. Почтовые сканеры (Outlook,
корпоративные фильтры) открывают ссылки из писем сами, и GET-отписка молча
снимала бы письма у человека, который ничего не нажимал. Решение владельца
30.09.2026: страница с кнопкой остаётся.

Флаг один — `users.email_opt_out` (068) на все информационные письма.
Служебные (коды, оплата) его не читают и ссылки отписки не несут. Вернуть
письма — тумблер «Письма» в настройках уведомлений (push/router.py, поле
`emails`). Тексты страницы — без рода: пола человека мы не знаем.
"""

import logging
from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User

logger = logging.getLogger("astro.email")

router = APIRouter(prefix="/api/v1/email", tags=["email"])

_PATHS = ("/unsubscribe/{token}", "/digest/unsubscribe/{token}")
_KEEP_NOTE = "Коды входа и письма об оплате продолжат приходить."
_RETURN_NOTE = "Вернуть письма можно в настройках уведомлений в профиле."


def unsubscribe_url(user: User) -> str | None:
    """Ссылка отписки для информационного письма; None — письмо не отправлять.

    Единственная проверка флага: каждый, кто шлёт информационное письмо,
    берёт ссылку здесь, а email_service требует её аргументом, так что
    обойти отписку можно только нарочно.
    """
    if user.email_opt_out:
        return None
    if not user.email_unsub_token:
        # Токен ставят миграция 068 и ORM — сюда попадать не должны.
        logger.error("email_unsub_token пуст у user=%s — письмо не отправлено", user.id)
        return None
    from backend.email_service import PUBLIC_API_URL
    return f"{PUBLIC_API_URL}/api/v1/email/unsubscribe/{user.email_unsub_token}"


def _page(title: str, note: str, form_action: str | None = None) -> HTMLResponse:
    button = (
        f'<form method="post" action="{escape(form_action, quote=True)}" style="margin-top:20px;">'
        '<button type="submit" style="background:#8b5cf6;color:#fff;border:none;border-radius:10px;'
        'padding:12px 24px;font-size:15px;cursor:pointer;">Отписаться</button></form>'
        if form_action else ""
    )
    return HTMLResponse(
        f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="robots" content="noindex"/><title>Отписка от писем</title></head>
<body style="margin:0;background:#0e0c1a;font-family:'Segoe UI',Arial,sans-serif;color:#e8e0f4;">
  <div style="max-width:480px;margin:80px auto;padding:40px;background:#1a1030;border-radius:16px;text-align:center;">
    <div style="font-size:22px;font-weight:700;color:#c9a8ff;margin-bottom:12px;">{title}</div>
    <div style="font-size:14px;color:#a090c0;line-height:1.6;">{note}</div>
    {button}
  </div>
</body></html>"""
    )


def _user(db: Session, token: str) -> User | None:
    return db.query(User).filter(User.email_unsub_token == token).first()


async def unsubscribe_page(token: str, db: Session = Depends(get_db)):
    user = _user(db, token)
    if not user:
        return _page("Ссылка недействительна", "Возможно, она из старого письма.")
    if user.email_opt_out:
        return _page("Отписка уже оформлена", _RETURN_NOTE)
    return _page(
        "Отписаться от писем Aristea?",
        f"Перестанут приходить подборки транзитов, прогнозы и советы. {_KEEP_NOTE}",
        form_action=f"/api/v1/email/unsubscribe/{token}",
    )


async def unsubscribe(token: str, db: Session = Depends(get_db)):
    user = _user(db, token)
    if not user:
        return _page("Ссылка недействительна", "Возможно, она из старого письма.")
    if not user.email_opt_out:
        user.email_opt_out = True
        db.commit()
    return _page("Письма больше не придут", f"{_KEEP_NOTE} {_RETURN_NOTE}")


for _path in _PATHS:
    router.add_api_route(_path, unsubscribe_page, methods=["GET", "HEAD"], response_class=HTMLResponse)
    router.add_api_route(_path, unsubscribe, methods=["POST"], response_class=HTMLResponse)
