"""SearchAgent 子图组装。

流程：plan_search（条件触发）→ search → filter → (retry?) expand_radius → search
plan_search_node 使用 LLM 规划搜索策略，仅在需要时调用。
"""
from __future__ import annotations
from langgraph.graph import StateGraph, END
from .state import SearchState
from .nodes import plan_search_node, search_node, filter_node, should_retry, expand_radius_node


def build_search_agent():
    g = StateGraph(SearchState)
    g.add_node("plan_search", plan_search_node)
    g.add_node("search", search_node)
    g.add_node("filter", filter_node)
    g.add_node("expand_radius", expand_radius_node)

    g.set_entry_point("plan_search")
    g.add_edge("plan_search", "search")
    g.add_edge("search", "filter")

    g.add_conditional_edges(
        "filter", should_retry,
        {"retry": "expand_radius", "done": END},
    )
    g.add_edge("expand_radius", "search")

    return g
