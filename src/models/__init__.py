"""SQLAlchemy 模型。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    JSON,
    TIMESTAMP,
    UUID,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    home_city: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # home_location 用 PG 的 POINT，简化起见这里用 String
    home_location: Mapped[str | None] = mapped_column(String(50), nullable=True)

    default_radius: Mapped[int] = mapped_column(Integer, default=1000)
    # 价格区间用 ARRAY[Integer]
    price_preference: Mapped[list[int] | None] = mapped_column(
        ARRAY(Integer), nullable=True
    )

    search_count: Mapped[int] = mapped_column(Integer, default=0)
    last_active: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    messages: Mapped[list] = mapped_column(JSONB, default=list)

    title: Mapped[str | None] = mapped_column(String(100), nullable=True)

    last_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_search_keys: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )
    # 多轮对话的结构化搜索上下文（关键词、价格、特征等）。
    # 不要塞到 last_location，那是给坐标用的。
    search_context: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    poi_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    poi_name: Mapped[str] = mapped_column(String(200), nullable=False)
    poi_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    poi_typecode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    poi_rating: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    poi_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    poi_location: Mapped[str | None] = mapped_column(Text, nullable=True)

    action: Mapped[str] = mapped_column(String(20), nullable=False)
    # viewed / clicked / navigated / liked / disliked / visited

    search_keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    weather: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hour_of_day: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # 个性化排序分数明细（简历佐证："个性化推荐"有数据支撑）
    # 格式: {"amap": 0.8, "preference": 0.6, "distance": 0.9, "price": 0.7, "final": 0.72}
    score_breakdown: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserPreferenceEmbedding(Base):
    __tablename__ = "user_preference_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        unique=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # text-embedding-v3 (DashScope) → 1024 维
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)

    preference_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    preferred_cuisines: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )
    disliked_cuisines: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )
    price_range: Mapped[list[int] | None] = mapped_column(
        ARRAY(Integer), nullable=True
    )
    min_rating: Mapped[float | None] = mapped_column(Numeric(2, 1), nullable=True)
    preferred_features: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )


class POICache(Base):
    __tablename__ = "poi_cache"

    poi_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    typecode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tel: Mapped[str | None] = mapped_column(String(100), nullable=True)

    rating: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_time: Mapped[str | None] = mapped_column(Text, nullable=True)

    photos: Mapped[list] = mapped_column(JSONB, default=list)

    view_count: Mapped[int] = mapped_column(Integer, default=0)
    click_count: Mapped[int] = mapped_column(Integer, default=0)
    nav_count: Mapped[int] = mapped_column(Integer, default=0)

    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "poi_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    poi_id: Mapped[str] = mapped_column(String(50), nullable=False)
    poi_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
