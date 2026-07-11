"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Boolean, DateTime, ForeignKey, Text, JSON, Integer,
    Date, Time, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=True)  # nullable for OAuth users
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    is_email_confirmed = Column(Boolean, default=False, nullable=False, server_default="false")
    tier = Column(String(20), default="free", nullable=False, server_default="free")  # free / lite / pro / premium
    google_sub = Column(String(255), nullable=True, unique=True)
    stripe_customer_id = Column(String(255), nullable=True, unique=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expert_mode = Column(Boolean, default=False, nullable=False, server_default="false")

    # First free interpretation (3.3) — одноразовый «вкус» для Free, навсегда
    free_interpretation_used = Column(
        Boolean, default=False, nullable=False, server_default="false"
    )

    # Referral (011)
    referral_code = Column(String(16), unique=True, nullable=True)
    referred_by   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Digest settings (012)
    digest_day_of_week = Column(Integer, nullable=False, default=0, server_default="0")

    # Push notification preferences (031)
    push_daily_forecast = Column(Boolean, nullable=False, default=True, server_default="true")
    push_daily_time     = Column(String(5), nullable=False, default="08:00", server_default="08:00")  # "HH:MM", локально по tz главной карты
    push_planner        = Column(Boolean, nullable=False, default=True, server_default="true")
    push_key_transits   = Column(Boolean, nullable=False, default=True, server_default="true")

    # Primary chart (018) — карта относительно которой строятся письма, планер, натальная карта
    primary_chart_id = Column(
        String(36),
        ForeignKey("natal_charts.id", ondelete="SET NULL", use_alter=True, name="fk_user_primary_chart"),
        nullable=True,
    )

    charts = relationship(
        "NatalChart",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="NatalChart.user_id",
    )
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")


class NatalChart(Base):
    __tablename__ = "natal_charts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    label = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)

    birth_date = Column(String(10), nullable=False)
    birth_time = Column(String(5), nullable=True)
    birth_place = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    timezone = Column(String(50), nullable=False)
    utc_datetime = Column(DateTime, nullable=True)
    time_unknown = Column(Boolean, default=False)

    planets = Column(JSON, nullable=False)
    houses = Column(JSON, nullable=False)
    aspects = Column(JSON, nullable=False)
    ascendant = Column(JSON, nullable=True)
    midheaven = Column(JSON, nullable=True)
    house_system = Column(String(20), default="placidus")
    public_token = Column(String(64), nullable=True, unique=True, index=True)
    share_name   = Column(String(100), nullable=True)  # имя для публичной страницы

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="charts", foreign_keys=[user_id])
    interpretations = relationship(
        "Interpretation", back_populates="chart", cascade="all, delete-orphan"
    )


class Interpretation(Base):
    __tablename__ = "interpretations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    chart_id = Column(String(36), ForeignKey("natal_charts.id"), nullable=False, index=True)
    profile_hash = Column(String(64), nullable=False, index=True)
    engine = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    sections = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    chart = relationship("NatalChart", back_populates="interpretations")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    stripe_subscription_id = Column(String(255), nullable=True, unique=True)
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_price_id = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="active")
    tier = Column(String(20), nullable=False, default="free")
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="subscriptions")


class CouponSent(Base):
    __tablename__ = "coupons_sent"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    coupon_id = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── CRM (013) ──

class AstrologerProfile(Base):
    __tablename__ = "astrologer_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    display_name = Column(String(100), nullable=True)
    broadcast_auto = Column(Boolean, default=False, nullable=False, server_default="false")  # автоотправка 1-го числа (022)

    clients = relationship("ClientProfile", back_populates="astrologer", cascade="all, delete-orphan")


class ClientProfile(Base):
    __tablename__ = "client_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    astrologer_id = Column(Integer, ForeignKey("astrologer_profiles.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    birth_date = Column(Date, nullable=False)
    birth_time = Column(Time, nullable=True)
    birth_place = Column(String(200), nullable=False)
    notes = Column(Text, nullable=True)
    email = Column(String(255), nullable=True)  # для рассылки (021)
    status = Column(String(20), nullable=False, default="lead", server_default="lead")  # lead/active/regular/archived (025)
    source = Column(String(100), nullable=True)  # откуда пришёл (025)
    tags = Column(JSON, nullable=True)  # свободные метки (029)
    unsubscribe_token = Column(String(64), nullable=True, unique=True, index=True)  # (022)
    broadcast_opt_out = Column(Boolean, default=False, nullable=False, server_default="false")  # (022)
    summary = Column(Text, nullable=True)          # AI-портрет клиента, кэш (024)
    summary_key = Column(String(64), nullable=True)  # хэш заметок+консультаций+карты
    created_at = Column(DateTime, default=datetime.utcnow)
    natal_chart_id = Column(String(36), ForeignKey("natal_charts.id", ondelete="SET NULL"), nullable=True)

    astrologer = relationship("AstrologerProfile", back_populates="clients")
    consultations = relationship(
        "Consultation",
        back_populates="client",
        cascade="all, delete-orphan",
        order_by="Consultation.date.desc()",
    )


