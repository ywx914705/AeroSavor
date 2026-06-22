"""反馈接口。"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime as dt, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.logging import get_logger
from ..models import Interaction
from ..monitoring.metrics import user_feedback_total
from ..services.memory_service import memory_service
from .auth import CurrentUser, get_current_user

logger = get_logger(__name__)

router = APIRouter(prefix="", tags=["feedback"])


class FeedbackRequest(BaseModel):
    session_id: str
    poi_id: str
    poi_name: str | None = None
    action: str  # liked / disliked / navigated / clicked / visited
    rating: int | None = None


@router.post("/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.action not in {
        "viewed",
        "clicked",
        "navigated",
        "liked",
        "disliked",
        "visited",
    }:
        return {"status": "ignored", "reason": "unknown action"}

    inter = Interaction(
        user_id=uuid.UUID(current_user.id),
        session_id=uuid.UUID(req.session_id) if req.session_id else None,
        poi_id=req.poi_id,
        poi_name=req.poi_name or "",
        action=req.action,
        rating=req.rating,
        hour_of_day=dt.now(timezone.utc).hour,
    )
    db.add(inter)
    await db.commit()

    # 指标埋点
    user_feedback_total.labels(action=req.action).inc()

    # 后台异步更新偏好向量（仅强信号）
    if req.action in {"liked", "navigated", "clicked"}:
        asyncio.create_task(memory_service.update_preference_embedding(current_user.id))

    return {"status": "ok"}