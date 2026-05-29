"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Boolean, DateTime, ForeignKey, Text, JSON, Integer
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

    charts = relationship("NatalChart", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")


class NatalChart(Base):
    __tablename__ = "natal_charts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    label = Column(String(255), nullable=True)

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

    user = relationship("User", back_populates="charts")
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
