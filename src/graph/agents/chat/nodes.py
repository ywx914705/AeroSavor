"""ChatAgent 节点：准备闲聊 prompt + 生成回复。

升级：使用 src/core/product_identity.py 的统一身份定义，
避免身份信息散落在多处导致不一致。
"""
from __future__ import annotations

import random

from ....core.logging import get_logger
from ....core.event_bus import push_event, evt_agent_start, evt_agent_done
from ....core.product_identity import (
    PRODUCT_IDENTITY,
    GREETING_RESPONSE,
    CAPABILITY_RESPONSE,
    IDENTITY_RESPONSE,
    AEROSAVOR_IDENTITY_SYSTEM_PROMPT,
)
from ....graph.prompts import CHAT_PROMPT

logger = get_logger(__name__)


# ── 身份问题检测模式 ──
_IDENTITY_PATTERNS = [
    "你是谁", "你叫什么", "你是什么", "你是哪", "谁开发的",
    "谁做的", "介绍一下你", "你是干嘛的", "你干什么的",
]

# ── 功能问题检测模式（区别于身份问题，需要详细展开功能） ──
_FEATURE_PATTERNS = [
    "你能做什么", "你有什么功能", "你有什么用",
    "都有哪些功能", "有哪些功能", "你能干嘛",
    "你会什么", "你都能做什么",
]

# ── 问候检测模式 ──
_GREETING_PATTERNS = [
    "你好", "嗨", "hi", "hello", "hey", "在吗",
    "早上好", "中午好", "下午好", "晚上好",
    "早啊", "哈喽",
]


# ── LLM Prompt 模板（用于需要 LLM 灵活回复的场景） ──

_GREETING_PROMPT = f"""你是 {PRODUCT_IDENTITY['name']}，一款 AI 驱动的餐厅推荐应用，由个人开发者{PRODUCT_IDENTITY['developer']}开发。

【用户记忆信息】
{{memory_context}}

【最近对话】
{{conversation_history}}

用户说了：'{{user_query}}'

请回应。要求：
1. 先自然地回应问候（如"你好呀"、"嗨～"等）
2. 介绍你自己：你是 {PRODUCT_IDENTITY['name']}，由个人开发者{PRODUCT_IDENTITY['developer']}开发，是一款 AI 餐厅推荐应用
3. 用1-2句话概括你的核心能力（AI推荐餐厅、实时高德数据、记住口味偏好、路线规划）
4. 自然引导到餐厅推荐话题（如"今天想吃点什么？"）
5. 3-4句即可，语气温暖轻松，不要像产品说明书"""

_IDENTITY_PROMPT = f"""你是 {PRODUCT_IDENTITY['name']}，一款 AI 驱动的餐厅推荐应用，由个人开发者{PRODUCT_IDENTITY['developer']}开发。

【用户记忆信息】
{{memory_context}}

【最近对话】
{{conversation_history}}

用户说了：'{{user_query}}'

请回应。要求：
1. 清楚地告诉用户：你是 {PRODUCT_IDENTITY['name']}，由{PRODUCT_IDENTITY['developer']}开发，是一款 AI 餐厅推荐应用
2. 用一句话概括你能做什么（比如"帮你找到最合口味的餐厅"），不要逐条列举功能
3. 回复要有个人风格——不要像产品说明书，要像一个热情的美食推荐师
4. 2-3 句即可"""

_FEATURE_PROMPT = f"""你是 {PRODUCT_IDENTITY['name']}，一款 AI 驱动的餐厅推荐应用，由个人开发者{PRODUCT_IDENTITY['developer']}开发。

核心功能（四项）：
1. AI 餐厅推荐 — 根据你的口味和需求，智能推荐附近的餐厅
2. 实时数据 — 基于高德地图 API，提供真实的餐厅评分、价格、距离
3. 偏好学习 — 记住你的口味偏好，越用推荐越懂你
4. 路线规划 — 帮你规划到餐厅的步行、驾车、公交路线

【用户记忆信息】
{{memory_context}}

【最近对话】
{{conversation_history}}

用户说了：'{{user_query}}'

请回应。要求：
1. 先说"我可以帮你..."然后逐项介绍四项核心功能
2. 每项功能用 1 句话说清楚，用用户视角（"帮你..."而不是"我们支持..."）
3. 可以加一些生动的比喻或例子，让功能描述更有画面感
4. 结尾自然引导（如"想试试吗？"、"告诉我想吃什么"）"""


