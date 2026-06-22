"""RouteAgent 子图组装。"""
from __future__ import annotations
from langgraph.graph import StateGraph, END
from .state import RouteState
from .nodes import resolve_destination_node, parallel_route_node


def build_route_agent():
    g = StateGraph(RouteState)
    g.add_node("resolve_destination", resolve_destination_node)
    g.add_node("parallel_route", parallel_route_node)

    g.set_entry_point("resolve_destination")
    g.add_edge("resolve_destination", "parallel_route")
    g.add_edge("parallel_route", END)

    return g
