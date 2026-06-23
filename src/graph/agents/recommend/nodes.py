"""RecommendAgent 节点：个性化重排序 + 质量检查 + LLM 生成推荐理由。

升级：新增 quality_check_node，在排序后评估搜索结果与用户需求的匹配度，
质量差时向 Supervisor 发送 feedback 消息，触发重搜。
"""
from __future__ import annotations
import json
from ....core.logging import get_logger
from ....core.event_bus import push_event, evt_agent_start, evt_agent_done
from ....services.personalization import cold_start_rank, rerank_pois
from ...prompts import AEROSAVOR_SYSTEM_PROMPT, RECOMMENDER_PROMPT, EMPTY_RESULT_RESPONSE
from ...messages import make_feedback_message, make_result_message, make_request_message

logger = get_logger(__name__)


def _parse_json_safely(text: str) -> dict:
    import re
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
    from ....core.llm import get_claude
    return get_claude()


def _classify_mismatch(reason: str) -> str:
    """从质量检查原因中分类 mismatch 类型，供 Supervisor 构建搜索策略。"""
    reason_lower = reason.lower()
    cuisine_words = ["菜系", "日料", "寿司", "川菜", "火锅", "烧烤", "快餐", "小吃",
                     "西餐", "韩料", "泰餐", "粤菜", "鲁菜", "湘菜", "东北菜",
                     "类型", "种类", "风味"]
    price_words = ["价格", "人均", "太贵", "太便宜", "价位", "消费", "预算"]
    distance_words = ["距离", "太远", "附近", "周边", "远"]

    for w in cuisine_words:
        if w in reason_lower:
            return "cuisine_mismatch"
    for w in price_words:
        if w in reason_lower:
            return "price_mismatch"
    for w in distance_words:
        if w in reason_lower:
            return "distance_mismatch"
    return "general"


def _extract_types_from_pois(pois: list[dict]) -> str:
    """从搜索结果中提取主要餐厅类型，用于 Supervisor 判断搜索偏差。"""
    types = []
    for p in pois:
        t = p.get("type", "")
        if t:
            # 取类型的第一级（如"餐饮服务;中餐厅" → "中餐厅"）
            parts = t.split(";")
            label = parts[1] if len(parts) > 1 else parts[0]
            if label and label not in types:
                types.append(label)
    return ", ".join(types[:5])


# 菜系关键词映射表
_CUISINE_MAP = {
    "日料": ["日料", "寿司", "日本料理"],
    "日式": ["日料", "寿司", "日本料理"],
    "寿司": ["寿司", "日料", "日本料理"],
    "川菜": ["川菜", "四川火锅", "麻辣"],
    "火锅": ["火锅", "川味火锅"],
    "烧烤": ["烧烤", "烤肉", "串烤"],
    "西餐": ["西餐", "牛排", "意面"],
    "韩料": ["韩料", "韩国料理", "烤肉"],
    "粤菜": ["粤菜", "广东菜", "港式"],
    "湘菜": ["湘菜", "湖南菜"],
    "东北菜": ["东北菜", "东北炖菜"],
    "饺子": ["饺子", "水饺", "东北饺子"],
    "泰国菜": ["泰国菜", "泰餐", "冬阴功"],
    "海鲜": ["海鲜", "海鲜自助", "海鲜烧烤"],
    "自助餐": ["自助餐", "自助烤肉", "海鲜自助"],
    "烤鱼": ["烤鱼", "酸菜鱼", "水煮鱼"],
}


def _extract_cuisine_keywords(user_query: str) -> list[str]:
    """从用户查询中提取菜系相关的搜索关键词。

    仅当用户明确提到菜系时才返回关键词，否则返回空列表。
    避免把"有没有便宜点的"这类追问当成菜系关键词。
    """
    for key, values in _CUISINE_MAP.items():
        if key in user_query:
            return values
    return []


async def rank_node(state: dict) -> dict:
    """个性化重排序：合并 declared_preferences + 调用排序服务。"""
    pois = state.get("filtered_pois") or []
    if not pois:
        return {"ranked_pois": [], "show_cold_start_guide": False}

    # 合并用户显式声明的偏好
    user_pref = state.get("user_preference")
    declared = state.get("declared_preferences")
    if declared:
        merged = dict(user_pref) if user_pref else {}
        if declared.get("disliked"):
            existing = list(merged.get("disliked_cuisines") or [])
            for d in declared["disliked"]:
                if d not in existing:
                    existing.append(d)
            merged["disliked_cuisines"] = existing
        if declared.get("preferred"):
            existing = list(merged.get("preferred_cuisines") or [])
            for p in declared["preferred"]:
                if p not in existing:
                    existing.append(p)
            merged["preferred_cuisines"] = existing
        if declared.get("price_max") and not merged.get("price_range"):
            merged["price_range"] = [0, declared["price_max"]]
        user_pref = merged

    context = {
        "price_max": state.get("price_max"),
        "features": state.get("feature_requests", []),
    }

    is_new = state.get("is_new_user", True)
    if is_new and not declared:
        ranked = cold_start_rank(pois, context)
    else:
        ranked = await rerank_pois(
            user_id=state.get("user_id", ""),
            pois=pois, context=context, user_preference=user_pref,
        )

    return {"ranked_pois": ranked[:10], "show_cold_start_guide": is_new}


