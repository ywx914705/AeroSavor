"""AeroSavor Supervisor 节点：intent_parser + get_weather + format_response + supervisor_decision。

本文件保留原 nodes.py 的全部节点函数作为过渡兼容。
新架构中，location/search/recommend/route/memory 由子图 Agent 替代，
Supervisor 负责 intent_parser、get_weather、format_response、supervisor_decision。
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime as dt
from typing import Any

from ..core.config import settings
from ..core.logging import get_logger
from ..core.event_bus import (
    push_event, evt_agent_start, evt_agent_done, evt_collaboration,
    evt_supervisor_decision, evt_quality_retry, evt_agent_message, evt_delegation,
)
from ..services.personalization import cold_start_rank, rerank_pois
from ..services.preference_service import get_user_preference
from ..tools.amap_client import (
    get_amap_client,
    get_city_code,
    resolve_city_center,
    resolve_city_from_hint,
)
from ..tools.search_tools import search_restaurants
from ..tools.route_tools import plan_routes
from .prompts import (
    AEROSAVOR_SYSTEM_PROMPT,
    COLD_START_FOLLOW_UP,
    EMPTY_RESULT_RESPONSE,
    INTENT_PARSER_PROMPT,
    RECOMMENDER_PROMPT,
)
from .state import SupervisorState

logger = get_logger(__name__)


# ──────────── 工具函数 ────────────


def _collab_reset_fields() -> dict:
    """返回 Multi-Agent 协作字段的重置值，防止跨轮次泄漏。"""
    return {
        "quality_check_passed": False,
        "iteration_count": 0,
        "delegation_count": 0,
        "next_action": None,
        "supervisor_reason": None,
        "search_strategy_hint": None,
        "pending_request_for_search_agent": None,
        "pending_request_for_recommend_agent": None,
        "pending_request_for_location_agent": None,
    }


def _parse_json_safely(text: str) -> dict:
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
        logger.warning("JSON parse failed for: %s", text[:80])
        return {}


def _format_messages(msgs: list, limit: int = 6) -> str:
    """取最近 N 条消息格式化。兼容 dict 与 LangChain BaseMessage 两种形态。"""
    lines: list[str] = []
    for m in (msgs or [])[-limit:]:
        if isinstance(m, dict):
            role = m.get("role", "unknown")
            content = m.get("content", "")
        else:
            # LangChain BaseMessage：HumanMessage / AIMessage / ...
            role = getattr(m, "type", None) or m.__class__.__name__
            content = getattr(m, "content", "") or ""
        lines.append(f"{role}: {str(content)[:120]}")
    return "\n".join(lines)


# ──────────── Agent 初始化 LLM 客户端（延迟）────────────


def _get_llm():
    """返回一个 ClaudeClient 或 None（无 Key 时降级）。"""
    from ..core.llm import get_claude

    return get_claude()


# ──────────── 节点1：意图解析 ────────────


async def intent_parser_node(state: dict) -> dict:
    session_id = state.get("session_id", "")
    await push_event(session_id, evt_agent_start("intent_parser", "理解你的需求..."))

    history = _format_messages(state.get("messages", []))
    query = state.get("user_query", "")
    prev = state.get("prev_search_context")
    logger.info("intent_parser: prev_ctx=%s recs=%d", bool(prev), len((prev or {}).get("recommendations", [])))

    # 快速规则：明确是闲聊追问的query，直接返回chat意图
    _CHAT_PATTERNS = ["我在哪", "我在哪个城市", "你记得", "我之前说", "我刚才说", "我告诉过你",
                      "你怎么知道", "你怎么了解", "你怎么会知道", "你怎么清楚", "你怎么明白"]
    for p in _CHAT_PATTERNS:
        if p in query:
            return {
                "intent": "chat", "chat_type": "location_confirm", "search_keywords": [],
                "location_hint": None, "price_max": None, "price_min": None,
                "feature_requests": [], "need_route": False,
                "is_followup": False, "target_poi_name": None, "target_poi_id": None,
                "declared_preferences": None,
                **_collab_reset_fields(),
            }

    # 快速规则：纯"附近"类词（无明确菜系但暗示搜索）→ search + 默认关键词
    _NEARBY_PATTERNS = ["附近", "周边", "周围", "就近", "附近有"]
    _has_nearby = any(p in query for p in _NEARBY_PATTERNS)
    _has_search_hint = any(w in query for w in ["吃", "喝", "推荐", "搜", "有没有", "想去", "想吃", "来点", "什么", "哪", "好"])
    if _has_nearby and not _has_search_hint and len(query) <= 6:
        # 短query只包含"附近"→默认搜美食
        logger.info("intent_parser: nearby-only rule, defaulting to '美食'")
        return {
            "intent": "search", "search_keywords": ["美食"],
            "location_hint": None, "price_max": None, "price_min": None,
            "feature_requests": [], "need_route": False,
            "is_followup": False, "target_poi_name": None, "target_poi_id": None,
            "declared_preferences": None,
            **_collab_reset_fields(),
        }

    # 快速规则：否定句式（"不想吃火锅"、"不要烧烤"、"别推荐日料"等）
    # 分两种情况：
    # 1. 只否定没肯定（"不想吃火锅"）→ clarify，问用户想吃什么
    # 2. 有否定也有肯定（"不想吃火锅，想吃烧烤"）→ search，用肯定的关键词
    _NEGATIVE_PATTERN = re.search(r"不[想爱吃要]|不要|别[给推荐]|不想|不爱", query)
    if _NEGATIVE_PATTERN:
        # 提取否定的菜系
        negated_cuisines = []
        for kw in _FOOD_KEYWORDS:
            if kw in query:
                negated_cuisines.append(kw)

        # 提取肯定的菜系（去掉否定词后的部分）
        _AFFIRM_WORDS = ["想", "要", "爱", "吃", "来点", "就吃", "换"]
        has_affirm = any(w in query for w in _AFFIRM_WORDS)
        # 去掉否定部分后看是否还有菜系词
        clean_query = re.sub(r"不[想爱吃要].{0,4}", "", query)
        affirm_cuisines = [kw for kw in _FOOD_KEYWORDS if kw in clean_query]

        if negated_cuisines:
            if affirm_cuisines:
                # 情况2：有否定也有肯定 → search用肯定的关键词
                logger.info("intent_parser: negative+affirm rule, disliked=%s prefer=%s", negated_cuisines, affirm_cuisines)
                return {
                    "intent": "search", "search_keywords": affirm_cuisines,
                    "location_hint": None, "price_max": None, "price_min": None,
                    "feature_requests": [], "need_route": False,
                    "is_followup": False, "target_poi_name": None, "target_poi_id": None,
                    "declared_preferences": {"disliked": negated_cuisines, "preferred": affirm_cuisines},
                    "search_strategy_hint": {"avoid_types": negated_cuisines, "prefer_types": affirm_cuisines, "reason": "用户否定+肯定"},
                    **_collab_reset_fields(),
                }
            else:
                # 情况1：只有否定没有肯定 → clarify，问用户想吃什么
                logger.info("intent_parser: negative-only rule, disliked=%s → clarify", negated_cuisines)
                disliked_str = "、".join(negated_cuisines)
                return {
                    "intent": "clarify", "chat_type": "negative_only",
                    "search_keywords": [],
                    "location_hint": None, "price_max": None, "price_min": None,
                    "feature_requests": [], "need_route": False,
                    "is_followup": False, "target_poi_name": None, "target_poi_id": None,
                    "declared_preferences": {"disliked": negated_cuisines},
                    **_collab_reset_fields(),
                }

    # 快速规则：用户声明位置的句式（"我在XX"、"我住XX"、"我在成都"）
    # 增强判断：如果同时包含闲聊成分（"你记住了吗"等），走 chat 意图但透传位置
    _LOCATION_DECLARE = re.search(r"我[在住于](.+)", query)
    if _LOCATION_DECLARE:
        place = _LOCATION_DECLARE.group(1).strip()

        # 检测"我在XX"后的文字是否包含闲聊/确认成分
        _CHAT_AFTER_LOCATION = ["你记住", "你记得", "了吗", "记住了吗", "好不好",
                                "行不行", "了没", "知道吗", "别忘了"]
        has_chat_after = any(p in place for p in _CHAT_AFTER_LOCATION)

        # 从 place 中提取纯位置部分（去掉闲聊后缀）
        clean_place = re.split(r'[，。？吗呢吧啊呀！!]', place)[0].strip()
        if len(clean_place) > 6:
            # "昆山你记住了"这种粘连，取前2-3字作为地名
            clean_place = place[:3]

        if has_chat_after:
            # 用户在聊天中提到位置，走 chat 意图，但把位置透传给 ChatAgent
            return {
                "intent": "chat", "chat_type": "location_confirm", "search_keywords": [],
                "location_hint": clean_place or place,
                "price_max": None, "price_min": None,
                "feature_requests": [], "need_route": False,
                "is_followup": False, "target_poi_name": None, "target_poi_id": None,
                "declared_preferences": {"location": clean_place or place},
                **_collab_reset_fields(),
            }

        # 纯位置声明：已知城市走 search
        from ..tools.amap_client import extract_city_name
        city = extract_city_name(clean_place or place)
        if city:
            return {
                "intent": "search", "search_keywords": ["美食"],
                "location_hint": city, "price_max": None, "price_min": None,
                "feature_requests": [], "need_route": False,
                "is_followup": False, "target_poi_name": None, "target_poi_id": None,
                "declared_preferences": {"location": city, "city": city},
                **_collab_reset_fields(),
            }
        # 城市未知（如"昆山"不在 CITY_CODES）：不再跳过规则，
        # 让 LLM 来决定意图，但把 clean_place 作为上下文

    # 快速规则：社交感谢语（"谢谢"、"好的"、"嗯嗯"等）→ chat 意图
    # 这必须在 route 规则之前检测，因为"谢谢你的推荐，第一家不错"中包含"第一家"
    # 但用户意图是感谢而非导航
    _SOCIAL_PATTERNS = ["谢谢", "感谢", "好的", "嗯嗯", "哈哈", "不用了", "太棒了", "不错"]
    q_lower = query.strip().lower()
    for p in _SOCIAL_PATTERNS:
        if p in q_lower:
            # 检查是否纯粹是社交感谢，没有明确的导航意图
            _NAV_PATTERNS = ["怎么去", "怎么走", "导航到", "路线到", "带我去", "送我去"]
            has_nav = any(n in q_lower for n in _NAV_PATTERNS)
            if not has_nav:
                logger.info("intent_parser: rule override ->chat (matched social '%s')", p)
                return {
                    "intent": "chat", "chat_type": "social", "search_keywords": [],
                    "location_hint": None, "price_max": None, "price_min": None,
                    "feature_requests": [], "need_route": False,
                    "is_followup": False, "target_poi_name": None, "target_poi_id": None,
                    "declared_preferences": None,
                    **_collab_reset_fields(),
                }

    # 快速规则：路线意图（"怎么去第X家"、"去XX"、"导航到XX"）
    # route 意图不应走搜索路径，而是直接从上轮推荐中取目标走路线规划
    _ROUTE_ORDINAL = re.search(r"第([一二三四五1-5])家", query)
    _ROUTE_KEYWORDS = re.search(r"怎么去|怎么走|导航|路线", query)
    if _ROUTE_KEYWORDS or _ROUTE_ORDINAL:
        target_name = None
        # 解析"第X家"中的序号，从 prev_search_context.recommendations 获取目标名
        if _ROUTE_ORDINAL:
            _ORDINAL = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4,
                        "1": 0, "2": 1, "3": 2, "4": 3, "5": 4}
            idx = _ORDINAL.get(_ROUTE_ORDINAL.group(1), 0)
            # 从 prev_search_context 保存的上轮推荐中获取
            prev_recs = (prev or {}).get("recommendations") or []
            if prev_recs and idx < len(prev_recs):
                target_name = prev_recs[idx].get("name")
                logger.info("route rule: idx=%d target_name=%s from prev_recs", idx, target_name)

        # route 意图需要恢复上轮位置（从 prev_search_context）
        prev_loc = None
        prev_city = None
        if prev:
            prev_loc = prev.get("location") or prev.get("location_hint")
            prev_city = prev.get("city")

        return {
            "intent": "route", "search_keywords": [],
            "location_hint": prev_loc, "price_max": None, "price_min": None,
            "feature_requests": [], "need_route": True,
            "is_followup": True, "target_poi_name": target_name, "target_poi_id": None,
            "declared_preferences": None,
            "user_city": prev_city or state.get("user_city") or state.get("home_city"),
            **_collab_reset_fields(),
        }

    # 构建上一轮搜索上下文（含用户显式声明的偏好）
    prev_ctx = ""
    if prev:
        parts = []
        if prev.get("keywords"):
            parts.append(f"关键词: {', '.join(prev['keywords'])}")
        if prev.get("price_max"):
            parts.append(f"最高人均: {prev['price_max']}元")
        if prev.get("price_min"):
            parts.append(f"最低人均: {prev['price_min']}元")
        if prev.get("location"):
            parts.append(f"搜索位置: {prev['location']}")
        if prev.get("location_hint"):
            parts.append(f"用户提到的位置: {prev['location_hint']}")
        if prev.get("features"):
            parts.append(f"特殊需求: {', '.join(prev['features'])}")
        # 用户显式声明的偏好（记忆系统核心）
        if prev.get("disliked"):
            parts.append(f"用户不喜欢: {', '.join(prev['disliked'])}")
        if prev.get("preferred"):
            parts.append(f"用户喜欢: {', '.join(prev['preferred'])}")
        if parts:
            prev_ctx = "上一轮搜索条件: " + "; ".join(parts) + "\n\n"

    llm = _get_llm()
    if llm is None:
        return _rule_based_intent(query)

    try:
        content = await llm.ainvoke(
            INTENT_PARSER_PROMPT.format(
                history=history, query=query, prev_context=prev_ctx
            ),
            max_tokens=200,   # 意图识别只需返回50字JSON，不需要2000
            temperature=0.1,  # 低温度保证输出稳定
        )
        if not content:
            # LLM 返回空（限流/超时等），走规则降级
            return _rule_based_intent(query)
        parsed = _parse_json_safely(content)
    except Exception as e:
        logger.warning("intent parser failed: %s", e)
        return _rule_based_intent(query)

    # 解析成功（keywords 可以为空，例如 chat 意图）
    intent = parsed.get("intent", "search")
    chat_type = parsed.get("chat_type")  # LLM 提取的 chat 子类型
    keywords = parsed.get("keywords")  # 可能是 [] 或 None

    # ── 规则后校验：防止 LLM 把闲聊/身份问题误判为 search ──
    _rule_forced_chat = False
    if intent not in ("chat", "clarify"):
        _chat_patterns = [
            "你是谁", "你叫什么", "你是什么", "你是哪", "谁开发的", "谁做的",
            "你能做什么", "你有什么功能", "你有什么用", "介绍一下你",
            "都有哪些功能", "有哪些功能", "你能干嘛", "你会什么",
            "你好", "嗨", "hello", "hi", "早上好", "晚上好", "下午好",
            "谢谢", "好的", "嗯嗯", "哈哈", "不用了", "太棒了",
        ]
        # 规则对应的 chat_type 映射
        _identity_pats = {"你是谁", "你叫什么", "你是什么", "你是哪", "谁开发的", "谁做的",
                          "介绍一下你"}
        _feature_pats = {"你能做什么", "你有什么功能", "你有什么用",
                         "都有哪些功能", "有哪些功能", "你能干嘛", "你会什么"}
        _greeting_pats = {"你好", "嗨", "hello", "hi", "早上好", "晚上好", "下午好"}
        _social_pats = {"谢谢", "好的", "嗯嗯", "哈哈", "不用了", "太棒了"}
        q_lower = query.strip().lower()
        for pat in _chat_patterns:
            if pat in q_lower:
                logger.info("intent_parser: rule override %s->chat (matched '%s')", intent, pat)
                intent = "chat"
                keywords = []
                parsed["intent"] = "chat"
                _rule_forced_chat = True
                # 推导 chat_type
                if pat in _identity_pats:
                    chat_type = "identity"
                elif pat in _feature_pats:
                    chat_type = "feature"
                elif pat in _greeting_pats:
                    chat_type = "greeting"
                elif pat in _social_pats:
                    chat_type = "social"
                else:
                    chat_type = "chat"
                break

    # 关键修复：如果用户说了位置（如"我在成都"），即使LLM解析为chat意图，
    # 也应该走搜索路径——但仅限用户同时表达了搜索意图的情况。
    # 规则校验已经认定的闲聊（问候/身份问题），不再被 location_hint 反转。
    # 纯位置+闲聊（"我在昆山你记住了吗"）不应被反转——用户在聊天不是在搜餐厅。
    location_hint_val = parsed.get("location_hint") or (
        (parsed.get("declared_preferences") or {}).get("location") if isinstance(parsed.get("declared_preferences"), dict) else None
    )
    _SEARCH_HINT_WORDS = ["找", "吃", "喝", "推荐", "搜", "附近", "有没有", "想去", "想吃", "来点"]
    _has_search_hint = any(w in query for w in _SEARCH_HINT_WORDS)
    if location_hint_val and intent in ("chat", "clarify") and not _rule_forced_chat and _has_search_hint:
        intent = "search"
        if not keywords:
            keywords = ["美食"]
        logger.info("intent_parser: chat->search because location_hint=%s + search_hint", location_hint_val)

    # LLM 返回了位置信息但没给关键词（泛搜索："附近有什么好吃的"）：
    # 不能丢弃 LLM 的位置数据走 rule-based 降级，用默认词 "美食" 代替。
    if intent == "search" and not keywords:
        has_location = bool(location_hint_val)
        if has_location:
            keywords = ["美食"]
            logger.info("intent_parser: LLM returned location but no keywords, defaulting to '美食'")
        else:
            return _rule_based_intent(query)

    # location_hint 与 declared_preferences.location 双向同步：
    # LLM 偶尔只填一边，本轮 location_node 就拿不到位置。这里做双向兜底回填。
    location_hint = parsed.get("location_hint")
    declared = parsed.get("declared_preferences") or {}
    declared_loc = declared.get("location") if isinstance(declared, dict) else None
    if not location_hint and declared_loc:
        location_hint = declared_loc
        logger.info("intent_parser: synced declared.location -> location_hint: %s", declared_loc)
    elif location_hint and not declared_loc:
        # 反向同步：LLM 只填了 location_hint 但没填 declared_preferences.location
        if not isinstance(declared, dict):
            declared = {}
        declared["location"] = location_hint
        logger.info("intent_parser: synced location_hint -> declared.location: %s", location_hint)

    # intent_parser 完成：推送结果事件
    intent_label = {"search": "搜索餐厅", "chat": "闲聊", "route": "路线规划", "clarify": "澄清需求"}.get(intent, intent)
    await push_event(session_id, evt_agent_done("intent_parser", f"识别为{intent_label}"))

    return {
        "intent": intent,
        "chat_type": chat_type if intent in ("chat", "clarify") else None,
        "search_keywords": keywords or [],
        "location_hint": location_hint,
        "price_max": parsed.get("price_max"),
        "price_min": parsed.get("price_min"),
        "feature_requests": parsed.get("features", []),
        "need_route": parsed.get("need_route", False) or False,
        "search_radius": state.get("search_radius") or 1000,
        "search_retry_count": 0,
        "is_followup": bool(parsed.get("is_followup", False)),
        "target_poi_name": parsed.get("target_poi_name"),
        "declared_preferences": declared if declared else None,
        **_collab_reset_fields(),
    }


# ── 关键词规则降级 ──

# 常见菜系/品类词
_FOOD_KEYWORDS = [
    "火锅", "日料", "日式", "寿司", "烤肉", "烧烤", "川菜", "粤菜",
    "湘菜", "东北菜", "西餐", "面馆", "饺子", "麻辣烫", "米线",
    "咖啡", "奶茶", "甜品", "快餐", "自助餐", "海鲜", "烤鱼",
    "披萨", "汉堡", "炸鸡", "轻食", "素食", "韩料", "韩国料理",
    "泰国菜", "越南菜", "墨西哥菜", "小龙虾", "串串", "冒菜",
]

# 泛搜索关键词：用户没有指定菜系时的通用词 → 映射到高德可搜索的关键词
_GENERIC_FOOD_PATTERNS = [
    ("好吃的", "美食"),
    ("好吃", "美食"),
    ("吃的", "美食"),
    ("美食", "美食"),
    ("餐厅", "餐厅"),
    ("饭店", "餐厅"),
    ("馆子", "餐厅"),
    ("外卖", "外卖"),
    ("夜宵", "夜宵"),
    ("早餐", "早餐"),
    ("午饭", "美食"),
    ("晚饭", "美食"),
    ("宵夜", "夜宵"),
]


def _rule_based_intent(query: str) -> dict:
    """LLM 不可用时，从原句中用规则提取搜索关键词、位置和价格。"""
    import re

    keywords: list[str] = []
    for kw in _FOOD_KEYWORDS:
        if kw in query:
            keywords.append(kw)

    # 泛搜索模式匹配（"好吃的"、"吃的"、"餐厅" 等）
    if not keywords:
        for pattern, mapped in _GENERIC_FOOD_PATTERNS:
            if pattern in query:
                keywords.append(mapped)
                break

    # 提取位置（城市名）
    location_hint = None
    declared_prefs = None
    from ..tools.amap_client import extract_city_name
    # 按城市名从长到短匹配，避免 "苏" 匹配到 "苏州" 之类
    city_match = extract_city_name(query)
    if city_match:
        location_hint = city_match
        declared_prefs = {"location": city_match, "city": city_match}
        # 如果只有位置没有菜系关键词，默认搜索美食
        if not keywords:
            keywords = ["美食"]

    if not keywords:
        # 没匹配到菜系也没有位置，取最后几个字作为关键词
        keywords.append(query[-4:] if len(query) > 4 else query)

    # 提取价格
    price_max = None
    m = re.search(r"(\d+)\s*[元块]?[/每]人", query)
    if m:
        price_max = int(m.group(1))
    m = re.search(r"人均\s*(\d+)", query)
    if m:
        price_max = int(m.group(1))

    return {
        "intent": "search",
        "search_keywords": keywords,
        "location_hint": location_hint,
        "price_max": price_max,
        "price_min": None,
        "feature_requests": [],
        "need_route": False,
        "search_radius": 1000,
        "search_retry_count": 0,
        "is_followup": False,
        "target_poi_name": None,
        "declared_preferences": declared_prefs,
        **_collab_reset_fields(),
    }


# ──────────── 节点2：位置解析 ────────────


async def location_node(state: dict) -> dict:
    """位置解析。

    优先级（从高到低）：
      1. user_location  — 前端 GPS 坐标（最准）
      2. state.location_hint  — 本轮 LLM 提取的位置描述
      3. prev_search_context.location_hint  — 上一轮记忆（多轮对话）
      4. home_city  — 永久层 users.home_city
      5. IP 定位兜底
    """
    user_loc = state.get("user_location")
    hint = state.get("location_hint")
    user_city = state.get("user_city") or settings.AMAP_DEFAULT_CITY

    # 上一轮记忆：从 prev_search_context 取 location_hint
    if not hint:
        prev_ctx = state.get("prev_search_context") or {}
        prev_hint = prev_ctx.get("location_hint")
        if prev_hint:
            hint = prev_hint
            logger.info("location_node: reuse prev_search_context.location_hint=%s", hint)

    # 永久层：home_city
    home_city = state.get("home_city")

    client = get_amap_client()

    if user_loc:
        target = user_loc
        # GPS 坐标存在但城市名未知时，用 regeocode 反查
        if not state.get("user_city"):
            try:
                regeo = await client.regeocode(user_loc)
                comp = regeo.get("addressComponent") or {}
                regeo_city = comp.get("city") or comp.get("province")
                if regeo_city:
                    regeo_city = regeo_city.rstrip("市")
                    user_city = regeo_city
                    logger.info("location_node: regeocode from GPS resolved city=%s", user_city)
            except Exception as e:
                logger.warning("location_node: regeocode from GPS failed: %s", e)
    elif hint:
        try:
            target = await client.geocode(hint, user_city)
        except Exception as e:
            logger.warning("geocode failed for '%s': %s", e.__class__.__name__, e)
            target = None

        if target:
            # geocode 成功 → 用 resolve_city_from_hint 获取城市名
            # （对"昆山"等不在 CITY_CODES 中的地名，会走 geocode+regeocode 路径）
            city_from_hint = await resolve_city_from_hint(hint, user_city)
            if city_from_hint:
                user_city = city_from_hint
            else:
                # 最后尝试：对 geocode 得到的坐标做 regeocode
                try:
                    regeo = await client.regeocode(target)
                    comp = regeo.get("addressComponent") or {}
                    regeo_city = comp.get("city") or comp.get("province")
                    if regeo_city:
                        regeo_city = regeo_city.rstrip("市")
                        user_city = regeo_city
                        logger.info("location_node: regeocode from coords resolved city=%s", user_city)
                except Exception as e:
                    logger.warning("location_node: regeocode from coords failed: %s", e)
        else:
            # geocode 失败 → 尝试 resolve_city_from_hint 获取城市名
            logger.warning("geocode returned empty for '%s', fallback to resolve", hint)
            city_from_hint = await resolve_city_from_hint(hint, user_city)
            if city_from_hint:
                user_city = city_from_hint
                target = await resolve_city_center(city_from_hint)
            else:
                target = await resolve_city_center(user_city)
    elif home_city:
        # 永久层兜底：用户已沉淀的常驻城市
        logger.info("location_node: fallback to home_city=%s", home_city)
        target = await resolve_city_center(home_city)
        user_city = home_city
    else:
        # IP 定位
        ip_data = await client.ip_locate()
        city_name = ip_data.get("city") or user_city
        target = await resolve_city_center(city_name)
        user_city = city_name

    return {
        "target_location": target,
        "user_city": user_city,
        "user_city_code": get_city_code(user_city) or get_city_code(settings.AMAP_DEFAULT_CITY),
    }


# ──────────── 节点3：并行上下文收集 ────────────


async def context_gather_node(state: dict) -> dict:
    client = get_amap_client()

    weather_task = client.get_weather(state.get("user_city_code") or get_city_code(settings.AMAP_DEFAULT_CITY))
    pref_task = _get_user_pref(state["user_id"])

    weather, pref = await asyncio.gather(weather_task, pref_task, return_exceptions=True)

    w = weather if isinstance(weather, dict) else None
    p = pref if isinstance(pref, dict) else None

    return {
        "weather": w,
        "user_preference": p,
        "is_new_user": p is None,
    }


async def _get_user_pref(user_id: str) -> dict | None:
    try:
        from ..services.preference_service import get_user_preference
        from ..core.database import db_session

        async with db_session() as db:
            return await get_user_preference(db, user_id)
    except Exception as e:
        logger.warning("get_user_preference failed: %s", e)
        return None


# ──────────── 节点：获取天气（Supervisor 直接做） ────────────


async def get_weather_node(state: dict) -> dict:
    """获取当前天气（轻量操作，Supervisor 直接做）。"""
    session_id = state.get("session_id", "")
    await push_event(session_id, evt_agent_start("get_weather", "查询天气..."))
    city_code = state.get("user_city_code") or get_city_code(settings.AMAP_DEFAULT_CITY)
    client = get_amap_client()
    try:
        weather = await client.get_weather(city_code)
    except Exception as e:
        logger.warning("get_weather failed: %s", e)
        weather = None
    label = weather.get("weather", "未知") if isinstance(weather, dict) else "未知"
    await push_event(session_id, evt_agent_done("get_weather", f"天气: {label}"))
    return {"weather": weather if isinstance(weather, dict) else None}


# ──────────── 节点4：搜索 ────────────


# 搜索半径递增表：第 N 轮（0-indexed）使用的半径。
# 末位作为兜底（重试次数超过表长时），评分门槛在第 3 轮起放宽。
RADIUS_BY_ATTEMPT = [1000, 2000, 5000]


async def search_node(state: dict) -> dict:
    target = state.get("target_location")
    if not target:
        target = settings.DEFAULT_LOCATION

    # attempt 是"本次"是第几次搜索（0=首次，1=第二次……）
    attempt = state.get("search_retry_count", 0)
    radius = RADIUS_BY_ATTEMPT[min(attempt, len(RADIUS_BY_ATTEMPT) - 1)]

    keywords = state.get("search_keywords") or [state.get("user_query", "")]
    max_price = state.get("price_max") or 999
    # 第 3 次起放宽评分门槛（前两次保持品质）
    min_rating = 0.0 if attempt < 2 else 3.0

    logger.info(
        "[搜索] 第%d轮 半径%dm 关键词:%s min_rating=%.1f",
        attempt + 1, radius, keywords, min_rating,
    )

    pois = await search_restaurants(
        location=target,
        keywords=keywords,
        radius=radius,
        max_price=max_price,
        min_rating=min_rating,
    )

    return {
        "raw_pois": pois,
        "search_radius": radius,
        "search_retry_count": attempt + 1,
    }


# ──────────── 节点5：过滤与排序 ────────────


async def filter_and_rank_node(state: dict) -> dict:
    pois = state.get("raw_pois") or []

    # 基本过滤
    valid = [p for p in pois if p.get("name") and p.get("location")]

    # 合并用户显式声明的偏好到 user_preference（当轮记忆）
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

    if state.get("is_new_user") and not declared:
        ranked = cold_start_rank(valid, context)
    else:
        ranked = await rerank_pois(
            user_id=state["user_id"],
            pois=valid,
            context=context,
            user_preference=user_pref,
        )

    return {
        "filtered_pois": ranked[:10],
        "show_cold_start_guide": bool(state.get("is_new_user")),
    }


# ──────────── 节点6：智能推荐 ────────────


async def recommend_node(state: dict) -> dict:
    pois = state.get("filtered_pois") or []
    top5 = pois[:5]
    weather = state.get("weather") or {}
    pref = state.get("user_preference")

    # Follow-up handling: if user is asking about a specific restaurant
    target_poi = None
    if state.get("is_followup") and state.get("target_poi_name"):
        target_name = state["target_poi_name"]
        target_poi = next(
            (p for p in pois if target_name in (p.get("name") or "")),
            None,
        )

    if not top5:
        radius = state.get("search_radius", 1000)
        return {
            "recommendations": [],
            "final_response": EMPTY_RESULT_RESPONSE.format(
                radius=radius,
                price_max=state.get("price_max") or "不限",
            ),
        }

    # 无 LLM 时用规则降级
    llm = _get_llm()
    if llm is None:
        recs = []
        for i, p in enumerate(top5[:3]):
            recs.append(
                {
                    **p,
                    "rank": i + 1,
                    "reason": f"评分 {p.get('rating','-')} 分，人均 ¥{p.get('cost','-')}，距离 {p.get('distance','-')}m",
                    "highlight": p.get("type", ""),
                    "suitable_for": "日常用餐",
                }
            )
        return {"recommendations": recs, "final_response": ""}

    try:
        content = await llm.ainvoke(
            RECOMMENDER_PROMPT.format(
                user_query=state.get("user_query", ""),
                weather=f"{weather.get('weather','未知')} {weather.get('temperature','')}°C",
                user_preference=(
                    pref.get("preference_text", "新用户，无历史偏好")
                    if pref
                    else "新用户"
                ),
                pois=json.dumps(top5, ensure_ascii=False, indent=2),
            ),
            system_prompt=AEROSAVOR_SYSTEM_PROMPT,
        )
        parsed = _parse_json_safely(content)
    except Exception as e:
        logger.warning("recommend_node LLM failed: %s", e)
        parsed = {}

    recommendations = []
    for rec in parsed.get("recommendations", []):
        matching = next(
            (p for p in top5 if p["id"] == rec.get("poi_id")),
            None,
        )
        if matching:
            recommendations.append(
                {
                    **matching,
                    "rank": rec.get("rank", 1),
                    "reason": rec.get("reason", ""),
                    "highlight": rec.get("highlight", ""),
                    "suitable_for": rec.get("suitable_for", ""),
                }
            )

    summary = parsed.get("summary", "")
    result = {"recommendations": recommendations, "final_response": summary}
    if target_poi:
        result["target_poi"] = target_poi
    return result


# ──────────── 节点7：路线规划 ────────────


async def route_node(state: dict) -> dict:
    target = state.get("target_poi") or (
        state["recommendations"][0] if state.get("recommendations") else None
    )
    origin = state.get("user_location") or state.get("target_location") or settings.DEFAULT_LOCATION

    if not target or not target.get("location"):
        return {"route_info": None}

    city = state.get("user_city", "")
    route = await plan_routes(origin, target["location"], city=city)
    return {"route_info": route}


# ──────────── 节点8：格式化最终响应 ────────────


async def format_response_node(state: dict) -> dict:
    """格式化最终响应。

    chat/clarify 意图：ChatAgent 已生成 final_response，直接透传。
    其他意图：走推荐列表格式化。
    """
    session_id = state.get("session_id", "")
    await push_event(session_id, evt_agent_start("format_response", "生成回复..."))

    intent = state.get("intent", "search")

    # 闲聊/澄清意图：ChatAgent 已处理，直接透传
    if intent in ("chat", "clarify"):
        await push_event(session_id, evt_agent_done("format_response", "回复已生成"))
        return {"final_response": state.get("final_response", "")}

    recs = state.get("recommendations") or []
    route = state.get("route_info")
    weather = state.get("weather") or {}
    summary = state.get("final_response", "")

    lines: list[str] = []

    # 路线意图（跳过了 search/recommend，只有路线信息）
    if intent == "route" and route and not recs:
        dest_name = route.get("destination_name") or state.get("target_poi_name") or "目标餐厅"
        lines.append(f"🗺️ **前往 {dest_name} 的路线**\n")
        if route.get("walking"):
            w = route["walking"]
            lines.append(f"🚶 步行约{w['duration_min']}分钟（{w['distance_m']}m）")
        if route.get("driving"):
            d = route["driving"]
            lines.append(f"🚗 驾车约{d['duration_min']}分钟")
        if route.get("transit"):
            t = route["transit"]
            lines.append(f"🚌 公交约{t['duration_min']}分钟")
        lines.append(f"\n[🗺️ 开始导航]({route.get('nav_url','')})")
        await push_event(session_id, evt_agent_done("format_response", "路线已生成"))
        return {"final_response": "\n".join(lines)}

    # 路线意图但没有路线信息
    if intent == "route" and not route:
        await push_event(session_id, evt_agent_done("format_response", "无法规划路线"))
        return {"final_response": "抱歉，无法规划路线。请先搜索餐厅，然后再问我怎么去 😊"}

    # 天气提示
    if weather.get("is_raining"):
        lines.append("🌧️ 今天有雨，推荐优先考虑有室内座位或外卖的餐厅\n")

    # Compare 意图：对比展示
    if intent == "compare" and len(recs) >= 2:
        lines.append("📊 **对比推荐**\n")
        for i, rec in enumerate(recs[:3]):
            rating = rec.get("rating", 0)
            cost = rec.get("cost", 0)
            dist = rec.get("distance", 0)
            lines.append(f"**{i + 1}. {rec['name']}**")
            lines.append(f"  ⭐ {rating} | 💰 ¥{cost}/人 | 📍 {dist}m")
            if rec.get("highlight"):
                lines.append(f"  ✨ {rec['highlight']}")
            if rec.get("reason"):
                lines.append(f"  💬 {rec['reason']}")
            if rec.get("suitable_for"):
                lines.append(f"  🎯 {rec['suitable_for']}")
            lines.append("")
        lines.append("---")
        lines.append("告诉我更倾向哪家，我帮你规划路线 🗺️")

    else:
        # 标准推荐列表
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, rec in enumerate(recs[:5]):
            medal = medals[i] if i < len(medals) else f"{i + 1}."
            lines.append(f"{medal} **{rec['name']}**")
            rating = rec.get("rating", 0)
            cost = rec.get("cost", 0)
            dist = rec.get("distance", 0)
            highlight = rec.get("highlight", "")
            reason = rec.get("reason", "")
            suitable = rec.get("suitable_for", "")
            lines.append(f"⭐ {rating} | 💰 ¥{cost}/人 | 📍 {dist}m")
            if suitable:
                lines.append(f"🎯 {suitable}")
            if highlight:
                lines.append(f"✨ {highlight}")
            if reason:
                lines.append(f"💬 {reason}")

            # 路线信息
            if route and len(recs) == 1:
                if route.get("walking"):
                    w = route["walking"]
                    lines.append(f"🚶 步行约{w['duration_min']}分钟（{w['distance_m']}m）")
                if route.get("driving"):
                    d = route["driving"]
                    lines.append(f"🚗 驾车约{d['duration_min']}分钟")
                if route.get("transit"):
                    t = route["transit"]
                    lines.append(f"🚌 公交约{t['duration_min']}分钟")
                lines.append(f"[🗺️ 开始导航]({route.get('nav_url','')})")
            else:
                lines.append(f"[查看详情]({rec.get('amap_url','')})")
            lines.append("")

    # 替换或追加 summary
    if summary:
        if lines and lines[-1] == "":
            lines[-1] = summary + "\n"
        else:
            lines.append(summary + "\n")

    # 冷启动
    if state.get("show_cold_start_guide"):
        lines.append("---")
        lines.append("💡 **告诉我你的偏好，下次推荐更准！**")
        lines.append("比如：哪家不错 / 有没有不喜欢的菜系 / 习惯的价格范围")

    # 多餐厅时可导航
    if len(recs) > 1 and not route:
        lines.append("---")
        lines.append("想去哪一家？告诉我，我帮你规划路线 🗺️")

    # 无推荐结果的兜底
    if not recs and not route:
        lines.append(
            "抱歉，暂时没找到符合条件的餐厅 😔\n\n"
            "建议试试：\n"
            "- 放宽价格限制\n"
            "- 换个关键词（如把「日料」改为「寿司」）\n"
            "- 扩大搜索范围（告诉我可以接受多远）"
        )

    await push_event(session_id, evt_agent_done("format_response", "回复已生成"))
    return {"final_response": "\n".join(lines)}


# ──────────── 节点9：Supervisor 动态决策 ────────────

MAX_ITERATIONS = 3
MAX_DELEGATIONS = 2  # Agent 间委派最多 2 次，防无限循环

SUPERVISOR_DECISION_PROMPT = """你是 AeroSavor 的任务调度器。根据各 Agent 的反馈，决定下一步行动。

