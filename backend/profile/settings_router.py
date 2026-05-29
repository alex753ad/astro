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
    digest_day: Optional[int] = None  # 0=пн … 6=вс


class UserSettingsResponse(BaseModel):
    expert_mode: bool
    digest_day_of_week: int = 0

    class Config:
        from_attributes = True


@router.get("/settings", response_model=UserSettingsResponse, summary="Get user UI settings")
async def get_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return UserSettingsResponse(
        expert_mode=bool(getattr(user, "expert_mode", False)),
        digest_day_of_week=int(getattr(user, "digest_day_of_week", 0)),
    )


@router.patch("/settings", response_model=UserSettingsResponse, summary="Update user UI settings")
async def update_settings(
    payload: UserSettingsPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.expert_mode is not None:
        user.expert_mode = payload.expert_mode
        logger.info("User %s set expert_mode=%s", user.id, payload.expert_mode)

    if payload.digest_day is not None:
        if not 0 <= payload.digest_day <= 6:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="digest_day must be 0–6")
        user.digest_day_of_week = payload.digest_day
        logger.info("User %s set digest_day_of_week=%s", user.id, payload.digest_day)

    db.commit()
    db.refresh(user)
    return UserSettingsResponse(
        expert_mode=bool(user.expert_mode),
        digest_day_of_week=int(user.digest_day_of_week),
    )
