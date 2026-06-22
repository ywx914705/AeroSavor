"""RouteAgent 状态定义。"""
from __future__ import annotations
from typing import Optional
from typing_extensions import TypedDict


class RouteState(TypedDict):
    # ── 输入（从主图映射） ──
    resolved_location: str
    recommendations: list[dict]
    target_poi_id: Optional[str]
    target_poi_name: Optional[str]
    user_city: Optional[str]
    user_location: Optional[str]
    prev_search_context: Optional[dict]
    session_id: str                     # SSE 推送用

    # ── 输出（写回主图） ──
    route_info: Optional[dict]

    # ── 内部字段 ──
    destination: Optional[str]
    destination_name: Optional[str]