# ── 质量检查 Prompt ──

QUALITY_CHECK_PROMPT = """评估搜索结果与用户需求的匹配程度。

用户需求：{user_query}
用户偏好：{user_preference}
搜索结果（前5家）：
{poi_list}

判断标准：
- good：至少 3 家餐厅与用户需求基本匹配（菜系、价格、场景）
- poor：结果与需求严重不符（如用户要日料，结果全是快餐）

以 JSON 返回：
{{
  "quality": "good 或 poor",
  "reason": "判断理由，15字以内",
  "suggestion": "accept 或 expand_keywords 或 relocation"
}}"""


async def quality_check_node(state: dict) -> dict:
    """评估搜索结果质量，不通过则向 Supervisor 发反馈。

    在 rank_node 之后、llm_recommend_node 之前执行。
    质量检查通过 → 继续 LLM 推荐
    质量检查不通过 → 结束子图，消息写入 agent_messages，Supervisor 会决策重搜

    核心原则：始终如实报告质量，由 Supervisor 决定是否重搜或输出。
    """
    session_id = state.get("session_id", "")
    await push_event(session_id, evt_agent_start("recommend_agent", "评估推荐质量..."))

    pois = state.get("ranked_pois") or []
    iteration_count = state.get("iteration_count", 0)

    # 结果为空，直接标记质量差
    # 注意：不清空 recommendations，保留已有推荐作为兜底
    if not pois:
        return {
            "quality_check_passed": False,
            "agent_messages": [make_feedback_message(
                from_agent="recommend_agent",
                status="empty_result",
                suggestion="expand_keywords",
                reason="推荐列表为空，无法生成推荐",
                mismatch_type="empty",
                got_types="",
                user_wants=state.get("user_query", ""),
            )],
        }

    poi_list = "\n".join([
        f"- {p.get('name', '?')}（{p.get('type', '未知')}，"
        f"人均¥{p.get('cost', '?')}，评分{p.get('rating', '?')}）"
        for p in pois[:5]
    ])

    pref_text = "新用户"
    user_pref = state.get("user_preference")
    if user_pref and isinstance(user_pref, dict):
        pref_text = user_pref.get("preference_text", "新用户") or "新用户"

    llm = _get_llm()

    # 无 LLM 时走规则降级：基本数量检查
    if llm is None:
        if len(pois) >= 3:
            return {
                "quality_check_passed": True,
                "agent_messages": [make_result_message(
                    "recommend_agent", len(pois),
                    sum(float(p.get("rating", 0) or 0) for p in pois) / len(pois),
                )],
            }
        else:
            # 不足3家，质量不通过
            # 注意：不清空 recommendations，保留已有推荐作为兜底
            return {
                "quality_check_passed": False,
                "agent_messages": [make_feedback_message(
                    from_agent="recommend_agent",
                    status="low_result",
                    suggestion="expand_keywords",
                    reason=f"仅 {len(pois)} 家候选，推荐质量可能受限",
                    mismatch_type="low_result",
                    got_types=_extract_types_from_pois(pois[:3]),
                    user_wants=state.get("user_query", ""),
                )],
            }

    try:
        content = await llm.ainvoke(
            QUALITY_CHECK_PROMPT.format(
                user_query=state.get("user_query", ""),
                user_preference=pref_text,
                poi_list=poi_list,
            ),
            max_tokens=200,
        )
        assessment = _parse_json_safely(content)
    except Exception as e:
        logger.warning("quality_check_node LLM failed: %s, defaulting to pass", e)
        assessment = {}

    quality = assessment.get("quality", "good")

    if quality == "poor":
        logger.info(
            "quality_check: POOR (reason=%s), sending feedback to supervisor",
            assessment.get("reason", ""),
        )
        await push_event(session_id, evt_agent_done("recommend_agent", "结果质量不佳，请求重新搜索"))
        # 关键：不清空 recommendations！保留已有推荐作为兜底
        # 结构化 mismatch 信息帮助 Supervisor 生成有针对性的搜索策略
        # 同时直接给 search_agent 发请求——Agent 间通信
        msgs = [make_feedback_message(
            from_agent="recommend_agent",
            status="quality_poor",
            suggestion=assessment.get("suggestion", "expand_keywords"),
            reason=assessment.get("reason", "结果与用户需求不匹配"),
            # 结构化 mismatch 数据，供 Supervisor 构建搜索策略
            mismatch_type=_classify_mismatch(assessment.get("reason", "")),
            got_types=_extract_types_from_pois(pois[:3]),
            user_wants=state.get("user_query", ""),
        )]

        # Agent 间直接通信：根据 mismatch 类型委派对应 Agent
        mismatch = _classify_mismatch(assessment.get("reason", ""))
        if mismatch == "cuisine_mismatch":
            got = _extract_types_from_pois(pois[:3])
            user_query = state.get("user_query", "")
            prefer = _extract_cuisine_keywords(user_query)
            # 如果用户追问中没有菜系词（如"有没有便宜点的"），回退到原搜索关键词
            if not prefer:
                prefer = list(state.get("search_keywords") or [])[:3]
            # 如果还是没有，用 got 的同义词（反向：搜到的类型就是可搜的类型）
            if not prefer:
                prefer = [t.strip() for t in got.split(",") if t.strip()][:3]
            # 只在确实有有意义关键词时才委派搜索
            meaningful = any(kw in _CUISINE_MAP or len(kw) <= 4 for kw in prefer)
            if meaningful and prefer:
                msgs.append(make_request_message(
                    from_agent="recommend_agent",
                    to_agent="search_agent",
                    request_type="search",
                    reason=f"菜系不匹配：搜到{got}，但用户要的是{user_query}",
                    priority="high",
                    avoid_types=[t.strip() for t in got.split(",") if t.strip()],
                    prefer_types=prefer,
                ))
        elif mismatch == "price_mismatch":
            # 价格不匹配 → 委派 search_agent 调整价格范围
            user_pref = state.get("user_preference") or {}
            price_max = user_pref.get("price_range", [0, 9999])[-1] if user_pref.get("price_range") else None
            avg_cost = sum(float(p.get("cost", 0) or 0) for p in pois[:3]) / min(3, len(pois[:3]))
            price_hint = "lower" if avg_cost > (price_max or 9999) else "higher"
            msgs.append(make_request_message(
                from_agent="recommend_agent",
                to_agent="search_agent",
                request_type="search",
                reason=f"价格不匹配：候选人均¥{avg_cost:.0f}，用户预算{'低于此' if price_hint == 'lower' else '高于此'}",
                priority="high",
                price_hint=price_hint,
                price_max=price_max,
            ))
        elif mismatch == "distance_mismatch":
            # 距离不匹配 → 委派 location_agent 换更近位置
            user_query = state.get("user_query", "")
            msgs.append(make_request_message(
                from_agent="recommend_agent",
                to_agent="location_agent",
                request_type="relocate",
                reason=f"距离不匹配：候选餐厅太远，需要更近的位置",
                priority="high",
                need_closer=True,
                user_query=user_query,
            ))

        return {
            "quality_check_passed": False,
            "agent_messages": msgs,
        }

    logger.info("quality_check: GOOD, proceeding to LLM recommend")
    await push_event(session_id, evt_agent_done("recommend_agent", "质量通过，生成推荐..."))
    return {
        "quality_check_passed": True,
        "agent_messages": [make_result_message(
            "recommend_agent", len(pois),
            sum(float(p.get("rating", 0) or 0) for p in pois) / len(pois),
        )],
    }


