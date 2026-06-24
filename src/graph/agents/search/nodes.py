"""SearchAgent 节点：LLM 搜索规划 + 并发搜索 + 过滤 + 自动扩大半径重试 + 质量反馈。

升级：
- plan_search_node: LLM 规划搜索策略（条件触发）
- search_node: 使用策略提示优化关键词
- filter_node: 使用策略提示过滤不匹配类型
"""
from __future__ import annotations
import asyncio
import json
import re
from ....core.config import settings
from ....core.logging import get_logger
from ....core.event_bus import push_event, evt_agent_start, evt_agent_done, evt_collaboration
from ....tools.search_tools import search_restaurants
from ....graph.messages import make_result_message, make_feedback_message, make_request_message, make_response_message

logger = get_logger(__name__)

RADIUS_STEPS = [1000, 2000, 5000]

# ── LLM 搜索规划 ──

SEARCH_PLANNING_PROMPT = """你是搜索策略规划器。根据用户需求和上下文，规划最优搜索关键词组合。

用户需求：{user_query}
用户偏好：{user_preference}
当前关键词：{current_keywords}
搜索策略提示：{strategy_hint}
已尝试的关键词（避免重复）：{tried_keywords}
搜索结果数量：{previous_count}

规划搜索策略，以 JSON 返回：
{{
  "keywords": ["主关键词", "备选关键词1", "备选关键词2"],
  "strategy": "策略说明（10字以内）",
  "radius": 搜索半径（米）,
  "skip_search": true/false（如果当前关键词已经足够好，跳过搜索）
}}

策略原则：
- 用户说"日料"→ 先搜"日料"，备选"寿司"、"日本料理"
- 用户说"好吃的"→ 搜"美食"，备选"餐厅"
- 如果 strategy_hint 指定了 avoid_types，不要包含这些关键词
- 如果已尝试的关键词效果不好，换同义/近义关键词
- 如果 previous_count >= 5 且无 strategy_hint，可以 skip_search"""


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


