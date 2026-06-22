"""会话管理服务。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Session as SessionModel
from ..models import User


async def get_or_create_session(
    db: AsyncSession,
    session_id: str,
    user_id: str | uuid.UUID,
) -> SessionModel:
    """通过 session_id 获取，不存在则创建。"""
    sid = uuid.UUID(session_id) if isinstance(session_id, str) else session_id
    uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

    res = await db.execute(select(SessionModel).where(SessionModel.id == sid))
    sess = res.scalar_one_or_none()
    if sess is not None:
        return sess

    sess = SessionModel(id=sid, user_id=uid, messages=[])
    db.add(sess)
    await db.commit()
    await db.refresh(sess)
    return sess


async def save_search_context(
    db: AsyncSession,
    session_id: str | uuid.UUID,
    context: dict,
) -> None:
    """保存本次搜索的结构化上下文到 session（供下一轮多轮对话用）。

    存到独立的 search_context JSONB 字段，不再污染 last_location。
    """
    sid = uuid.UUID(session_id) if isinstance(session_id, str) else session_id
    res = await db.execute(select(SessionModel).where(SessionModel.id == sid))
    sess = res.scalar_one_or_none()
    if sess is None:
        return
    sess.search_context = context
    # 顺便把坐标放回真正用于坐标的字段
    if context.get("location"):
        sess.last_location = context["location"]
    if context.get("keywords"):
        sess.last_search_keys = list(context["keywords"])
    await db.commit()


async def get_prev_search_context(
    db: AsyncSession,
    session_id: str | uuid.UUID,
) -> dict | None:
    """读取上一轮搜索上下文。"""
    sid = uuid.UUID(session_id) if isinstance(session_id, str) else session_id
    res = await db.execute(select(SessionModel).where(SessionModel.id == sid))
    sess = res.scalar_one_or_none()
    if sess is None:
        return None
    if sess.search_context:
        return dict(sess.search_context)
    # 兼容旧数据：search_context 为空时尝试从 last_location 解 JSON
    if sess.last_location and sess.last_location.startswith("{"):
        try:
            return json.loads(sess.last_location)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


async def append_message(
    db: AsyncSession,
    session_id: str | uuid.UUID,
    role: str,
    content: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """追加一条消息（基于 PG JSONB 的 ||）。"""
    sid = uuid.UUID(session_id) if isinstance(session_id, str) else session_id

    msg = {"role": role, "content": content, "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        msg.update(extra)

    res = await db.execute(select(SessionModel).where(SessionModel.id == sid))
    sess = res.scalar_one_or_none()
    if sess is None:
        return

    msgs = list(sess.messages or [])
    msgs.append(msg)
    sess.messages = msgs
    sess.turn_count = (sess.turn_count or 0) + (1 if role == "user" else 0)

    # 自动命名：首条用户消息且尚无标题时，取前 30 字符作为标题
    if role == "user" and not sess.title:
        text = content.strip().replace("\n", " ")
        sess.title = text[:30] + ("..." if len(text) > 30 else "")

    await db.commit()


async def get_or_create_default_user(
    db: AsyncSession, user_id: str | None = None
) -> User:
    """开发模式：没有 user_id 时返回/创建默认用户。"""
    if user_id:
        uid = uuid.UUID(user_id)
        res = await db.execute(select(User).where(User.id == uid))
        u = res.scalar_one_or_none()
        if u is not None:
            return u

    # 默认用户
    default_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    res = await db.execute(select(User).where(User.id == default_id))
    u = res.scalar_one_or_none()
    if u is not None:
        return u

    u = User(id=default_id, nickname="demo")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def update_user_home_city(
    db: AsyncSession,
    user_id: str | uuid.UUID,
    city: str,
) -> bool:
    """把已识别的城市写入 users.home_city（永久层）。

    只有命中本系统已知城市表的字符串才会被写入，避免把"望京 SOHO"这种点位
    或拼写错误的非城市文本污染永久记忆。已存在的 home_city 允许被新陈述覆盖
    （用户表达的意愿优先于历史值，例如用户从北京搬到成都）。

    支持区级地点自动提取城市名，如 "成都武侯" → "成都"。

    返回是否实际写入。
    """
    from ..tools.amap_client import extract_city_name, is_known_city

    # 先尝试从完整地点中提取城市名（如 "成都武侯" → "成都"）
    city_name = extract_city_name(city) or city
    if not is_known_city(city_name):
        return False

    uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    res = await db.execute(select(User).where(User.id == uid))
    u = res.scalar_one_or_none()
    if u is None:
        return False
    if u.home_city == city_name:
        return False  # 没变，跳过 commit
    u.home_city = city_name
    await db.commit()
    return True


async def get_user(
    db: AsyncSession, user_id: str | uuid.UUID
) -> User | None:
    """按 ID 取用户对象（含 home_city 等永久层字段）。"""
    uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    res = await db.execute(select(User).where(User.id == uid))
    return res.scalar_one_or_none()
