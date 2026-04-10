"""Pydantic schemas for request validation and response serialization."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ═══════════════════════════════════════════════════════════
# CHART REQUEST SCHEMAS
# ═══════════════════════════════════════════════════════════

class BirthDataInput(BaseModel):
    birth_date: date = Field(..., description="Date of birth (YYYY-MM-DD)")
    birth_time: Optional[str] = Field(
        None,
        description="Time of birth (HH:MM, 24h). Omit if unknown.",
        pattern=r"^\d{2}:\d{2}$",
    )
    birth_place: str = Field(..., min_length=2, max_length=255)
    house_system: str = Field(
        "placidus",
        pattern=r"^(placidus|koch|whole_sign|equal)$",
    )

    @field_validator("birth_date")
    @classmethod
    def validate_date_range(cls, v: date) -> date:
        if v.year < 1900:
            raise ValueError("Dates before 1900 are not supported (ephemeris data limitation).")
        if v.year > 2100:
            raise ValueError("Dates after 2100 are not supported.")
        if v > date.today():
            raise ValueError("Birth date cannot be in the future.")
        return v

    @field_validator("birth_time")
    @classmethod
    def validate_time_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        parts = v.split(":")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Invalid time: {v}. Expected HH:MM (00:00–23:59).")
        return v


class TransitRequest(BaseModel):
    from_date: date
    to_date: date

    @model_validator(mode="after")
    def validate_date_range(self) -> "TransitRequest":
        if self.to_date <= self.from_date:
            raise ValueError("to_date must be after from_date.")
        delta = (self.to_date - self.from_date).days
        if delta > 366:
            raise ValueError("Transit period cannot exceed 1 year (366 days).")
        return self


# ═══════════════════════════════════════════════════════════
# AUTH SCHEMAS
# ═══════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 chars)")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address.")
        return v.lower().strip()


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class GoogleOAuthRequest(BaseModel):
    code: str
    redirect_uri: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    email: str
    tier: str = "free"


class UserProfileResponse(BaseModel):
    id: str
    email: str
    tier: str
    is_email_confirmed: bool = False
    stripe_customer_id: Optional[str] = None
    created_at: Optional[str] = None


class MessageResponse(BaseModel):
    message: str


# ═══════════════════════════════════════════════════════════
# PAYMENTS SCHEMAS
# ═══════════════════════════════════════════════════════════

class CheckoutRequest(BaseModel):
    tier: str = Field(..., description="Subscription tier: pro or premium")
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    url: str


class PortalRequest(BaseModel):
    return_url: str


class PortalResponse(BaseModel):
    url: str


class SubscriptionResponse(BaseModel):
    tier: str
    status: str
    stripe_subscription_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    current_period_end: Optional[str] = None


# ═══════════════════════════════════════════════════════════
# CHART RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════

class PlanetPosition(BaseModel):
    name: str
    longitude: float
    sign: str
    degree_in_sign: float
    house: Optional[int] = None
    retrograde: bool = False


class HouseData(BaseModel):
    number: int
    sign: str
    degree: float


class AspectData(BaseModel):
    planet1: str
    planet2: str
    aspect_type: str
    angle: float
    orb: float
    applying: bool


class PointData(BaseModel):
    sign: str
    degree: float
    longitude: float


class NatalChartResponse(BaseModel):
    id: str
    birth_date: str
    birth_time: Optional[str]
    birth_place: str
    latitude: float
    longitude: float
    timezone: str
    time_unknown: bool
    house_system: str
    planets: list[PlanetPosition]
    houses: list[HouseData]
    aspects: list[AspectData]
    ascendant: Optional[PointData] = None
    midheaven: Optional[PointData] = None
    warnings: list[str] = []


class TransitEvent(BaseModel):
    start_date: str
    peak_date: str
    end_date: str
    transit_planet: str
    transit_sign: str = ""
    natal_planet: str
    natal_sign: str = ""
    aspect_type: str
    peak_orb: float
    exact_date: Optional[str] = None
    applying: bool = True

    # backward-compat aliases
    @property
    def date(self) -> str:
        return self.peak_date

    @property
    def orb(self) -> float:
        return self.peak_orb


class TransitPlanetPosition(BaseModel):
    name: str
    longitude: float
    sign: str
    degree_in_sign: float
    retrograde: bool
    glyph: str


class TransitResponse(BaseModel):
    chart_id: str
    from_date: str
    to_date: str
    events: list[TransitEvent]


class TransitPlanetPositionsResponse(BaseModel):
    date: str
    planets: list[TransitPlanetPosition]


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str


class ErrorResponse(BaseModel):
    detail: str
