"""Note templates router.

Endpoints:
  GET    /api/v1/note-templates        — список шаблонов
  POST   /api/v1/note-templates        — создать шаблон
  PATCH  /api/v1/note-templates/{id}   — обновить шаблон
  DELETE /api/v1/note-templates/{id}   — удалить шаблон
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import NoteTemplate, User
from backend.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/note-templates", tags=["note-templates"])


class NoteTemplateCreate(BaseModel):
    title: str
    content: str


class NoteTemplateUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class NoteTemplateOut(BaseModel):
    id: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=list[NoteTemplateOut])
def list_templates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(NoteTemplate).filter(NoteTemplate.user_id == user.id).order_by(NoteTemplate.created_at.desc()).all()


@router.post("", response_model=NoteTemplateOut, status_code=201)
def create_template(
    body: NoteTemplateCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    template = NoteTemplate(user_id=user.id, title=body.title, content=body.content)
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.patch("/{template_id}", response_model=NoteTemplateOut)
def update_template(
    template_id: int,
    body: NoteTemplateUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    template = db.query(NoteTemplate).filter(NoteTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    if template.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if body.title is not None:
        template.title = body.title
    if body.content is not None:
        template.content = body.content
    template.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    template = db.query(NoteTemplate).filter(NoteTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    if template.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(template)
    db.commit()
