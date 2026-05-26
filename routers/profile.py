"""Profile router — re-export from backend.profile."""

from fastapi import APIRouter
from backend.profile.router import router as _profile_router
from backend.profile.settings_router import router as _settings_router

# Merge both sub-routers under a single importable name.
router = APIRouter()
router.include_router(_profile_router)
router.include_router(_settings_router)
