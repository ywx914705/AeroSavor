"""RecommendAgent 状态定义。"""
from __future__ import annotations
from typing import Optional
from typing_extensions import TypedDict


class RecommendState(TypedDict):
    # ── 输入（从主图映射） ──
    filtered_pois: list[dict]
    user_preference: Optional[dict]
    weather: Optional[dict]
    user_query: str
    is_new_user: bool
    price_max: Optional[int]
    feature_requests: list[str]
    declared_preferences: Optional[dict]
    user_id: str
    iteration_count: int   # 从主图传入，用于强制跳过质量检查
    session_id: str        # SSE 推送用

    # ── 输出（写回主图） ──
    recommendations: list[dict]
    final_response: str
    show_cold_start_guide: bool
    quality_check_passed: bool   # 质量评估结果（写回主图）
    agent_messages: list         # 写回主图，触发协作

    # ── 内部字段 ──
    ranked_pois: list[dict]
