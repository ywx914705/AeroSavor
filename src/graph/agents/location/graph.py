"""LocationAgent 子图组装。

流程：reason_location（条件触发）→ geocode → (success?) END / ip_locate → END
reason_location_node 使用 LLM 推理模糊位置描述，仅在需要时调用。
"""
from __future__ import annotations
from langgraph.graph import StateGraph, END
from .state import LocationState
from .nodes import reason_location_node, geocode_node, ip_locate_node


def build_location_agent():
    g = StateGraph(LocationState)
    g.add_node("reason_location", reason_location_node)
    g.add_node("geocode", geocode_node)
    g.add_node("ip_locate", ip_locate_node)

    g.set_entry_point("reason_location")
    g.add_edge("reason_location", "geocode")

    g.add_conditional_edges(
        "geocode",
        lambda s: "end" if s.get("geocode_success") else "ip_locate",
        {"end": END, "ip_locate": "ip_locate"},
    )
    g.add_edge("ip_locate", END)

    return g  # 不 compile，在 builder.py 里统一 compile
