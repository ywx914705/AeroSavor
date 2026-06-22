"""ChatAgent 子图组装。"""
from __future__ import annotations
from langgraph.graph import StateGraph, END
from .state import ChatState
from .nodes import prepare_chat_node, generate_chat_node


def build_chat_agent():
    g = StateGraph(ChatState)
    g.add_node("prepare_chat", prepare_chat_node)
    g.add_node("generate_chat", generate_chat_node)

    g.set_entry_point("prepare_chat")
    g.add_edge("prepare_chat", "generate_chat")
    g.add_edge("generate_chat", END)

    return g
