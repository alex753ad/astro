"""backend/feedback/router.py — E8 «Здесь что-то не так».

POST /api/v1/feedback        — создать запись (multipart/form-data, auth опциональна)
GET  /api/v1/feedback        — список для админа (require_admin)

Подключить в main.py: app.include_router(feedback_router).
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Feedback, User
from backend.auth.dependencies import get_current_user_optional
from backend.admin.admin_router import require_admin
from backend.limiter import limiter
from backend.auth.rate_limits import feedback_key
from backend.metrics import log_event  # для метрик трения (E11)
from backend.notifications.telegram import send_support_message
from backend.email_service import send_support_copy

logger = logging.getLogger("astro.feedback")

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])

MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024

# Копия каждого обращения на почту поддержки (решение владельца 30.09.2026) —
# второй канал на случай, когда Telegram с сервера недоступен (docs/support.md).
# Адрес публичный (оферта, политика), env — только чтобы сменить без релиза.
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "carearistea@mail.ru")

# Тип определяется по сигнатуре файла (magic bytes), не по расширению/заголовку —
# пользователь (или атакующий) не может выдать произвольный файл за картинку.
_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_JPEG_SIG = b"\xff\xd8\xff"


def _detect_image_type(header: bytes) -> Optional[str]:
    if header.startswith(_PNG_SIG):
        return "image/png"
    if header.startswith(_JPEG_SIG):
        return "image/jpeg"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return None


_EXT_BY_MIME = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


class FeedbackOut(BaseModel):
    id: int
    user_id: Optional[str] = None
    screen: Optional[str] = None
    url: Optional[str] = None
    message: Optional[str] = None
    user_agent: Optional[str] = None
    context: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


def _format_report(row: Feedback, user: Optional[User], app: Optional[dict] = None) -> str:
    """Сигнал владельцу в Telegram.

    `app` — обращение из приложения (SupportSheet.jsx): версия, телефон и
    очищенный на клиенте текст ошибки. Номер аккаунта и email берутся из
    токена, не из формы: email нужен, чтобы ответить, — человеку он показан
    открыто («Ответим на почту …»).
    """
    who = f"#{user.id} {user.email}" if user else "аноним"
    head = "Обращение в поддержку" if app else "Новая жалоба"
    lines = [head, f"Экран: {row.screen or '—'}"]
    if row.url:
        lines.append(f"URL: {row.url}")
    lines.append(f"Пользователь: {who}")
    if app:
        lines.append(f"Версия: {app.get('version') or '—'}")
        lines.append(f"Телефон: {app.get('device') or '—'}")
        if app.get("error"):
            lines.append(f"Ошибка: {app['error']}")
    else:
        lines.append(f"Устройство: {row.user_agent or '—'}")
    return chr(10).join(lines) + chr(10) + chr(10) + (row.message or "")


# Экран «Написать в поддержку» из раздела оплаты (приложение и веб). Для него
# к жалобе приклеиваются тариф и последние платежи: человек, у которого
# «заплатил, а тарифа нет», номер платежа не знает, а без него владельцу
# разбираться не с чем.
PAYMENT_SCREEN = "payment"


def _payment_context(db: Session, user: User) -> str:
    from backend.models import PaymentEvent, Subscription
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    lines = ["", "", f"Тариф: {user.tier}"
             + (f", до {sub.current_period_end:%d.%m.%Y}" if sub and sub.current_period_end else "")]
    rows = (db.query(PaymentEvent).filter(PaymentEvent.user_id == user.id)
            .order_by(PaymentEvent.created_at.desc()).limit(3).all())
    for r in rows:
        lines.append(f"Платёж {r.inv_id}: {r.amount or 0:.0f} ₽, {r.tier or '—'}, "
                     f"{r.created_at:%d.%m.%Y %H:%M} UTC" + ("" if r.period else " (не начислен)"))
    if not rows:
        lines.append("Платежей в базе нет — если человек платил, проверь ЮKassa по email.")
    return chr(10).join(lines)


async def _notify_owner(feedback_id: int, text: str) -> None:
    """Сигнал владельцу. Обращение к этому моменту уже в БД; неудача
    Telegram — ошибка уровня ERROR, то есть событие в Sentry
    (LoggingIntegration в sentry_setup.py): иначе недоставленное обращение
    заметили бы только по жалобе «написал — тишина»."""
    if not await send_support_message(text):
        logger.error("Обращение #%s не доставлено в Telegram (в БД сохранено)", feedback_id)


async def _email_copy(feedback_id: int, text: str, screenshot: Optional[bytes] = None,
                      filename: str = "screenshot.png") -> None:
    """Копия обращения на почту. Ошибки не наружу: фоновые задачи Starlette
    идут цепочкой, и исключение здесь сорвало бы следующие."""
    try:
        ok = await send_support_copy(SUPPORT_EMAIL, feedback_id, text, screenshot, filename)
    except Exception:
        logger.exception("Обращение #%s: сбой копии на почту", feedback_id)
        return
    if not ok:
        logger.error("Обращение #%s не доставлено на почту (в БД сохранено)", feedback_id)


async def _notify_both(feedback_id: int, text: str) -> None:
    # Одновременно, а не по очереди: повторы Telegram (5 и 30 с) не должны
    # задерживать письмо, и наоборот.
    await asyncio.gather(_notify_owner(feedback_id, text), _email_copy(feedback_id, text),
                         return_exceptions=True)


@router.post("", status_code=201)
@limiter.limit("5/hour", key_func=feedback_key)
async def create_feedback(
    request: Request,
    background_tasks: BackgroundTasks,
    screen: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    message: Optional[str] = Form(None),
    user_agent: Optional[str] = Form(None),
    app_version: Optional[str] = Form(None),
    device: Optional[str] = Form(None),
    error_text: Optional[str] = Form(None),
    screenshot: Optional[UploadFile] = File(None),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    screenshot_path = None
    shot = None
    if screenshot is not None:
        header = await screenshot.read(16)
        mime = _detect_image_type(header)
        if mime is None:
            raise HTTPException(status_code=422, detail="Файл должен быть изображением (PNG, JPEG или WEBP)")

        rest = await screenshot.read(MAX_SCREENSHOT_BYTES + 1 - len(header))
        if len(header) + len(rest) > MAX_SCREENSHOT_BYTES:
            raise HTTPException(status_code=422, detail="Скриншот больше 5 МБ — приложи файл поменьше")

        shot = header + rest
        fd, screenshot_path = tempfile.mkstemp(suffix=_EXT_BY_MIME[mime])
        with os.fdopen(fd, "wb") as f:
            f.write(header)
            f.write(rest)

    app = None
    if app_version or device:
        app = {"version": (app_version or "")[:60], "device": (device or "")[:120],
               "error": (error_text or "")[:300]}

    row = Feedback(
        user_id=user.id if user else None,
        screen=(screen or "")[:120] or None,
        url=(url or "")[:500] or None,
        message=message,
        user_agent=(user_agent or "")[:300] or None,
        context=app,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # событие трения — считаем, где чаще всего жмут «что-то не так»
    log_event(db, user.id if user else None, "feedback_reported", {"screen": row.screen})

    text = _format_report(row, user, app)
    if row.screen == PAYMENT_SCREEN and user is not None:
        text += _payment_context(db, user)

    if screenshot_path:
        # Письмо — в фоне и ДО ожидания Telegram: уходит и тогда, когда
        # Telegram упал и ответ ниже возвращается досрочно.
        background_tasks.add_task(_email_copy, row.id, text, shot,
                                  "screenshot" + os.path.splitext(screenshot_path)[1])
        # Фото ждём синхронно (один запрос к Telegram) — иначе нечем определить,
        # получилось ли отправить, и что вернуть пользователю. Удаляем сразу после.
        sent = False
        try:
            sent = await send_support_message(text, photo_path=screenshot_path)
        finally:
            try:
                os.unlink(screenshot_path)
            except OSError:
                pass
        if not sent:
            logger.error("Обращение #%s не доставлено в Telegram (в БД сохранено)", row.id)
            return {"id": row.id, "message": "Скриншот не отправился, но текст мы получили"}
        return {"id": row.id, "message": "Спасибо — жалоба получена"}

    # Без скриншота результат отправки не влияет на ответ — шлём в фоне.
    background_tasks.add_task(_notify_both, row.id, text)
    return {"id": row.id, "message": "Спасибо — жалоба получена"}


@router.get("", response_model=list[FeedbackOut])
async def list_feedback(db: Session = Depends(get_db), _=Depends(require_admin)):
    return db.query(Feedback).order_by(Feedback.created_at.desc()).limit(200).all()