async def plan_search_node(state: dict) -> dict:
    """LLM 规划搜索策略。仅在需要时调用（有 strategy_hint 或上次结果差）。

    委派响应：如果存在 pending_request_for_search_agent（来自 RecommendAgent 的委派），
    直接使用请求中的 prefer_types 作为搜索关键词，并回复 response 消息。
    """
    session_id = state.get("session_id", "")
    strategy_hint = state.get("search_strategy_hint")
    previous_count = len(state.get("filtered_pois") or [])

    # ── 委派响应：RecommendAgent 直接请求搜索 ──
    pending_request = state.get("pending_request_for_search_agent")
    if pending_request:
        req_data = pending_request.get("data", {})
        prefer_types = req_data.get("prefer_types", [])
        avoid_types = req_data.get("avoid_types", [])
        price_hint = req_data.get("price_hint")
        price_max = req_data.get("price_max")

        updates = {}
        if prefer_types:
            updates["search_keywords"] = prefer_types
            logger.info("[委派响应] RecommendAgent 请求搜索: prefer=%s avoid=%s",
                        prefer_types, avoid_types)
        if avoid_types:
            if not strategy_hint:
                strategy_hint = {}
            strategy_hint["avoid_types"] = avoid_types
            updates["search_strategy_hint"] = strategy_hint

        # 价格委派：调整价格上限
        if price_hint:
            if not strategy_hint:
                strategy_hint = {}
            strategy_hint["price_hint"] = price_hint
            if price_max:
                strategy_hint["price_max"] = price_max
                updates["price_max"] = price_max
            updates["search_strategy_hint"] = strategy_hint
            logger.info("[委派响应] 价格调整: hint=%s max=%s", price_hint, price_max)

        await push_event(session_id, evt_agent_start("search_agent", "响应推荐Agent的搜索请求..."))
        await push_event(session_id, evt_agent_done("search_agent",
            f"使用推荐Agent建议的关键词: {', '.join(prefer_types) if prefer_types else '默认'}"))

        # 回复 response 消息
        if updates:
            updates["agent_messages"] = [make_response_message(
                from_agent="search_agent",
                to_agent="recommend_agent",
                reply_to=req_data.get("request_type", "search"),
                status="accepted",
                reason=f"接受搜索请求，使用关键词: {', '.join(prefer_types) if prefer_types else '默认'}",
                keywords=prefer_types,
            )]
        # 清除已处理的 pending_request，防止重复路由
        updates["pending_request_for_search_agent"] = None
        return updates

    # ── 正常 LLM 规划路径 ──

    # 跳过规划：无策略提示且上次结果好
    if not strategy_hint and previous_count >= 5:
        return {}

    # 跳过规划：第一次搜索（无先验信息）
    if not strategy_hint and previous_count == 0 and not state.get("tried_keywords"):
        return {}

    llm = _get_llm()
    if llm is None:
        return {}

    tried_keywords = list(state.get("tried_keywords") or [])
    current_kw = list(state.get("search_keywords") or [])

    await push_event(session_id, evt_agent_start("search_agent", "规划搜索策略..."))

    try:
        content = await asyncio.wait_for(
            llm.ainvoke(
                SEARCH_PLANNING_PROMPT.format(
                    user_query=state.get("user_query", ""),
                    user_preference=str(state.get("user_preference") or "无"),
                    current_keywords=", ".join(current_kw),
                    strategy_hint=str(strategy_hint or "无"),
                    tried_keywords=", ".join(tried_keywords),
                    previous_count=previous_count,
                ),
                max_tokens=200,
                temperature=0,
            ),
            timeout=10.0,
        )
        plan = _parse_json_safely(content)
    except Exception as e:
        logger.warning("plan_search_node LLM failed: %s", e)
        await push_event(session_id, evt_agent_done("search_agent", "策略规划失败，使用默认关键词"))
        return {}

    new_keywords = plan.get("keywords", [])
    skip = plan.get("skip_search", False)
    new_radius = plan.get("radius")

    if skip:
        await push_event(session_id, evt_agent_done("search_agent", "当前关键词足够，跳过规划"))
        return {}

    updates = {}
    if new_keywords:
        updates["search_keywords"] = new_keywords
        logger.info("[搜索规划] 策略: %s → 关键词: %s", plan.get("strategy", ""), new_keywords)
    if new_radius and isinstance(new_radius, int):
        updates["current_radius"] = new_radius

    await push_event(session_id, evt_agent_done("search_agent", f"搜索策略: {plan.get('strategy', '默认')}"))
    return updates


# ── 搜索与过滤 ──


async def search_node(state: dict) -> dict:
    """并发多关键词搜索。使用 search_strategy_hint 优化搜索方向和价格。"""
    session_id = state.get("session_id", "")
    target = state.get("resolved_location") or settings.DEFAULT_LOCATION
    radius = state.get("current_radius") or RADIUS_STEPS[0]
    retry_count = state.get("retry_count", 0)
    keywords = list(state.get("search_keywords") or [state.get("user_query", "美食")])
    max_price = state.get("price_max") or 999
    min_rating = 0.0 if retry_count < 2 else 3.0

    # 使用搜索策略提示优化关键词、价格、半径
    strategy = state.get("search_strategy_hint")
    if strategy:
        prefer_types = strategy.get("prefer_types", [])
        # 将 prefer_types 加入关键词（避免重复）
        for pt in prefer_types:
            if pt and pt not in keywords:
                keywords.append(pt)

        # 价格策略：调整 max_price
        if strategy.get("price_hint") == "lower" and strategy.get("price_max"):
            max_price = strategy["price_max"]
            logger.info("[搜索] 价格策略: 限制人均≤%d元", max_price)

        # 距离策略：缩小搜索半径
        if strategy.get("radius_reduction"):
            radius = min(radius, RADIUS_STEPS[0])  # 缩到最小半径1000m
            logger.info("[搜索] 距离策略: 缩小半径到%dm", radius)

        logger.info("[搜索] 策略提示: prefer=%s avoid=%s reason=%s",
                    prefer_types, strategy.get("avoid_types", []), strategy.get("reason", ""))

    # 推送开始事件
    await push_event(session_id, evt_agent_start(
        "search_agent",
        f"搜索「{'、'.join(keywords)}」...",
    ))

    logger.info("[搜索] 第%d轮 半径%dm 关键词:%s min_rating=%.1f",
                retry_count + 1, radius, keywords, min_rating)

    pois = await search_restaurants(
        location=target, keywords=keywords,
        radius=radius, max_price=max_price, min_rating=min_rating,
    )

    # 推送完成事件
    await push_event(session_id, evt_agent_done(
        "search_agent",
        f"找到 {len(pois)} 家候选餐厅",
    ))

    return {"raw_pois": pois, "current_radius": radius}


