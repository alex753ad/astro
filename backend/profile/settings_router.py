"""Profile settings router.

Endpoints:
  GET   /api/v1/profile/settings  — get user UI preferences
  PATCH /api/v1/profile/settings  — update user UI preferences

Живёт рядом с profile/router.py, не трогает его.
Подключается отдельной строкой в main.py.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.auth.dependencies import get_current_user

logger = logging.getLogger("astro.profile.settings")

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


class UserSettingsPatch(BaseModel):
    expert_mode: Optional[bool] = None


class UserSettingsResponse(BaseModel):
    expert_mode: bool

    class Config:
        from_attributes = True


@router.get("/settings", response_model=UserSettingsResponse, summary="Get user UI settings")
async def get_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return UserSettingsResponse(expert_mode=bool(getattr(user, "expert_mode", False)))


@router.patch("/settings", response_model=UserSettingsResponse, summary="Update user UI settings")
async def update_settings(
    payload: UserSettingsPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not hasattr(user, "expert_mode"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Колонка expert_mode не найдена. Запусти: alembic upgrade head",
        )

    if payload.expert_mode is not None:
        user.expert_mode = payload.expert_mode
        logger.info("User %s set expert_mode=%s", user.id, payload.expert_mode)

    db.commit()
    db.refresh(user)
    return UserSettingsResponse(expert_mode=bool(user.expert_mode))