# ── 硬编码兜底（LLM 否认身份或调用失败时使用） ──
_GREETING_FALLBACKS = [
    "你好！我是 **AeroSavor**，由个人开发者忆往昔开发的一款 AI 餐厅推荐应用 😊 我能帮你找到附近好吃的、记住你的口味偏好，还能规划到餐厅的路线。今天想吃点什么？",
    "嗨～我是 **AeroSavor**！忆往昔开发的 AI 餐厅推荐助手 🍽️ 基于高德实时数据，越用越懂你的口味。想找什么好吃的？",
    "你好呀！我是 **AeroSavor**，忆往昔开发的餐厅推荐应用。AI 智能推荐 + 真实评分数据 + 路线规划，告诉我你想吃什么，我来帮你找～",
]

_IDENTITY_FALLBACKS = [
    IDENTITY_RESPONSE,
    f"你好～我是 **{PRODUCT_IDENTITY['name']}**，{PRODUCT_IDENTITY['developer']}开发的餐厅推荐助手。简单来说就是——告诉我你想吃什么，我帮你找到最合适的店，评分、价格、路线都给你安排好。",
    f"叫我 **{PRODUCT_IDENTITY['name']}** 就好！我是{PRODUCT_IDENTITY['developer']}开发的一款餐厅推荐应用，核心能力就是帮你在附近找到好吃的——评分、人均、距离、路线，一条龙搞定。",
]

_FEATURE_FALLBACKS = [
    CAPABILITY_RESPONSE,
    f"我可以帮你：\n\n🤖 **AI推荐** — 根据你的口味推荐附近好店\n📊 **真实数据** — 高德地图的评分、价格、距离\n🧠 **偏好学习** — 记住你的口味，越用越准\n🗺️ **路线规划** — 步行/驾车/公交都行\n\n告诉我你想吃什么，我马上帮你搜！",
]

# ── LLM 失败时的通用兜底 ──
_FALLBACK_RESPONSES = [
    "你好！我是 **AeroSavor**，忆往昔开发的 AI 餐厅推荐应用 😊 AI 推荐附近好店 + 真实评分数据 + 路线规划，告诉我你想吃什么？",
    "嗨～我是 **AeroSavor**，忆往昔开发的餐厅推荐助手！基于高德实时数据，越用越懂你的口味。想找点什么好吃的？",
    "你好呀！我是 **AeroSavor**，忆往昔开发的 AI 餐厅推荐应用。告诉我你想吃什么，我马上帮你搜 🍽️",
]


def _is_identity_question(query: str) -> bool:
    """检测是否为身份类问题（你是谁、谁开发的等）。"""
    q = query.strip().lower()
    return any(p in q for p in _IDENTITY_PATTERNS)


def _is_feature_question(query: str) -> bool:
    """检测是否为功能类问题（你能做什么、有什么功能等）。"""
    q = query.strip().lower()
    return any(p in q for p in _FEATURE_PATTERNS)


def _is_greeting(query: str) -> bool:
    """检测是否为问候类消息。"""
    q = query.strip().lower()
    short = q.strip()
    if len(short) <= 6 and any(p in short for p in _GREETING_PATTERNS):
        return True
    return False


def _classify_chat_type(query: str) -> str:
    """将闲聊 query 分为三类：greeting / identity / feature / chat。

    返回: "greeting" | "identity" | "feature" | "chat"
    """
    if _is_greeting(query):
        return "greeting"
    if _is_feature_question(query):
        return "feature"
    if _is_identity_question(query):
        return "identity"
    return "chat"