# ── Consultations (020) ──

class Consultation(Base):
    __tablename__ = "consultations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(
        Integer, ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date = Column(DateTime, nullable=False, default=datetime.utcnow)
    topic = Column(String(50), nullable=True)     # натал / соляр / хорар / синастрия / транзиты / другое
    notes = Column(Text, nullable=True)
    assignment = Column(Text, nullable=True)       # домашнее задание клиенту (026, для портала)
    next_date = Column(DateTime, nullable=True)
    price = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="done", server_default="done")  # planned / done / canceled
    question_moment = Column(DateTime, nullable=True)   # хорар: момент вопроса (027)
    question_place = Column(String(200), nullable=True)  # хорар: место вопроса (027)
    horary_chart_id = Column(String(36), ForeignKey("natal_charts.id", ondelete="SET NULL"), nullable=True)  # (027)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("ClientProfile", back_populates="consultations")


# ── Client broadcasts (021 / roadmap idea 5) ──

class ClientBroadcastLog(Base):
    __tablename__ = "client_broadcast_log"
    __table_args__ = (
        UniqueConstraint("astrologer_id", "client_id", "period_ym", name="uq_broadcast_astro_client_period"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    astrologer_id = Column(
        Integer, ForeignKey("astrologer_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id = Column(
        Integer, ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_ym = Column(String(7), nullable=False)   # "YYYY-MM"
    status = Column(String(10), nullable=False)     # "success" | "error"
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Client intake forms (023 / roadmap idea 6) ──

class ClientIntake(Base):
    __tablename__ = "client_intake"

    id = Column(Integer, primary_key=True, autoincrement=True)
    astrologer_id = Column(
        Integer, ForeignKey("astrologer_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, default="pending", server_default="pending")  # pending / converted / archived
    submitted_data = Column(JSON, nullable=True)   # {name, birth_date, birth_time, birth_place, email, question}
    submitted_at = Column(DateTime, nullable=True)
    client_id = Column(Integer, ForeignKey("client_profiles.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Client portal (026 / roadmap idea 10) ──

class ClientPortalAccess(Base):
    __tablename__ = "client_portal_access"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(
        Integer, ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    token = Column(String(64), nullable=False, unique=True, index=True)
    enabled = Column(Boolean, default=True, nullable=False, server_default="true")
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Author interpretations library (028 / roadmap idea 13) ──

class AstrologerInterpretation(Base):
    __tablename__ = "astrologer_interpretations"
    __table_args__ = (
        UniqueConstraint("astrologer_id", "key", name="uq_author_interp_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    astrologer_id = Column(
        Integer, ForeignKey("astrologer_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key = Column(String(100), nullable=False)     # напр. "saturn_house_7", "sun_taurus", "asc_leo"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Note templates (016) ──

class NoteTemplate(Base):
    __tablename__ = "note_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Calendar export log (017) ──

class CalendarExportLog(Base):
    __tablename__ = "calendar_export_logs"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    month      = Column(String(7), nullable=False)          # "YYYY-MM"
    event_count= Column(Integer, nullable=False, default=0)
    event_types= Column(JSON, nullable=False, default=list) # ["new_moon", "aspect", ...]
    status     = Column(String(10), nullable=False)         # "success" | "error"
    error_msg  = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Gift codes (014) ──

class GiftCode(Base):
    __tablename__ = "gift_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(16), unique=True, nullable=False)
    tier = Column(String(20), nullable=False)
    duration_months = Column(Integer, nullable=False)
    purchased_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    redeemed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    redeemed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Usage counters (3.3 / 3.4a) ──
# Persistent per-user, per-kind, per-calendar-month counters.
# Переживают рестарт сервера и дают настоящий календарный месяц
# (в отличие от прежнего in-memory 24h-счётчика).
#   kind:      "interpretation" | "transit_ai"
#   period_ym: "YYYY-MM"
# UNIQUE(user_id, kind, period_ym) — на пользователя ровно одна строка на месяц.

class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "period_ym", name="uq_usage_user_kind_period"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(String(32), nullable=False)       # "interpretation" | "transit_ai"
    period_ym = Column(String(7), nullable=False)   # "YYYY-MM"
    count = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Push notifications (031) ──
# Web Push подписки устройств пользователя (может быть несколько на юзера).
class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint = Column(Text, nullable=False, unique=True)  # URL push-сервиса (уникален)
    p256dh   = Column(Text, nullable=False)               # публичный ключ клиента
    auth     = Column(Text, nullable=False)               # auth-секрет клиента
    created_at = Column(DateTime, default=datetime.utcnow)


# Журнал отправленных пушей — дедупликация (один пуш на событие).
#   kind:    "daily" | "planner" | "transit"
#   ref_key: уникальный ключ события (дата дня / planet:house:start / tp:np:aspect:start)
class PushSentLog(Base):
    __tablename__ = "push_sent_log"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "ref_key", name="uq_push_sent_user_kind_ref"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind    = Column(String(16), nullable=False)
    ref_key = Column(String(128), nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
