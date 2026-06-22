"""MemoryAgent 状态定义。"""
from __future__ import annotations
from typing import Optional
from typing_extensions import TypedDict


class MemoryState(TypedDict):
    # ── 输入（从主图映射） ──
    user_id: str
    session_id: str                    # SSE 推送用

    # ── 输出（写回主图） ──
    user_preference: Optional[dict]
    is_new_user: bool
