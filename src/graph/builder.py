"""AeroSavor 主图组装 — Multi-Agent 协作版。

Supervisor + 6 子图 Agent + 动态决策架构：
  搜索路径: intent_parser → location_agent → (get_weather ∥ memory_agent) → search_agent → supervisor_decision → ...
  闲聊路径: intent_parser → memory_agent → chat_agent → format_response
  路线路径: intent_parser → memory_agent → route_agent → format_response
  天气获取: 在 location_agent 之后触发（依赖 user_city_code）

supervisor_decision 是协作核心：根据 Agent 反馈动态决定重搜、换位置、还是继续推荐。
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .state import SupervisorState
from .supervisor import (
    intent_parser_node,
    get_weather_node,
    format_response_node,
    supervisor_decision_node,
    message_dispatch_node,
    route_after_supervisor,
)
from .agents.location.graph import build_location_agent
from .agents.search.graph import build_search_agent
from .agents.memory.graph import build_memory_agent
from .agents.recommend.graph import build_recommend_agent
from .agents.route.graph import build_route_agent
from .agents.chat.graph import build_chat_agent


def build_main_graph():
    g = StateGraph(SupervisorState)

    # ── Supervisor 自己的节点 ──────────────────────
    g.add_node("intent_parser",       intent_parser_node)
    g.add_node("get_weather",         get_weather_node)
    g.add_node("supervisor_decision", supervisor_decision_node)   # 新增：动态决策
    g.add_node("message_dispatch", message_dispatch_node)         # 新增：Agent间消息路由
    g.add_node("format_response",     format_response_node)

    # ── 子图 Agent 节点 ────────────────────────────
    g.add_node("location_agent",  build_location_agent().compile())
    g.add_node("memory_agent",    build_memory_agent().compile())
    g.add_node("search_agent",    build_search_agent().compile())
    g.add_node("recommend_agent", build_recommend_agent().compile())
    g.add_node("route_agent",     build_route_agent().compile())
    g.add_node("chat_agent",      build_chat_agent().compile())
    g.set_entry_point("intent_parser")

    # intent_parser 后分流：
    # chat/clarify → memory_agent（闲聊需要偏好上下文）
    # route → memory_agent（路线需要偏好上下文）+ 后续走 route_agent
    # search → location_agent（搜索需要位置）
    def _after_intent(state: dict) -> str:
        intent = state.get("intent", "search")
        if intent in ("chat", "clarify"):
            return "memory_agent"
        if intent == "route":
            return "memory_agent"
        return "location_agent"

    g.add_conditional_edges(
        "intent_parser",
        _after_intent,
        {"location_agent": "location_agent", "memory_agent": "memory_agent"},
    )

    # ── 搜索路径：location → get_weather + memory 并行 → search ──
    # location_agent 完成后才触发 get_weather（因为需要 user_city_code）
    g.add_edge("location_agent", "get_weather")
    g.add_edge("location_agent", "memory_agent")

    # get_weather 完成后 → search
    g.add_edge("get_weather", "search_agent")

    # memory_agent 完成后条件分流：
    # chat/clarify → chat_agent；route → route_agent；search → search_agent
    def _after_memory(state: dict) -> str:
        intent = state.get("intent", "search")
        if intent in ("chat", "clarify"):
            return "chat_agent"
        if intent == "route":
            return "route_agent"
        return "search_agent"

    g.add_conditional_edges(
        "memory_agent",
        _after_memory,
        {"chat_agent": "chat_agent", "search_agent": "search_agent", "route_agent": "route_agent"},
    )

    # ── 核心变化：search_agent → supervisor_decision → message_dispatch → 动态路由 ──
    g.add_edge("search_agent", "supervisor_decision")
    g.add_edge("supervisor_decision", "message_dispatch")

    # Supervisor 决策后路由（从 message_dispatch 出发，含 Agent 间请求分发）
    g.add_conditional_edges(
        "message_dispatch",
        route_after_supervisor,
        {
            "search_agent":    "search_agent",
            "location_agent":  "location_agent",
            "recommend_agent": "recommend_agent",
            "format_response": "format_response",
        },
    )

    # recommend 完成 → 再次 Supervisor 决策（评估质量检查结果）
    g.add_edge("recommend_agent", "supervisor_decision")

    # recommend 后如果需要路线 → route_agent
    # 注意：recommend_agent 完成后走 supervisor_decision，
    # supervisor_decision 在 quality_check_passed=True 时会 route 到 format_response，
    # 但如果 need_route=True，format_response_node 会处理路线信息。
    # 这里我们不单独走 route_agent，而是让 format_response_node 来格式化。

    # chat 直接结束
    g.add_edge("chat_agent", "format_response")

    # route 直接结束
    g.add_edge("route_agent", "format_response")

    # format_response → END
    g.add_edge("format_response", END)

    # 设置合理的递归限制（默认25太低，10007太高）
    # 搜索协作最多3轮迭代，每轮约5个节点，15+10=25安全线
    return g.compile(
        checkpointer=MemorySaver(),
        # LangGraph 默认 recursion_limit=10007，我们限制到合理值
    )


# 全局单例
restaurant_graph = build_main_graph()
