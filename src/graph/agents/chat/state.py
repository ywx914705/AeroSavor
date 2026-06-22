"""ChatAgent 状态定义。"""
from __future__ import annotations
from typing import Optional
from typing_extensions import TypedDict


class ChatState(TypedDict):
    # ── 输入（从主图映射） ──
    user_query: str
    chat_type: Optional[str]              # intent_parser 解析的 chat 子类型
    user_preference: Optional[dict]
    is_new_user: bool
    home_city: Optional[str]
    prev_search_context: Optional[dict]
    messages: list
    location_hint: Optional[str]       # 用户当前轮次声明的位置
    session_id: str                    # SSE 推送用

    # ── 输出（写回主图） ──
    final_response: str
    chat_prompt: Optional[str]       # 供 SSE 流式路径复用，避免重复构建 prompt
