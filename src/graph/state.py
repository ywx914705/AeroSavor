"""AeroSavor 主图状态定义。

SupervisorState 只保留跨 Agent 必须共享的字段。
每个子图的中间状态留在子图内部，不暴露给主图。
"""
from __future__ import annotations

from typing import Annotated, Optional

from langgraph.graph.message import add_messages
from operator import add
from typing_extensions import TypedDict


class SupervisorState(TypedDict):
    # ── 对话基础 ──────────────────────────────
    messages: Annotated[list, add_messages]
    user_query: str
    session_id: str
    user_id: str
    user_ip: Optional[str]

    # ── Supervisor 解析结果 ───────────────────
    intent: str                               # search/route/compare/chat/clarify
    chat_type: Optional[str]                  # chat 子类型：greeting/identity/feature/social/location_confirm/chat
    search_keywords: list[str]
    location_hint: Optional[str]
    price_max: Optional[int]
    price_min: Optional[int]
    feature_requests: list[str]
    need_route: bool
    is_followup: bool
    target_poi_name: Optional[str]
    target_poi_id: Optional[str]
    declared_preferences: Optional[dict]

    # ── 各子图输出（子图写，Supervisor 读） ────
    resolved_location: Optional[str]          # LocationAgent → "lng,lat"
    user_city: Optional[str]                 # LocationAgent → 城市名
    user_city_code: Optional[str]            # LocationAgent → 高德城市编码
    user_preference: Optional[dict]           # MemoryAgent → 偏好数据
    is_new_user: bool                         # MemoryAgent → 是否冷启动
    weather: Optional[dict]                   # 天气
    filtered_pois: list[dict]                 # SearchAgent → 过滤后餐厅列表
    recommendations: list[dict]               # RecommendAgent → Top3 推荐
    route_info: Optional[dict]                # RouteAgent → 路线信息

    # ── 跨轮次上下文 ──────────────────────────
    home_city: Optional[str]
    user_location: Optional[str]
    prev_search_context: Optional[dict]

    # ── 最终输出 ──────────────────────────────
    final_response: str
    chat_prompt: Optional[str]               # ChatAgent → 供 SSE 流式路径复用
    show_cold_start_guide: bool

    # ── Multi-Agent 协作字段 ────────────────────
    agent_messages: Annotated[list, add]      # Agent 间通信消息（自动追加不覆盖）
    completed_steps: Annotated[list, add]     # 已完成步骤记录
    next_action: Optional[str]                # Supervisor 决定的下一步
    supervisor_reason: Optional[str]          # 决策理由（前端展示）
    iteration_count: int                      # 当前协作迭代次数
    quality_check_passed: bool                # RecommendAgent 质量评估结果
    search_strategy_hint: Optional[dict]      # Supervisor 给 SearchAgent 的搜索策略提示
    tried_keywords: Annotated[list, add]      # 已尝试的搜索关键词（避免重复）
    pending_request_for_search_agent: Optional[dict]    # 给 SearchAgent 的待处理请求
    pending_request_for_recommend_agent: Optional[dict] # 给 RecommendAgent 的待处理请求
    pending_request_for_location_agent: Optional[dict]  # 给 LocationAgent 的待处理请求
    delegation_count: int                                # Agent 委派计数（防无限循环）


def make_initial_state(
    user_query: str,
    session_id: str,
    user_id: str,
    user_location: str | None = None,
    user_city: str | None = None,
    home_city: str | None = None,
) -> SupervisorState:
    """构造初始状态。"""
    return {
        "messages": [],
        "user_query": user_query,
        "session_id": session_id,
        "user_id": user_id,
        "user_ip": None,
        "intent": "search",
        "chat_type": None,
        "search_keywords": [],
        "location_hint": None,
        "price_max": None,
        "price_min": None,
        "feature_requests": [],
        "need_route": False,
        "is_followup": False,
        "target_poi_name": None,
        "target_poi_id": None,
        "declared_preferences": None,
        "resolved_location": None,
        "user_city": user_city,
        "user_city_code": None,
        "user_preference": None,
        "is_new_user": True,
        "weather": None,
        "filtered_pois": [],
        "recommendations": [],
        "route_info": None,
        "home_city": home_city,
        "user_location": user_location,
        "prev_search_context": None,
        "final_response": "",
        "chat_prompt": None,
        "show_cold_start_guide": False,
        # Multi-Agent 协作字段初始值
        "agent_messages": [],
        "completed_steps": [],
        "next_action": None,
        "supervisor_reason": None,
        "iteration_count": 0,
        "quality_check_passed": False,
        "search_strategy_hint": None,
        "tried_keywords": [],
        "pending_request_for_search_agent": None,
        "pending_request_for_recommend_agent": None,
        "pending_request_for_location_agent": None,
        "delegation_count": 0,
    }