用户原始需求：{user_query}
已执行步骤：{completed_steps}
当前迭代次数：{iteration_count}（最多允许 {max_iterations} 次）

各 Agent 的最新反馈：
{agent_messages}

当前搜索结果数量：{poi_count} 家
当前关键词：{keywords}
当前位置：{location}

请决定下一步，以 JSON 返回：
{{
  "next_action": 以下之一：
    "recommend_agent"   → 结果足够好，进入推荐
    "search_agent"      → 需要重新搜索（需提供新关键词）
    "location_agent"    → 需要重新定位（结果与位置无关）
    "end"               → 直接结束（结果实在找不到，输出兜底回复）,
  "reason": "决策理由，10字以内",
  "new_keywords": ["新关键词，仅当 next_action=search_agent 时填写"],
  "new_location_hint": "新位置描述，仅当 next_action=location_agent 时填写"
}}

决策原则：
- 结果 ≥ 3 家且 Agent 无投诉 → recommend_agent
- 结果 0 家 且 已尝试当前位置 → location_agent（换商圈）
- 结果 < 3 家 或 RecommendAgent 投诉质量差 → search_agent（换关键词）
- 迭代次数已达上限 → end（不再重试）

质量反馈处理（关键）：
- 如果 RecommendAgent 报告 quality_poor，仔细阅读 reason 字段：
  - reason 提到菜系不匹配（如"要日料但搜到快餐"）→ search_agent，new_keywords 用更精确的菜系词（如["日料","寿司","日本料理"]）
  - reason 提到价格不匹配 → search_agent，new_keywords 加价格相关词
  - reason 提到距离太远 → location_agent，换更近的商圈