def _build_memory_context(state: dict) -> str:
    """从 state 中构建用户记忆上下文字符串。"""
    parts = []
    location_hint = state.get("location_hint")
    if location_hint:
        parts.append(f"用户当前提到的位置：{location_hint}")
    home_city = state.get("home_city")
    if home_city:
        parts.append(f"用户的常驻城市：{home_city}")
    pref = state.get("user_preference")
    if pref and pref.get("preference_text"):
        parts.append(f"用户偏好：{pref['preference_text']}")
    prev = state.get("prev_search_context")
    if prev and prev.get("location_hint"):
        parts.append(f"用户之前提到的位置：{prev['location_hint']}")
    if prev and prev.get("preferred"):
        parts.append(f"用户喜欢的菜系：{', '.join(prev['preferred'])}")
    return "\n".join(parts) if parts else "暂无用户信息"


def _build_conversation_history(messages: list, max_messages: int = 4) -> str:
    """从 messages 中构建最近对话历史字符串。"""
    recent = list(messages[-max_messages:]) if messages else []
    if not recent:
        return "（无历史对话）"
    lines = []
    for m in recent:
        if hasattr(m, "type"):
            role = m.type
            content = str(m.content)[:120]
        elif isinstance(m, dict):
            role = m.get("role", "")
            content = str(m.get("content", ""))[:120]
        else:
            role = ""
            content = str(m)[:120]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def prepare_chat_node(state: dict) -> dict:
    """构建闲聊 prompt，存入 chat_prompt 供后续节点使用。

    chat_type 由 intent_parser 提供（greeting/identity/feature/social/location_confirm/chat），
    不同类型使用不同 prompt：
    - 问候 → 简短欢迎 + 引导
    - 身份 → 名字 + 开发者 + 一句话定位
    - 功能 → 详细展开四项功能
    - 其他闲聊 → 通用 CHAT_PROMPT
    """
    user_query = state.get("user_query", "")
    chat_type = state.get("chat_type") or _classify_chat_type(user_query)
    memory_context = _build_memory_context(state)
    conversation_history = _build_conversation_history(state.get("messages", []))

    prompt_map = {
        "greeting": _GREETING_PROMPT,
        "identity": _IDENTITY_PROMPT,
        "feature": _FEATURE_PROMPT,
        "chat": CHAT_PROMPT,
        # 兼容 intent_parser 返回的其他 chat_type
        "social": CHAT_PROMPT,
        "location_confirm": CHAT_PROMPT,
    }

    template = prompt_map.get(chat_type, CHAT_PROMPT)
    chat_prompt = template.format(
        memory_context=memory_context,
        conversation_history=conversation_history,
        user_query=user_query,
    )

    return {"chat_prompt": chat_prompt}


def _get_llm():
    from ....core.llm import get_claude
    return get_claude()


def _validate_response(content: str, chat_type: str) -> bool:
    """校验 LLM 回复是否正确包含 AeroSavor 身份信息。

    问候：必须包含 AeroSavor
    身份/功能：必须包含 AeroSavor + 忆往昔
    功能：还要至少提到 2 项核心功能
    """
    if not content:
        return False
    # 不能否认身份
    deny_patterns = ["不是 AeroSavor", "不是AeroSavor", "我是 MiMo",
                     "我是小米", "我是其他", "并非 AeroSavor"]
    for pat in deny_patterns:
        if pat in content:
            return False

    # 问候：只要包含 AeroSavor 即可
    if chat_type == "greeting":
        return "AeroSavor" in content

    # 身份/功能：必须包含 AeroSavor + 开发者名
    if "AeroSavor" not in content or PRODUCT_IDENTITY["developer"] not in content:
        return False

    # 功能类：还要至少提到 2 项核心功能关键词
    if chat_type == "feature":
        func_keywords = ["推荐", "评分", "价格", "距离", "偏好", "记住",
                         "路线", "规划", "学习", "高德", "数据"]
        count = sum(1 for kw in func_keywords if kw in content)
        if count < 2:
            return False

    return True


