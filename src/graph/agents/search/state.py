"""SearchAgent 状态定义。"""
from __future__ import annotations
from typing import Optional
from typing_extensions import TypedDict


class SearchState(TypedDict):
    # ── 输入（从主图映射） ──
    resolved_location: str
    search_keywords: list[str]
    price_max: Optional[int]
    price_min: Optional[int]
    feature_requests: list[str]
    user_query: str  # fallback keyword
    user_preference: Optional[dict]   # 用户偏好（供 plan_search 使用）
    search_strategy_hint: Optional[dict]  # Supervisor 给的搜索策略
    tried_keywords: list[str]             # 已尝试的关键词
    session_id: str                       # SSE 推送用
    pending_request_for_search_agent: Optional[dict]  # 来自 RecommendAgent 的委派请求

    # ── 输出（写回主图） ──
    filtered_pois: list[dict]
    agent_messages: list   # 写回主图，触发协作

    # ── 内部字段 ──
    raw_pois: list[dict]
    current_radius: int
    retry_count: int
