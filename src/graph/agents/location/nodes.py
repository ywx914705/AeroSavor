"""LocationAgent 节点：LLM 位置推理 + 将位置描述转为坐标。

升级：
- reason_location_node: LLM 推理模糊位置描述（条件触发）
- geocode_node: 将地址描述转为坐标
- ip_locate_node: IP 定位兜底
"""
from __future__ import annotations
import json
import re
from ....core.config import settings
from ....core.logging import get_logger
from ....core.event_bus import push_event, evt_agent_start, evt_agent_done
from ....tools.amap_client import (
    get_amap_client, get_city_code, resolve_city_center, resolve_city_from_hint,
)

logger = get_logger(__name__)

# ── LLM 位置推理 ──

LOCATION_REASONING_PROMPT = """你是位置推理器。用户提到了一个模糊的位置描述，请根据上下文推断最可能的具体位置。

用户位置描述：{location_hint}
当前城市：{current_city}
对话历史：{conversation_history}

常见模糊描述的推理规则：
- "市中心" → 根据城市推断核心商圈（成都→春熙路，北京→王府井，上海→南京路，广州→天河城）
- "商圈" → 该城市最知名的商圈
- "附近" → 无法推理，返回空
- "新区"/"开发区" → 根据城市推断（成都→天府新区，大连→金州新区）
- 短地名（<3字）→ 可能是简称，尝试补全（"昆山"→"昆山市"）

以 JSON 返回：
{{
  "refined_hint": "推理后的精确位置描述",
  "city": "推断的城市名（不含'市'）",
  "confidence": "high/medium/low",
  "reasoning": "推理过程（15字以内）"
}}

如果无法推理（如"附近"），返回：
{{ "refined_hint": "", "city": "", "confidence": "low", "reasoning": "无法推理" }}"""


def _parse_json_safely(text: str) -> dict:
    """安全解析 JSON（兼容 markdown 代码块包裹）。"""
    msg = text.strip()
    for attempt in [msg.strip(), None]:
        try:
            return json.loads(msg)
        except json.JSONDecodeError:
            pass
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", msg)
        if m:
            msg = m.group(1).strip()
            continue
        m = re.search(r"\{[\s\S]*\}", msg)
        if m:
            msg = m.group(0)
            break
    try:
        return json.loads(msg)
    except json.JSONDecodeError:
        return {}


def _get_llm():
    try:
        from ....core.llm import get_claude
        return get_claude()
    except Exception:
        return None


async def reason_location_node(state: dict) -> dict:
    """LLM 推理模糊位置描述。仅在位置描述模糊时触发。

    触发条件：
    1. location_hint 短于10字（模糊）且无 GPS 坐标
    2. 收到 RecommendAgent 的 distance_mismatch 委派请求（need_closer=True）
    """
    session_id = state.get("session_id", "")
    user_location = state.get("user_location")
    location_hint = state.get("location_hint") or ""

    # ── 委派响应：RecommendAgent 请求换更近位置 ──
    pending_request = state.get("pending_request_for_location_agent")
    updates = {}
    if pending_request:
        req_data = pending_request.get("data", {})
        if req_data.get("need_closer"):
            await push_event(session_id, evt_agent_start("location_agent", "响应推荐Agent的换位置请求..."))
            # 距离不匹配 → 推理用户附近更精确的位置
            # 如果有 GPS 但之前的搜索结果太远，缩小到 GPS 附近
            if user_location:
                await push_event(session_id, evt_agent_done("location_agent", "使用GPS位置，缩小搜索范围"))
                # 清除已处理的 pending_request，防止重复路由
                updates["pending_request_for_location_agent"] = None
                return updates

            # 无 GPS → 用 LLM 推理更近的商圈
            current_city = state.get("user_city") or settings.AMAP_DEFAULT_CITY
            user_query = req_data.get("user_query", state.get("user_query", ""))
            await push_event(session_id, evt_agent_done("location_agent", "推理更近的位置..."))
            # fall through 到 LLM 推理（用当前位置描述但更精确）
        # 清除已处理的 pending_request，防止重复路由
        updates["pending_request_for_location_agent"] = None

    # 有 GPS 坐标 → 不需要推理
    if user_location:
        return updates

    # 无位置描述 → 不需要推理
    if not location_hint:
        return updates

    # 位置描述足够精确（>=10字）→ 不需要推理
    if len(location_hint) >= 10:
        return updates

    # 已经是精确地址（含路名/门牌号）→ 不需要推理
    precise_patterns = ["路", "街", "号", "栋", "楼", "层", "室", "区", "号"]
    if any(p in location_hint for p in precise_patterns) and len(location_hint) >= 4:
        return updates

    llm = _get_llm()
    if llm is None:
        return updates

    current_city = state.get("user_city") or settings.AMAP_DEFAULT_CITY
    conversation_history = str(state.get("conversation_history") or "无")

    await push_event(session_id, evt_agent_start("location_agent", f"推理位置「{location_hint}」..."))

    try:
        content = await llm.ainvoke(
            LOCATION_REASONING_PROMPT.format(
                location_hint=location_hint,
                current_city=current_city,
                conversation_history=conversation_history,
            ),
            max_tokens=200,
            temperature=0,
        )
        result = _parse_json_safely(content)
    except Exception as e:
        logger.warning("reason_location_node LLM failed: %s", e)
        await push_event(session_id, evt_agent_done("location_agent", "位置推理失败，使用原始描述"))
        return updates

    refined = result.get("refined_hint", "")
    confidence = result.get("confidence", "low")
    reasoning = result.get("reasoning", "")
    inferred_city = result.get("city", "")

    if not refined or confidence == "low":
        await push_event(session_id, evt_agent_done("location_agent", "无法推理，使用原始描述"))
        return updates

    updates["location_hint"] = refined
    if inferred_city:
        updates["user_city"] = inferred_city

    logger.info("[位置推理] '%s' → '%s' (city=%s, confidence=%s, reason=%s)",
                location_hint, refined, inferred_city, confidence, reasoning)
    await push_event(session_id, evt_agent_done("location_agent", f"推理: {reasoning}"))

    return updates