async def llm_recommend_node(state: dict) -> dict:
    """调用 LLM 生成个性化推荐理由。"""
    pois = state.get("ranked_pois") or []
    top5 = pois[:5]

    if not top5:
        radius = 1000
        return {
            "recommendations": [],
            "final_response": EMPTY_RESULT_RESPONSE.format(radius=radius, price_max="不限"),
        }

    weather = state.get("weather") or {}
    pref = state.get("user_preference")

    llm = _get_llm()
    if llm is None:
        recs = []
        for i, p in enumerate(top5[:3]):
            recs.append({
                **p, "rank": i + 1,
                "reason": f"评分 {p.get('rating','-')} 分，人均 ¥{p.get('cost','-')}，距离 {p.get('distance','-')}m",
                "highlight": p.get("type", ""), "suitable_for": "日常用餐",
            })
        return {"recommendations": recs, "final_response": ""}

    try:
        content = await llm.ainvoke(
            RECOMMENDER_PROMPT.format(
                user_query=state.get("user_query", ""),
                weather=f"{weather.get('weather','未知')} {weather.get('temperature','')}°C",
                user_preference=pref.get("preference_text", "新用户，无历史偏好") if pref else "新用户",
                pois=json.dumps(top5, ensure_ascii=False, indent=2),
            ),
            system_prompt=AEROSAVOR_SYSTEM_PROMPT,
        )
        parsed = _parse_json_safely(content)
    except Exception as e:
        logger.warning("llm_recommend_node failed: %s", e)
        parsed = {}

    recommendations = []
    for rec in parsed.get("recommendations", []):
        matching = next((p for p in top5 if p.get("id") == rec.get("poi_id")), None)
        if matching:
            recommendations.append({
                **matching,
                "rank": rec.get("rank", 1),
                "reason": rec.get("reason", ""),
                "highlight": rec.get("highlight", ""),
                "suitable_for": rec.get("suitable_for", ""),
            })

    summary = parsed.get("summary", "")
    return {"recommendations": recommendations, "final_response": summary}
