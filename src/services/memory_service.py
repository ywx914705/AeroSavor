"""记忆系统统一入口。

计划书 6.2 节要求 MemoryService 类作为记忆系统的统一接口，
封装三层记忆：短期（MemorySaver）、长期（interactions）、向量（user_preference_embeddings）。

当前短期记忆由 LangGraph MemorySaver 管理，本模块聚焦长期记忆和向量记忆。
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import db_session
from ..core.logging import get_logger
from ..models import Interaction, UserPreferenceEmbedding
from .preference_service import (
    get_user_preference,
    update_user_preference_embedding,
)

logger = get_logger(__name__)


class MemoryService:
    """记忆系统的统一入口（计划书 6.2 节）。"""

    # ──────────────────────────────────────────────
    # 读取接口（对话开始时调用）
    # ──────────────────────────────────────────────

    @staticmethod
    async def get_user_preference(
        user_id: str | uuid.UUID,
        db: AsyncSession | None = None,
    ) -> Optional[dict]:
        """
        读取用户偏好，返回结构化数据 + 向量。
        冷启动用户返回 None。
        """
        if db is not None:
            return await get_user_preference(db, user_id)

        async with db_session() as session:
            return await get_user_preference(session, user_id)

    # ──────────────────────────────────────────────
    # 更新接口（对话结束后异步调用）
    # ──────────────────────────────────────────────

    @staticmethod
    async def update_preference_embedding(user_id: str | uuid.UUID) -> None:
        """
        从最近 30 条有效交互重新生成用户偏好向量。
        整个过程异步执行，不阻塞用户响应。
        """
        await update_user_preference_embedding(user_id)

    # ──────────────────────────────────────────────
    # 交互记录接口
    # ──────────────────────────────────────────────

    @staticmethod
    async def record_interaction(
        user_id: str | uuid.UUID,
        session_id: str | uuid.UUID | None = None,
        poi: dict | None = None,
        action: str = "viewed",
        context: dict | None = None,
    ) -> None:
        """记录一次用户与餐厅的交互。"""
        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        sid = uuid.UUID(session_id) if isinstance(session_id, str) else session_id
        context = context or {}
        poi = poi or {}

        async with db_session() as db:
            db.add(
                Interaction(
                    user_id=uid,
                    session_id=sid,
                    poi_id=str(poi.get("id", "")),
                    poi_name=str(poi.get("name", "")),
                    poi_type=str(poi.get("type", ""))[:100] or None,
                    poi_typecode=str(poi.get("typecode", ""))[:20] or None,
                    poi_rating=float(poi.get("rating", 0) or 0) or None,
                    poi_cost=int(poi.get("cost", 0) or 0) or None,
                    poi_location=str(poi.get("location", "")) or None,
                    action=action,
                    search_keyword=context.get("search_keyword"),
                    weather=context.get("weather"),
                    hour_of_day=context.get("hour_of_day"),
                )
            )
            await db.commit()


# 模块级便捷函数（供不想实例化的调用方使用）
memory_service = MemoryService()