# ── 地理编码 ──

async def geocode_node(state: dict) -> dict:
    """将地址描述转为坐标（GPS > geocode(hint) > regeocode 兜底）。"""
    user_loc = state.get("user_location")
    if user_loc:
        uc = state.get("user_city")
        # GPS 坐标存在但城市名未知时，用 regeocode 反查
        if not uc:
            try:
                client = get_amap_client()
                regeo = await client.regeocode(user_loc)
                comp = regeo.get("addressComponent") or {}
                regeo_city = comp.get("city") or comp.get("province")
                if regeo_city:
                    regeo_city = regeo_city.rstrip("市")
                    uc = regeo_city
                    logger.info("geocode_node: regeocode from GPS resolved city=%s", uc)
            except Exception as e:
                logger.warning("geocode_node: regeocode from GPS failed: %s", e)
        if not uc:
            uc = settings.AMAP_DEFAULT_CITY
        return {"resolved_location": user_loc, "user_city": uc,
                "user_city_code": get_city_code(uc) or get_city_code(settings.AMAP_DEFAULT_CITY),
                "geocode_success": True}

    hint = state.get("location_hint")
    uc = state.get("user_city") or settings.AMAP_DEFAULT_CITY

    if not hint:
        prev_ctx = state.get("prev_search_context") or {}
        prev_hint = prev_ctx.get("location_hint")
        if prev_hint:
            hint = prev_hint
            logger.info("geocode_node: reuse prev location_hint=%s", hint)

    if not hint:
        return {"geocode_success": False}

    client = get_amap_client()
    target = None
    try:
        target = await client.geocode(hint, uc)
    except Exception as e:
        logger.warning("geocode failed for '%s': %s", e.__class__.__name__, e)

    if target:
        # geocode 成功 → 用 resolve_city_from_hint 获取城市名
        # （对"昆山"等不在 CITY_CODES 中的地名，会走 geocode+regeocode 路径）
        city_from_hint = await resolve_city_from_hint(hint, uc)
        if city_from_hint:
            uc = city_from_hint
        else:
            # 最后尝试：对 geocode 得到的坐标做 regeocode
            try:
                regeo = await client.regeocode(target)
                comp = regeo.get("addressComponent") or {}
                regeo_city = comp.get("city") or comp.get("province")
                if regeo_city:
                    regeo_city = regeo_city.rstrip("市")
                    uc = regeo_city
                    logger.info("geocode_node: regeocode from coords resolved city=%s", uc)
            except Exception as e:
                logger.warning("geocode_node: regeocode from coords failed: %s", e)
    else:
        # geocode 完全失败 → 尝试 resolve_city_from_hint 获取城市名，再用 resolve_city_center 获取坐标
        logger.warning("geocode empty for '%s', fallback to resolve", hint)
        city_from_hint = await resolve_city_from_hint(hint, uc)
        if city_from_hint:
            uc = city_from_hint
            target = await resolve_city_center(uc)
        else:
            target = await resolve_city_center(uc)

    city_code = get_city_code(uc) or get_city_code(settings.AMAP_DEFAULT_CITY)
    return {"resolved_location": target, "user_city": uc,
            "user_city_code": city_code, "geocode_success": bool(target)}


async def ip_locate_node(state: dict) -> dict:
    """IP定位 / home_city 兜底。"""
    home_city = state.get("home_city")
    if home_city:
        logger.info("ip_locate_node: fallback to home_city=%s", home_city)
        target = await resolve_city_center(home_city)
        return {"resolved_location": target,
                "user_city": home_city,
                "user_city_code": get_city_code(home_city) or get_city_code(settings.AMAP_DEFAULT_CITY)}

    client = get_amap_client()
    uc = state.get("user_city") or settings.AMAP_DEFAULT_CITY
    try:
        ip_data = await client.ip_locate()
        ip_city = ip_data.get("city")
        if ip_city:
            uc = ip_city
    except Exception as e:
        logger.warning("ip_locate failed: %s", e)

    target = await resolve_city_center(uc)
    return {"resolved_location": target,
            "user_city": uc,
            "user_city_code": get_city_code(uc) or get_city_code(settings.AMAP_DEFAULT_CITY)}
