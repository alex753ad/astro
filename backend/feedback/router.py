"""backend/feedback/router.py — E8 «Здесь что-то не так».

POST /api/v1/feedback        — создать запись (multipart/form-data, auth опциональна)
GET  /api/v1/feedback        — список для админа (require_admin)

Подключить в main.py: app.include_router(feedback_router).
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Feedback, User
from backend.auth.dependencies import get_current_user_optional
from backend.admin.admin_router import require_admin
from backend.limiter import limiter
from backend.metrics import log_event  # для метрик трения (E11)
from backend.notifications.telegram import send_support_message

logger = logging.getLogger("astro.feedback")

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])

MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024

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
    screen: Optional[str] = None
    url: Optional[str] = None
    message: Optional[str] = None
    user_agent: Optional[str] = None

    model_config = {"from_attributes": True}


def _format_report(row: Feedback, user: Optional[User]) -> str:
    who = user.email if user else "аноним"
    return (
        f"Новая жалоба\n"
        f"Экран: {row.screen or '—'}\n"
        f"URL: {row.url or '—'}\n"
        f"Пользователь: {who}\n"
        f"Устройство: {row.user_agent or '—'}\n\n"
        f"{row.message or ''}"
    )


@router.post("", status_code=201)
@limiter.limit("5/hour")
async def create_feedback(
    request: Request,
    background_tasks: BackgroundTasks,
    screen: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    message: Optional[str] = Form(None),
    user_agent: Optional[str] = Form(None),
    screenshot: Optional[UploadFile] = File(None),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    screenshot_path = None
    if screenshot is not None:
        header = await screenshot.read(16)
        mime = _detect_image_type(header)
        if mime is None:
            raise HTTPException(status_code=422, detail="Файл должен быть изображением (PNG, JPEG или WEBP)")

        rest = await screenshot.read(MAX_SCREENSHOT_BYTES + 1 - len(header))
        if len(header) + len(rest) > MAX_SCREENSHOT_BYTES:
            raise HTTPException(status_code=422, detail="Скриншот больше 5 МБ — приложите файл поменьше")

        fd, screenshot_path = tempfile.mkstemp(suffix=_EXT_BY_MIME[mime])
        with os.fdopen(fd, "wb") as f:
            f.write(header)
            f.write(rest)

    row = Feedback(
        user_id=user.id if user else None,
        screen=(screen or "")[:120] or None,
        url=(url or "")[:500] or None,
        message=message,
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # событие трения — считаем, где чаще всего жмут «что-то не так»
    log_event(db, user.id if user else None, "feedback_reported", {"screen": row.screen})

    text = _format_report(row, user)

    if screenshot_path:
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
            return {"id": row.id, "message": "Скриншот не отправился, но текст мы получили"}
        return {"id": row.id, "message": "Спасибо — жалоба получена"}

    # Без скриншота результат отправки не влияет на ответ — шлём в фоне.
    background_tasks.add_task(send_support_message, text)
    return {"id": row.id, "message": "Спасибо — жалоба получена"}


@router.get("", response_model=list[FeedbackOut])
async def list_feedback(db: Session = Depends(get_db), _=Depends(require_admin)):
    return db.query(Feedback).order_by(Feedback.created_at.desc()).limit(200).all()