- 如果已有推荐结果但质量差，优先尝试 search_agent 换关键词，而不是直接输出
- 只有 quality_check_passed=True 时才推荐输出"""


async def message_dispatch_node(state: dict) -> dict:
    """读取 agent_messages，将非 supervisor 导向的请求路由到对应 Agent。

    同时推送 SSE 事件让前端看到 Agent 间通信。
    这是 Agent 间直接通信的路由层——Supervisor 保持全局视野，
    但 Agent 可以给其他 Agent 发送 request 消息。

    委派计数保护：超过 MAX_DELEGATIONS 次委派后，不再路由请求，
    强制走 format_response 输出当前结果。
    """
    session_id = state.get("session_id", "")
    messages = state.get("agent_messages", [])
    delegation_count = state.get("delegation_count", 0)

    # 找出所有非 supervisor 导向的 pending request
    pending = {}
    for msg in reversed(messages[-20:]):  # 只看最近 20 条
        to = msg.get("to_agent", "supervisor")
        if to != "supervisor" and msg.get("message_type") == "request":
            if to not in pending:
                pending[to] = msg

    updates = {}

    # 委派计数保护：超过上限不再路由
    if delegation_count >= MAX_DELEGATIONS and pending:
        logger.warning("message_dispatch: MAX_DELEGATIONS reached (%d), ignoring pending requests",
                       delegation_count)
        await push_event(session_id, evt_collaboration(
            "supervisor", "委派次数已达上限，使用当前结果输出",
        ))
        # 清空 pending requests，防止后续路由
        for agent in pending:
            field = f"pending_request_for_{agent}"
            updates[field] = None
        updates["delegation_count"] = delegation_count + 1  # 标记已超限
    else:
        for agent, req in pending.items():
            # 映射到 pending_request 字段
            field = f"pending_request_for_{agent}"
            updates[field] = req
            # 推送 SSE 事件
            await push_event(session_id, evt_agent_message(
                req.get("from_agent", ""),
                agent,
                req.get("reason", ""),
            ))
            # 推送委派事件
            await push_event(session_id, evt_delegation(
                req.get("from_agent", ""),
                agent,
                req.get("data", {}).get("request_type", ""),
            ))
            logger.info("message_dispatch: %s → %s: %s",
                         req.get("from_agent", ""), agent, req.get("reason", ""))
        if pending:
            # 每次只递增1，不管有几个 pending request
            # 避免一次质量差的结果耗尽整个委派预算
            updates["delegation_count"] = delegation_count + 1

    # 注意：agent_messages 是 Annotated[list, add]，不能通过返回值截断
    # （返回列表会被追加而非替换）。截断逻辑已移除，
    # 改为在读取时只看 messages[-20:]（已在上方 for 循环中实现）。

    return updates


async def supervisor_decision_node(state: dict) -> dict:
    """读取所有 Agent 消息，动态决定下一步。

    这是多 Agent 协作的核心：SearchAgent/RecommendAgent 通过
    agent_messages 向 Supervisor 汇报结果质量和建议，
    Supervisor 根据 LLM 判断决定重搜、换位置、还是继续推荐。
    同时通过 event_bus 推送 SSE 事件，让前端看到决策过程。
    """
    session_id = state.get("session_id", "")

    # 格式化 Agent 消息
    messages = state.get("agent_messages", [])
    msg_text = "\n".join([
        f"[{m['from_agent']}] {m['status']}: {m['reason']}"
        for m in messages[-5:]  # 只看最近 5 条
    ]) or "暂无反馈"

    iteration_count = state.get("iteration_count", 0)
    user_query = state.get("user_query", "")

    # 安全保护：超过最大迭代次数强制结束
    if iteration_count >= MAX_ITERATIONS:
        filtered_pois = state.get("filtered_pois", [])
        recommendations = state.get("recommendations", [])
        # 如果 recommend_agent 已经产出推荐，优先使用
        if recommendations:
            next_action = "format_response"
            reason = "已有推荐结果，输出回复"
        elif filtered_pois:
            next_action = "recommend_agent"
            reason = "已达迭代上限，使用现有结果推荐"
        else:
            next_action = "format_response"
            reason = "已达迭代上限，无搜索结果"
        logger.info("supervisor_decision: MAX_ITERATIONS reached, action=%s recs=%d", next_action, len(recommendations))
        await push_event(session_id, evt_supervisor_decision(reason, next_action))
        return {
            "next_action": next_action,
            "supervisor_reason": reason,
            "iteration_count": iteration_count + 1,
            "completed_steps": ["supervisor_decision"],
        }

    # 质量感知保护：有推荐结果时，只在质量通过或达到迭代上限时输出
    # 不再无脑"有结果就停"——让 LLM 决策有机会在质量差时重搜
    recommendations = state.get("recommendations", [])
    if recommendations:
        # 质量通过 → 输出
        if state.get("quality_check_passed"):
            next_action = "format_response"
            reason = "推荐质量通过，输出回复"
            logger.info("supervisor_decision: quality passed, outputting %d recs", len(recommendations))
            await push_event(session_id, evt_supervisor_decision(reason, next_action))
            return {
                "next_action": next_action,
                "supervisor_reason": reason,
                "iteration_count": iteration_count + 1,
                "completed_steps": ["supervisor_decision"],
            }
        # 达到迭代上限 → 强制输出（有总比没有好）
        if iteration_count >= MAX_ITERATIONS:
            next_action = "format_response"
            reason = "已达迭代上限，使用现有推荐"
            logger.info("supervisor_decision: MAX_ITERATIONS with %d recs, outputting", len(recommendations))
            await push_event(session_id, evt_supervisor_decision(reason, next_action))
            return {
                "next_action": next_action,
                "supervisor_reason": reason,
                "iteration_count": iteration_count + 1,
                "completed_steps": ["supervisor_decision"],
            }
        # 质量未通过且未达上限 → fall through 到 LLM 决策
        # LLM 会读到 quality_poor 的 reason 并决定重搜还是接受

    llm = _get_llm()

    # 无 LLM 时走规则降级
    if llm is None:
        next_action = _rule_based_supervisor_decision(state)
        # 构建有意义的决策原因
        filtered_pois = state.get("filtered_pois", [])
        poi_count = len(filtered_pois)
        if next_action == "recommend_agent":
            reason = f"找到{poi_count}家候选，直接推荐"
        elif next_action == "search_agent":
            reason = f"仅{poi_count}家候选，换关键词重搜"
        elif next_action == "location_agent":
            reason = "当前位置无结果，换个区域"
        else:
            reason = "输出当前结果"
        logger.info("supervisor_decision: rule-based, action=%s reason=%s", next_action, reason)
        await push_event(session_id, evt_supervisor_decision(reason, next_action))
        return {
            "next_action": next_action,
            "supervisor_reason": "规则降级决策",
            "iteration_count": iteration_count + 1,
            "completed_steps": ["supervisor_decision"],
        }

    try:
        content = await llm.ainvoke(
            SUPERVISOR_DECISION_PROMPT.format(
                user_query=user_query,
                completed_steps=", ".join(state.get("completed_steps", []) or []),
                iteration_count=iteration_count,
                max_iterations=MAX_ITERATIONS,
                agent_messages=msg_text,
                poi_count=len(state.get("filtered_pois", [])),
                keywords=", ".join(state.get("search_keywords", [])),
                location=state.get("resolved_location") or state.get("location_hint") or "未知",
            ),
            max_tokens=300,
        )
        decision = _parse_json_safely(content)
    except Exception as e:
        logger.warning("supervisor_decision LLM failed: %s, falling back to rules", e)
        decision = {}

    next_action = decision.get("next_action", "recommend_agent")

    # 合法性检查
    valid_actions = {
        "recommend_agent", "search_agent",
        "location_agent", "format_response", "end",
    }
    if next_action not in valid_actions:
        next_action = "recommend_agent"

    if next_action == "end":
        next_action = "format_response"

    # 更新关键词（如果 Supervisor 建议换关键词）
    updates: dict = {
        "next_action": next_action,
        "supervisor_reason": decision.get("reason", ""),
        "iteration_count": iteration_count + 1,
        "completed_steps": ["supervisor_decision"],
    }

    if next_action == "search_agent" and decision.get("new_keywords"):
        updates["search_keywords"] = decision["new_keywords"]

    if next_action == "location_agent" and decision.get("new_location_hint"):
        updates["location_hint"] = decision["new_location_hint"]

    # 构建搜索策略提示：从 Agent 反馈中提取结构化信息
    if next_action == "search_agent":
        strategy = _build_search_strategy(messages, decision)
        if strategy:
            updates["search_strategy_hint"] = strategy
        # 记录当前关键词为已尝试
        current_kw = state.get("search_keywords", [])
        if current_kw:
            updates["tried_keywords"] = current_kw

    # 推送 SSE 事件
    reason = decision.get("reason", "")
    if next_action == "search_agent":
        # 检查是否因质量差而重搜
        strategy_hint = updates.get("search_strategy_hint")
        if strategy_hint:
            new_kw = strategy_hint.get("prefer_types", [])
            strategy_text = f"换「{'、'.join(new_kw)}」试试" if new_kw else "换关键词重搜"
            await push_event(session_id, evt_quality_retry(
                reason=strategy_hint.get("reason", "结果不匹配"),
                new_strategy=strategy_text,
            ))
        else:
            await push_event(session_id, evt_collaboration(
                "supervisor",
                "结果不够理想，换个方向重新找找...",
            ))
    elif next_action == "location_agent":
        await push_event(session_id, evt_collaboration(
            "supervisor",
            "当前位置附近没找到，换个区域试试...",
        ))
    await push_event(session_id, evt_supervisor_decision(reason, next_action))

    logger.info(
        "supervisor_decision: action=%s reason=%s iteration=%d",
        next_action, reason, iteration_count + 1,
    )

    return updates


def _build_search_strategy(feedback_messages: list, llm_decision: dict) -> dict | None:
    """从 Agent 反馈 + Supervisor LLM 决策中构建搜索策略提示。

    策略类型：
    - cuisine_mismatch: avoid_types + prefer_types（换菜系关键词）
    - price_mismatch: price_hint + price_max（调整价格范围）
    - distance_mismatch: radius_reduction（缩小搜索半径）
    - general: new_keywords（通用换关键词）
    """
    strategy = {
        "avoid_types": [],
        "prefer_types": [],
        "reason": "",
    }

    # 1. 从 feedback 消息中提取结构化策略数据
    for msg in reversed(feedback_messages[-5:]):
        data = msg.get("data", {})
        mismatch = data.get("mismatch_type", "")
        if mismatch == "cuisine_mismatch":
            got_types = data.get("got_types", "")
            strategy["avoid_types"] = [t.strip() for t in got_types.split(",") if t.strip()] if got_types else []
            strategy["prefer_types"] = data.get("prefer_types", [])
            strategy["mismatch_type"] = mismatch
            strategy["reason"] = f"菜系不匹配: {msg.get('reason', '')}"
            break
        elif mismatch == "price_mismatch":
            price_hint = data.get("price_hint", "lower")
            strategy["price_hint"] = price_hint
            if data.get("price_max"):
                strategy["price_max"] = data["price_max"]
            strategy["mismatch_type"] = mismatch
            strategy["reason"] = f"价格不匹配: {msg.get('reason', '')}"
            break
        elif mismatch == "distance_mismatch":
            strategy["radius_reduction"] = True
            strategy["mismatch_type"] = mismatch
            strategy["reason"] = f"距离不匹配: {msg.get('reason', '')}"
            break
        elif mismatch in ("general", "empty", "low_result"):
            # 通用不匹配：使用 Supervisor LLM 建议的关键词
            strategy["mismatch_type"] = mismatch
            strategy["reason"] = msg.get("reason", "结果与用户需求不匹配")
            break

    # 2. 从 pending_request 消息中提取委派策略（优先级更高）
    for msg in reversed(feedback_messages[-5:]):
        if msg.get("message_type") == "request" and msg.get("to_agent") != "supervisor":
            req_data = msg.get("data", {})
            if msg.get("to_agent") == "search_agent":
                if req_data.get("avoid_types"):
                    strategy["avoid_types"] = req_data["avoid_types"]
                if req_data.get("prefer_types"):
                    strategy["prefer_types"] = req_data["prefer_types"]
                if req_data.get("price_hint"):
                    strategy["price_hint"] = req_data["price_hint"]
                if req_data.get("price_max"):
                    strategy["price_max"] = req_data["price_max"]
                if not strategy.get("reason"):
                    strategy["reason"] = req_data.get("reason", "委派搜索")
            elif msg.get("to_agent") == "location_agent":
                if req_data.get("need_closer"):
                    strategy["radius_reduction"] = True
                if not strategy.get("reason"):
                    strategy["reason"] = req_data.get("reason", "委派重定位")

    # 3. 从 LLM 决策中补充关键词
    new_kw = llm_decision.get("new_keywords", [])
    if new_kw and not strategy.get("prefer_types"):
        strategy["prefer_types"] = new_kw
        if not strategy.get("reason"):
            strategy["reason"] = "Supervisor 建议换关键词"

    if not strategy.get("reason") and not strategy.get("prefer_types") and not strategy.get("avoid_types"):
        return None

    return strategy


def _rule_based_supervisor_decision(state: dict) -> str:
    """LLM 不可用时的规则降级：根据搜索结果数量决策。"""
    filtered_pois = state.get("filtered_pois", [])
    count = len(filtered_pois)
    iteration_count = state.get("iteration_count", 0)

    # 硬保护：超过最大迭代次数强制结束
    if iteration_count >= MAX_ITERATIONS:
        if filtered_pois:
            return "recommend_agent"
        return "format_response"

    # 检查 Agent 消息中的反馈
    messages = state.get("agent_messages", [])
    has_quality_poor = any(
        m.get("status") == "quality_poor" for m in messages[-3:]
    )

    # 质量检查不通过 → 需要重新搜索
    if has_quality_poor and iteration_count < MAX_ITERATIONS:
        return "search_agent"

    if count >= 3:
        return "recommend_agent"
    elif count == 0 and iteration_count < 1:
        return "location_agent"
    elif count < 3 and iteration_count < MAX_ITERATIONS:
        return "search_agent"
    elif filtered_pois:
        # 有结果但不足3家 → 硬着头皮推荐
        return "recommend_agent"
    else:
        return "format_response"


def route_after_supervisor(state: dict) -> str:
    """Supervisor 决策后的路由，含安全保护。

    根据 Supervisor 决定的 next_action 路由到对应节点：
    - recommend_agent → 进入推荐
    - search_agent → 重新搜索
    - location_agent → 重新定位
    - format_response → 输出结果（兜底）

    核心原则：
    1. 委派请求最高优先级（Agent 间直接通信）
    2. 质量通过或达到上限才输出
    3. 否则尊重 Supervisor LLM 决策
    """
    iteration_count = state.get("iteration_count", 0)
    action = state.get("next_action", "recommend_agent")
    completed = state.get("completed_steps", [])
    messages = state.get("agent_messages", [])
    delegation_count = state.get("delegation_count", 0)

    # 0. 委派请求最高优先级（Agent 间直接通信）
    #    但受 MAX_DELEGATIONS 限制
    if delegation_count < MAX_DELEGATIONS:
        pending_search = state.get("pending_request_for_search_agent")
        if pending_search and not state.get("quality_check_passed"):
            logger.info("route_after_supervisor: delegation → search_agent (from recommend_agent)")
            return "search_agent"

        pending_location = state.get("pending_request_for_location_agent")
        if pending_location:
            logger.info("route_after_supervisor: delegation → location_agent")
            return "location_agent"

    # 1. recommend_agent 质量通过 → 结束
    if state.get("quality_check_passed"):
        return "format_response"

    # 2. 达到最大迭代次数 → 强制结束（有结果输出，没结果兜底）
    if iteration_count >= MAX_ITERATIONS:
        if state.get("recommendations"):
            return "format_response"
        if state.get("filtered_pois"):
            return "recommend_agent"
        return "format_response"

    # 3. 委派超限 → 强制输出
    if delegation_count >= MAX_DELEGATIONS:
        logger.warning("route_after_supervisor: MAX_DELEGATIONS reached, forcing output")
        if state.get("recommendations") or state.get("filtered_pois"):
            return "recommend_agent" if state.get("filtered_pois") else "format_response"
        return "format_response"

    # 4. 有推荐但质量未通过 → 尊重 Supervisor 决策
    #    如果 Supervisor 说重搜（search_agent），就重搜
    #    不再无脑"有推荐就输出"
    recommendations = state.get("recommendations", [])
    if recommendations and action == "format_response":
        # Supervisor 主动选择输出，尊重
        return "format_response"

    # 5. 安全保护：supervisor_decision 调用次数过多
    #    注意：completed_steps 是 Annotated[list, add]，跨轮次累积，
    #    所以用 iteration_count（每轮重置）作为主要保护
    if iteration_count > MAX_ITERATIONS + 1:
        logger.warning("route_after_supervisor: too many supervisor calls, forcing end")
        return "recommend_agent" if state.get("filtered_pois") else "format_response"

    # 6. 正常路由：尊重 Supervisor 的 next_action
    valid = {"search_agent", "location_agent", "recommend_agent", "format_response"}
    return action if action in valid else "recommend_agent"