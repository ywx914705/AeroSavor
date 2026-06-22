"""MemoryAgent 子图组装。"""
from __future__ import annotations
from langgraph.graph import StateGraph, END
from .state import MemoryState
from .nodes import read_preference_node


def build_memory_agent():
    g = StateGraph(MemoryState)
    g.add_node("read_preference", read_preference_node)

    g.set_entry_point("read_preference")
    g.add_edge("read_preference", END)

    return g
