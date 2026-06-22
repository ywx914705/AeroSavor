"""历史 / 收藏接口。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models import Favorite, Session as SessionModel
from .auth import CurrentUser, get_current_user

router = APIRouter(prefix="", tags=["history"])


# ──────────── Schema ────────────


class AddFavoriteRequest(BaseModel):
    poi_id: str
    poi_name: str
    note: str | None = None


class RemoveFavoriteRequest(BaseModel):
    poi_id: str


# ──────────── 历史 ────────────


@router.get("/history")
async def get_history(
    limit: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(SessionModel)
        .where(
            SessionModel.user_id == uuid.UUID(current_user.id),
            SessionModel.is_active.is_(True),
        )
        .order_by(desc(SessionModel.updated_at))
        .limit(limit)
    )
    sessions = res.scalars().all()
    out = []
    for s in sessions:
        msgs = s.messages or []
        last = msgs[-1] if msgs else {}
        # 优先用 title 字段，其次用最后一条消息
        display = s.title or (last.get("content", "") if isinstance(last, dict) else "")
        out.append(
            {
                "id": str(s.id),
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                "turn_count": s.turn_count,
                "last_message": display,
                "title": s.title,
            }
        )
    return out


@router.get("/sessions/{session_id}")
async def get_session_messages(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个会话的完整对话历史（用于点击侧边栏恢复会话）。"""
    sid = uuid.UUID(session_id)
    uid = uuid.UUID(current_user.id)

    res = await db.execute(
        select(SessionModel).where(
            SessionModel.id == sid,
            SessionModel.user_id == uid,
        )
    )
    session = res.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = session.messages or []
    return {
        "id": str(session.id),
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        "turn_count": session.turn_count,
        "messages": messages,
    }


# ──────────── 删除 / 重命名 ────────────


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sid = uuid.UUID(session_id)
    uid = uuid.UUID(current_user.id)

    res = await db.execute(
        select(SessionModel).where(
            SessionModel.id == sid,
            SessionModel.user_id == uid,
        )
    )
    session = res.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 软删除
    session.is_active = False
    await db.commit()
    return {"status": "ok"}


class RenameSessionRequest(BaseModel):
    title: str


@router.patch("/sessions/{session_id}")
async def rename_session(
    session_id: str,
    req: RenameSessionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sid = uuid.UUID(session_id)
    uid = uuid.UUID(current_user.id)

    res = await db.execute(
        select(SessionModel).where(
            SessionModel.id == sid,
            SessionModel.user_id == uid,
        )
    )
    session = res.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    session.title = req.title.strip()[:100]
    await db.commit()
    return {"status": "ok", "title": session.title}


# ──────────── 收藏 ────────────


@router.get("/favorites")
async def get_favorites(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Favorite)
        .where(Favorite.user_id == uuid.UUID(current_user.id))
        .order_by(desc(Favorite.created_at))
    )
    favs = res.scalars().all()
    return [
        {
            "poi_id": f.poi_id,
            "poi_name": f.poi_name,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "note": f.note,
        }
        for f in favs
    ]


@router.post("/favorites")
async def add_favorite(
    req: AddFavoriteRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = uuid.UUID(current_user.id)
    # 幂等：已存在则更新 note
    existing = await db.execute(
        select(Favorite).where(
            Favorite.user_id == uid,
            Favorite.poi_id == req.poi_id,
        )
    )
    fav = existing.scalar_one_or_none()
    if fav:
        if req.note is not None:
            fav.note = req.note
        await db.commit()
        return {"status": "ok", "action": "updated"}
    fav = Favorite(
        user_id=uid,
        poi_id=req.poi_id,
        poi_name=req.poi_name,
        note=req.note,
    )
    db.add(fav)
    await db.commit()
    return {"status": "ok", "action": "added"}


@router.delete("/favorites")
async def remove_favorite(
    req: RemoveFavoriteRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = uuid.UUID(current_user.id)
    existing = await db.execute(
        select(Favorite).where(
            Favorite.user_id == uid,
            Favorite.poi_id == req.poi_id,
        )
    )
    fav = existing.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="未收藏此餐厅")
    await db.delete(fav)
    await db.commit()
    return {"status": "ok", "action": "removed"}