def filter_node(state: dict) -> dict:
    """过滤：有效性检查 + 基本筛选 + 向 Supervisor 发送质量反馈。

    根据过滤结果数量生成不同级别的反馈消息：
    - 0 家 → empty_result，建议 relocation
    - < 3 家 → low_result，建议 expand_keywords
    - ≥ 3 家 → success，建议 accept

    使用 search_strategy_hint 中的 avoid_types 过滤不匹配类型。
    """
    pois = state.get("raw_pois") or []
    price_max = state.get("price_max") or 9999

    # 原有过滤逻辑
    filtered = [p for p in pois if p.get("name") and p.get("location")]

    # 使用策略提示过滤不匹配类型
    strategy = state.get("search_strategy_hint")
    if strategy and strategy.get("avoid_types"):
        avoid = strategy["avoid_types"]
        before_count = len(filtered)
        filtered = [p for p in filtered if not any(
            a in p.get("type", "") for a in avoid
        )]
        if len(filtered) < before_count:
            logger.info("[过滤] 策略过滤: %d → %d (避免类型: %s)", before_count, len(filtered), avoid)

    count = len(filtered)
    avg_rating = (
        sum(float(p.get("rating", 0) or 0) for p in filtered) / count
        if count > 0 else 0
    )

    # 根据结果质量生成反馈消息
    if count == 0:
        msg = make_feedback_message(
            from_agent="search_agent",
            status="empty_result",
            suggestion="relocation",
            reason=f"关键词「{'、'.join(state.get('search_keywords', []))}」"
                   f"在当前位置 {state.get('current_radius', 1000)}m 内无结果",
            tried_radius=state.get("current_radius", 1000),
            keywords=state.get("search_keywords", []),
        )
    elif count < 3:
        # 低结果反馈给 Supervisor——这是汇报质量，不是委派
        # Supervisor 会根据反馈决策：有少量结果 → recommend_agent，无结果 → search_agent/location_agent
        msg = make_feedback_message(
            from_agent="search_agent",
            status="low_result",
            suggestion="expand_keywords",
            reason=f"仅找到 {count} 家，推荐质量可能受限",
            count=count,
            avg_rating=round(avg_rating, 1),
        )
    else:
        msg = make_result_message("search_agent", count, round(avg_rating, 1))

    return {
        "filtered_pois": filtered,
        "agent_messages": [msg],  # 追加到消息总线
    }


def should_retry(state: dict) -> str:
    """结果不足且未达重试上限 → retry。"""
    retry_count = state.get("retry_count", 0)
    poi_count = len(state.get("filtered_pois") or [])
    if poi_count < 3 and retry_count < 2:
        return "retry"
    return "done"


def expand_radius_node(state: dict) -> dict:
    """扩大搜索半径。"""
    retry_count = state.get("retry_count", 0)
    next_radius = RADIUS_STEPS[min(retry_count + 1, len(RADIUS_STEPS) - 1)]
    return {"current_radius": next_radius, "retry_count": retry_count + 1}
