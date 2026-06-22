"""RouteAgent 节点：并行计算步行、驾车路线。"""
from __future__ import annotations
import asyncio
from ....core.config import settings
from ....core.logging import get_logger
from ....core.event_bus import push_event, evt_agent_start, evt_agent_done
from ....tools.route_tools import plan_routes

logger = get_logger(__name__)


async def resolve_destination_node(state: dict) -> dict:
    """确定导航目标。

    优先从 recommendations 列表中取目标；
    如果 recommendations 为空（route 意图跳过了 search/recommend），
    但 target_poi_name 有值，则用高德搜索目标餐厅获取坐标。
    """
    session_id = state.get("session_id", "")
    await push_event(session_id, evt_agent_start("route_agent", "确定导航目标..."))

    target_id = state.get("target_poi_id")
    target_name = state.get("target_poi_name")
    recs = state.get("recommendations") or []
    # route 意图跳过了 search/recommend，从 prev_search_context 获取上轮推荐
    prev_recs = (state.get("prev_search_context") or {}).get("recommendations") or []
    if not recs and prev_recs:
        recs = prev_recs
    logger.info("route resolve: target_id=%s target_name=%s recs=%d prev_recs=%d resolved_loc=%s user_loc=%s",
                target_id, target_name, len(recs), len(prev_recs), state.get("resolved_location"), state.get("user_location"))

    target = None

    # 1) 从推荐列表中按 ID 或名称匹配
    if target_id:
        target = next((r for r in recs if r.get("id") == target_id), None)
    if not target and target_name and recs:
        target = next((r for r in recs if target_name in r.get("name", "")), None)
    if not target and recs:
        target = recs[0]

    # 2) 推荐列表为空但有 target_poi_name：用高德搜索目标餐厅
    if not target and target_name:
        try:
            from ....tools.amap_client import get_amap_client
            location = state.get("user_location") or state.get("resolved_location")
            # 从 prev_search_context 恢复用户位置（route 意图跳过了 location_agent）
            if not location:
                prev = state.get("prev_search_context")
                if prev:
                    location = prev.get("location")
            client = get_amap_client()
            results = await client.search_nearby(
                location=location or "",
                keywords=target_name,
                radius=5000,
            )
            if results:
                target = results[0]
                logger.info("route: found target '%s' via amap search", target_name)
        except Exception as e:
            logger.warning("route: amap search for target failed: %s", e)

    if not target or not target.get("location"):
        await push_event(session_id, evt_agent_done("route_agent", "无法确定目标"))
        return {"destination": None, "destination_name": None}

    await push_event(session_id, evt_agent_done("route_agent", f"目标: {target.get('name', '')}"))
    return {"destination": target["location"], "destination_name": target.get("name", "")}


async def parallel_route_node(state: dict) -> dict:
    """并行计算步行 + 驾车路线。"""
    session_id = state.get("session_id", "")
    await push_event(session_id, evt_agent_start("route_agent", "规划路线..."))

    # route 意图可能跳过了 location_agent，从 prev_search_context 恢复用户位置
    origin = state.get("user_location") or state.get("resolved_location")
    if not origin:
        prev = state.get("prev_search_context")
        if prev:
            origin = prev.get("location")
    if not origin:
        origin = settings.DEFAULT_LOCATION
    dest = state.get("destination")
    city = state.get("user_city") or ""

    if not dest:
        await push_event(session_id, evt_agent_done("route_agent", "无导航目标"))
        return {"route_info": None}

    route = await plan_routes(origin, dest, city=city)
    # 确保 destination_name 传递到 route_info
    if route:
        route["destination_name"] = state.get("destination_name") or state.get("target_poi_name")
        modes = []
        if route.get("walking"): modes.append("步行")
        if route.get("driving"): modes.append("驾车")
        if route.get("transit"): modes.append("公交")
        mode_str = "、".join(modes) if modes else "路线"
        await push_event(session_id, evt_agent_done("route_agent", f"路线规划完成（{mode_str}）"))
    else:
        await push_event(session_id, evt_agent_done("route_agent", "无法规划路线"))
    return {"route_info": route}
