"""LocationAgent 状态定义。"""
from __future__ import annotations
from typing import Optional
from typing_extensions import TypedDict


class LocationState(TypedDict):
    # ── 输入（从主图映射） ──
    location_hint: Optional[str]
    user_ip: Optional[str]
    user_location: Optional[str]
    user_city: Optional[str]
    home_city: Optional[str]
    prev_search_context: Optional[dict]
    user_query: str                     # 用户原始查询（供 reason_location 推理）
    conversation_history: Optional[str] # 对话历史（供 reason_location 推理上下文）
    session_id: str                     # SSE 推送用
    pending_request_for_location_agent: Optional[dict]  # 来自 RecommendAgent 的委派请求

    # ── 输出（写回主图） ──
    resolved_location: Optional[str]
    user_city_code: Optional[str]

    # ── 内部字段 ──
    geocode_success: bool