def _get_fallback(chat_type: str) -> str:
    """根据问题类型选择合适的硬编码兜底。"""
    if chat_type == "greeting":
        return random.choice(_GREETING_FALLBACKS)
    if chat_type == "feature":
        return random.choice(_FEATURE_FALLBACKS)
    if chat_type == "identity":
        return random.choice(_IDENTITY_FALLBACKS)
    return random.choice(_FALLBACK_RESPONSES)


async def generate_chat_node(state: dict) -> dict:
    """调用 LLM 生成闲聊回复。

    chat_type 由 intent_parser 提供，不同类型有不同深度的回答：
    - 问候：简短欢迎 + 引导
    - 身份：名字 + 开发者 + 定位
    - 功能：详细展开四项功能
    - 社交/位置确认/其他闲聊：通用回复

    后校验确保 AeroSavor 身份不丢失，LLM 否认身份时回退硬编码兜底。
    """
    session_id = state.get("session_id", "")
    user_query = state.get("user_query", "")
    chat_type = state.get("chat_type") or _classify_chat_type(user_query)
    needs_identity = chat_type in ("greeting", "identity", "feature")

    await push_event(session_id, evt_agent_start("chat_agent", "生成回复..."))

    chat_prompt = state.get("chat_prompt", "")
    if not chat_prompt:
        await push_event(session_id, evt_agent_done("chat_agent", "回复已生成"))
        return {"final_response": _get_fallback(chat_type), "chat_prompt": None}

    llm = _get_llm()
    if llm is None:
        await push_event(session_id, evt_agent_done("chat_agent", "回复已生成"))
        return {"final_response": _get_fallback(chat_type), "chat_prompt": None}

    try:
        result = await llm.ainvoke(
            chat_prompt,
            max_tokens=500,
            system_prompt=AEROSAVOR_IDENTITY_SYSTEM_PROMPT,
        )
        content = result.content.strip() if hasattr(result, "content") else str(result).strip()

        if not content:
            return {"final_response": _get_fallback(chat_type), "chat_prompt": None}

        # 截断检测：末尾没有结束标点
        if content[-1] not in "。！？.!?～~）)】]":
            logger.info("generate_chat: truncated (no ending punct): %s", content[:60])
            if needs_identity:
                return {"final_response": _get_fallback(chat_type), "chat_prompt": None}
            last_sent = max(content.rfind("。"), content.rfind("！"), content.rfind("？"), content.rfind("~"))
            if last_sent > len(content) // 2:
                content = content[:last_sent + 1]
            else:
                return {"final_response": _get_fallback(chat_type), "chat_prompt": None}

        # 身份/问候/功能类：校验 AeroSavor 身份
        if needs_identity:
            if _validate_response(content, chat_type):
                await push_event(session_id, evt_agent_done("chat_agent", "回复已生成"))
                return {"final_response": content}
            else:
                logger.info("generate_chat: validation failed for %s. LLM said: %s", chat_type, content[:80])
                await push_event(session_id, evt_agent_done("chat_agent", "回复已生成（兜底）"))
                return {"final_response": _get_fallback(chat_type), "chat_prompt": None}

        # 普通闲聊：宽松校验
        if len(content) > 5:
            await push_event(session_id, evt_agent_done("chat_agent", "回复已生成"))
            return {"final_response": content}
        await push_event(session_id, evt_agent_done("chat_agent", "回复已生成（兜底）"))
        return {"final_response": _get_fallback(chat_type)}

    except Exception as e:
        logger.warning("generate_chat_node LLM failed: %s (query=%s)", e, user_query[:30])
        await push_event(session_id, evt_agent_done("chat_agent", "回复已生成（兜底）"))
        return {"final_response": _get_fallback(chat_type), "chat_prompt": None}
