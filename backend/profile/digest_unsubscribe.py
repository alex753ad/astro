"""Отписка от недельного дайджеста по ссылке из письма — без входа.

GET  /api/v1/email/digest/unsubscribe/{token} — страница с кнопкой «Отписаться»
POST /api/v1/email/digest/unsubscribe/{token} — отписывает

⚠️ Отписывает POST, а не сам переход по ссылке. Почтовые сканеры (Outlook,
корпоративные фильтры) открывают ссылки из писем сами, и GET-отписка молча
снимала бы дайджест у платящего человека, который ничего не нажимал.

Токен — `users.email_unsub_token` (063), заводится при первой отправке
дайджеста и больше не меняется: старые письма продолжают работать.
Отписка касается только дайджеста — служебные письма (оплата, сброс
пароля, уведомление о ценах по оферте) идут как раньше.
"""

import secrets
from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User

router = APIRouter(prefix="/api/v1/email/digest", tags=["email"])


def ensure_unsub_token(user: User, db: Session) -> str:
    if not user.email_unsub_token:
        user.email_unsub_token = secrets.token_urlsafe(24)
        db.commit()
    return user.email_unsub_token


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
<meta name="robots" content="noindex"/><title>Отписка от дайджеста</title></head>
<body style="margin:0;background:#0e0c1a;font-family:'Segoe UI',Arial,sans-serif;color:#e8e0f4;">
  <div style="max-width:480px;margin:80px auto;padding:40px;background:#1a1030;border-radius:16px;text-align:center;">
    <div style="font-size:22px;font-weight:700;color:#c9a8ff;margin-bottom:12px;">{title}</div>
    <div style="font-size:14px;color:#a090c0;">{note}</div>
    {button}
  </div>
</body></html>"""
    )


@router.api_route("/unsubscribe/{token}", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def unsubscribe_page(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email_unsub_token == token).first()
    if not user:
        return _page("Ссылка недействительна", "Возможно, она из старого письма.")
    if user.digest_opt_out:
        return _page("Отписка уже оформлена", "Недельных писем больше не будет.")
    return _page(
        "Отписаться от недельного дайджеста?",
        "Письма об оплате и важные уведомления о сервисе продолжат приходить.",
        form_action=f"/api/v1/email/digest/unsubscribe/{token}",
    )


@router.post("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email_unsub_token == token).first()
    if not user:
        return _page("Ссылка недействительна", "Возможно, она из старого письма.")
    if not user.digest_opt_out:
        user.digest_opt_out = True
        db.commit()
    return _page("Готово", "Недельный дайджест больше приходить не будет.")
