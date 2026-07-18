"""Pydantic schemas for request validation and response serialization."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator, AnyHttpUrl


# ═══════════════════════════════════════════════════════════
# CHART REQUEST SCHEMAS
# ═══════════════════════════════════════════════════════════

class BirthDataInput(BaseModel):
    name: Optional[str] = Field(None, max_length=100, description="Имя пользователя для персонализации")
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
            raise ValueError("Даты до 1900 не поддерживаются (ограничение эфемерид).")
        if v.year > 2100:
            raise ValueError("Даты после 2100 не поддерживаются.")
        if v > date.today():
            raise ValueError("Дата рождения не может быть в будущем.")
        return v

    @field_validator("birth_time")
    @classmethod
    def validate_time_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        parts = v.split(":")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Неверное время: {v}. Ожидается HH:MM (00:00–23:59).")
        return v

    @field_validator("birth_place")
    @classmethod
    def validate_place(cls, v: str) -> str:
        v = v.strip()
        if re.search(r"[<>{}\[\]\\]", v):
            raise ValueError("Название места содержит недопустимые символы.")
        return v


class CoordinatesInput(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)

    @field_validator("latitude")
    @classmethod
    def lat_not_pole(cls, v: float) -> float:
        if abs(v) > 89.9:
            raise ValueError("Широта слишком близка к полюсу (|lat| ≤ 89.9°).")
        return round(v, 6)

    @field_validator("longitude")
    @classmethod
    def lon_precision(cls, v: float) -> float:
        return round(v, 6)


class TransitRequest(BaseModel):
    from_date: date
    to_date: date

    @model_validator(mode="after")
    def validate_date_range(self) -> "TransitRequest":
        if self.to_date <= self.from_date:
            raise ValueError("to_date должна быть позже from_date.")
        delta = (self.to_date - self.from_date).days
        if delta > 366:
            raise ValueError("Период транзитов не может превышать 1 год (366 дней).")
        return self


# ═══════════════════════════════════════════════════════════
# AUTH SCHEMAS
# ═══════════════════════════════════════════════════════════

# Разрешённые российские почтовые домены
RU_EMAIL_DOMAINS: frozenset[str] = frozenset({
    "yandex.ru", "ya.ru",
    "mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru",
    "rambler.ru", "lenta.ru", "autorambler.ru", "myrambler.ru", "ro.ru",
})

_RU_DOMAIN_ERROR = (
    "Принимаем только почту российских сервисов: "
    "Яндекс (yandex.ru), Mail.ru, Rambler и другие."
)


def _validate_ru_email(v: str) -> str:
    v = v.lower().strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", v):
        raise ValueError("Некорректный email-адрес.")
    if len(v) > 254:
        raise ValueError("Email слишком длинный (макс. 254 символа).")
    domain = v.split("@")[1]
    if domain not in RU_EMAIL_DOMAINS:
        raise ValueError(_RU_DOMAIN_ERROR)
    return v


def _validate_password(v: str) -> str:
    """Делегирует единой политике из backend.auth.passwords."""
    from backend.auth.passwords import validate_password

    return validate_password(v)


# ── Старая схема — сохранена для тестов и обратной совместимости ──

class RegisterRequest(BaseModel):
    email: str = Field(..., description="Email пользователя")
    password: str = Field(..., min_length=8, max_length=128)
    ref_code: Optional[str] = Field(None, max_length=16)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.lower().strip()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", v):
            raise ValueError("Некорректный email-адрес.")
        if len(v) > 254:
            raise ValueError("Email слишком длинный (макс. 254 символа).")
        return v

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        return _validate_password(v)


# ── OTP-регистрация по email ──

class SendEmailOTPRequest(BaseModel):
    email: str = Field(..., description="Email российского сервиса")
    password: str = Field(..., min_length=8, max_length=128)
    name: Optional[str] = Field(None, max_length=100)
    ref_code: Optional[str] = Field(None, max_length=16)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _validate_ru_email(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password(v)


class VerifyEmailOTPRequest(BaseModel):
    email: str
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()


# ── Общие auth-схемы ──

class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class GoogleOAuthRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=1024)
    redirect_uri: str = Field(..., max_length=2048)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    email: str
    name: Optional[str] = None
    tier: str = "free"
    is_admin: bool = False


class UserProfileResponse(BaseModel):
    id: str
    email: Optional[str] = None
    name: Optional[str] = None
    tier: str
    is_email_confirmed: bool = False
    is_admin: bool = False
    stripe_customer_id: Optional[str] = None
    created_at: Optional[str] = None


class MessageResponse(BaseModel):
    message: str


# ═══════════════════════════════════════════════════════════
# PAYMENTS SCHEMAS
# ═══════════════════════════════════════════════════════════

_VALID_TIERS = {"lite", "pro", "premium"}


class CheckoutRequest(BaseModel):
    tier: str = Field(..., description="Тариф: lite, pro или premium")
    billing_period: str = Field("monthly", description="monthly или annual")
    success_url: str = Field(..., max_length=2048)
    cancel_url: str = Field(..., max_length=2048)
    promo_code: str | None = Field(None)

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        if v not in _VALID_TIERS:
            raise ValueError(f"Tier должен быть одним из: {', '.join(sorted(_VALID_TIERS))}.")
        return v

    @field_validator("billing_period")
    @classmethod
    def validate_billing_period(cls, v: str) -> str:
        if v not in ("monthly", "annual"):
            raise ValueError("billing_period должен быть 'monthly' или 'annual'.")
        return v

    @field_validator("success_url", "cancel_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not re.match(r"^https?://", v):
            raise ValueError("URL должен начинаться с http:// или https://.")
        return v


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalRequest(BaseModel):
    return_url: str = Field(..., max_length=2048)

    @field_validator("return_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not re.match(r"^https?://", v):
            raise ValueError("return_url должен начинаться с http:// или https://.")
        return v


class PortalResponse(BaseModel):
    portal_url: str


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
    longitude: float = Field(..., ge=0.0, lt=360.0)
    sign: str
    degree_in_sign: float = Field(..., ge=0.0, lt=30.0)
    house: Optional[int] = Field(None, ge=1, le=12)
    retrograde: bool = False


class HouseData(BaseModel):
    number: int = Field(..., ge=1, le=12)
    sign: str
    degree: float = Field(..., ge=0.0, lt=360.0)


class AspectData(BaseModel):
    planet1: str
    planet2: str
    aspect_type: str
    angle: float = Field(..., ge=0.0, le=360.0)
    orb: float = Field(..., ge=0.0, le=15.0)
    applying: bool
    importance: str = "low"


class PointData(BaseModel):
    sign: str
    degree: float = Field(..., ge=0.0, lt=30.0)
    longitude: float = Field(..., ge=0.0, lt=360.0)


class NatalChartResponse(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    birth_date: str
    birth_time: Optional[str]
    birth_place: str
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
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
    transit_degree: float = 0.0
    natal_planet: str
    natal_sign: str = ""
    aspect_type: str
    peak_orb: float = Field(..., ge=0.0, le=15.0)
    exact_date: Optional[str] = None
    applying: bool = True
    significant: bool = False
    free_unlocked: bool = False

    @property
    def date(self) -> str:
        return self.peak_date

    @property
    def orb(self) -> float:
        return self.peak_orb


class TransitPlanetPosition(BaseModel):
    name: str
    longitude: float = Field(..., ge=0.0, lt=360.0)
    sign: str
    degree_in_sign: float = Field(..., ge=0.0, lt=30.0)
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
