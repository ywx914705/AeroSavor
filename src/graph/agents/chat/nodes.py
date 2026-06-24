"""ChatAgent 节点：准备闲聊 prompt + 生成回复。

升级：使用 src/core/product_identity.py 的统一身份定义 + 人格 Prompt，
让对话更自然、更有温度，不再被硬编码验证逻辑束缚。
"""
from __future__ import annotations

import asyncio
import random

from ....core.logging import get_logger
from ....core.event_bus import push_event, evt_agent_start, evt_agent_done, evt_agent_degraded
from ....core.product_identity import (
    PRODUCT_IDENTITY,
    GREETING_RESPONSE,
    CAPABILITY_RESPONSE,
    IDENTITY_RESPONSE,
    PERSONALITY_PROMPT,
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

_GREETING_PROMPT = f"""你是 {PRODUCT_IDENTITY['name']}，一个懂吃、有温度的餐厅推荐搭子。

【用户记忆信息】
{{memory_context}}

【最近对话】
{{conversation_history}}

用户说了：'{{user_query}}'

请回应。要求：
1. 先自然地回应问候（如"你好呀"、"嗨～"等），不要像客服
2. 可以简单提一下自己（名字和定位），但不要像产品说明书
3. 自然引导到餐厅话题（如"今天想吃点什么？"），但不要太生硬
4. 3-4 句即可，语气温暖轻松，像一个经常一起觅食的朋友"""

_IDENTITY_PROMPT = f"""你是 {PRODUCT_IDENTITY['name']}，一个懂吃、有温度的餐厅推荐搭子。

【用户记忆信息】
{{memory_context}}

【最近对话】
{{conversation_history}}

用户说了：'{{user_query}}'

请回应。要求：
1. 自然地告诉用户你是谁——名字是 {PRODUCT_IDENTITY['name']}，由{PRODUCT_IDENTITY['developer']}开发，是一款 AI 餐厅推荐应用
2. 用一句话概括你能做什么，不要逐条列举功能
3. 要有个人风格——像朋友介绍自己，不要像产品说明书
4. 2-3 句即可"""

_FEATURE_PROMPT = f"""你是 {PRODUCT_IDENTITY['name']}，一个懂吃、有温度的餐厅推荐搭子。

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
1. 用聊天的方式介绍你能做什么，不要像产品演示
2. 每项功能用 1 句话说清楚，用用户视角（"帮你..."而不是"我们支持..."）
3. 可以加点比喻或例子，让描述更有画面感
4. 结尾自然引导（如"想试试吗？"、"告诉我想吃什么"）"""


# ── 否定句澄清 prompt（用户只说了不想吃什么，没说想吃什么） ──

_NEGATIVE_ONLY_PROMPT = f"""你是 {PRODUCT_IDENTITY['name']}，一个懂吃、有温度的餐厅推荐搭子。

【用户记忆信息】
{{memory_context}}

【最近对话】
{{conversation_history}}

用户说了：'{{user_query}}'

用户明确表达了不想吃什么，但没有说想吃什么。

请回应。要求：
1. 先用轻松的语气回应（"收到！"、"了解了"之类）
2. 记住用户不想吃什么（用聊天的方式确认）
3. 主动给2-3个方向建议，引导用户说出想吃什么
   例如："不想吃火锅的话，那烧烤、日料、东北菜，哪个更对胃口？"
4. 不要推荐餐厅（因为还不知道用户想吃什么）
5. 回复简短（2-3句话），不要长篇大论"""


# ── 硬编码兜底（LLM 否认身份或调用失败时使用） ──
_GREETING_FALLBACKS = [
    "你好！我是 AeroSavor 😊 一个帮你找好吃的 AI 搭子。今天想吃点什么？",
    "嗨～我是 AeroSavor！帮你搜附近好店的 🍽️ 告诉我你想吃啥？",
    "你好呀！我是 AeroSavor，你的 AI 美食推荐搭子～想吃点啥？",
]

_IDENTITY_FALLBACKS = [
    IDENTITY_RESPONSE,
    "我是 AeroSavor，忆往昔开发的餐厅推荐搭子。简单说——告诉我你想吃啥，我帮你找到最合适的店 🍽️",
    "叫我 AeroSavor 就好！忆往昔开发的一款餐厅推荐应用，核心就是帮你在附近找到好吃的～",
]

_FEATURE_FALLBACKS = [
    CAPABILITY_RESPONSE,
    "我可以帮你：\n\n🤖 **AI推荐** — 根据你的口味推荐附近好店\n📊 **真实数据** — 高德地图的评分、价格、距离\n🧠 **偏好学习** — 记住你的口味，越用越准\n🗺️ **路线规划** — 步行/驾车/公交都行\n\n告诉我你想吃什么，我马上帮你搜！",
]

_NEGATIVE_ONLY_FALLBACKS = [
    "收到！不吃火锅，那换个口味？烧烤、日料、东北菜，哪个更对胃口？",
    "了解～那咱换个方向！想吃烧烤还是日料，或者来点东北菜？",
    "没问题！不馋火锅的话，烧烤、串串、韩料，你想往哪个方向走？",
]

# ── LLM 失败时的通用兜底 ──
_FALLBACK_RESPONSES = [
    "嗨～有什么想吃的吗？告诉我，我帮你找 😊",
    "想吃点什么？附近好店我帮你搜～",
    "有什么美食需求尽管说，我帮你安排 🍽️",
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
    """从 state 中构建用户记忆上下文字符串，包含推荐、天气等丰富信息。"""
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

    # 新增：之前推荐的餐厅
    recs = state.get("recommendations") or []
    if recs:
        rec_names = []
        for r in recs[:3]:
            name = r.get("name", "?")
            reason = r.get("reason", "")
            if reason:
                rec_names.append(f"{name}（{reason[:30]}）")
            else:
                rec_names.append(name)
        parts.append(f"之前推荐的餐厅：{'；'.join(rec_names)}")

    # 新增：天气信息
    weather = state.get("weather")
    if weather and isinstance(weather, dict):
        w_text = weather.get("weather", "")
        w_temp = weather.get("temperature", "")
        if w_text or w_temp:
            parts.append(f"当前天气：{w_text} {w_temp}°C")

    # 新增：之前搜索的关键词
    if prev and prev.get("keywords"):
        parts.append(f"之前搜索的关键词：{', '.join(prev['keywords'])}")

    return "\n".join(parts) if parts else "暂无用户信息"


def _build_conversation_history(messages: list, max_messages: int = 10) -> str:
    """从 messages 中构建最近对话历史字符串。

    扩大到 10 条 / 500 字符，让 agent 有足够上下文记忆。
    """
    recent = list(messages[-max_messages:]) if messages else []
    if not recent:
        return "（无历史对话）"
    lines = []
    for m in recent:
        if hasattr(m, "type"):
            role = m.type
            content = str(m.content)[:500]
        elif isinstance(m, dict):
            role = m.get("role", "")
            content = str(m.get("content", ""))[:500]
        else:
            role = ""
            content = str(m)[:500]
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
        "negative_only": _NEGATIVE_ONLY_PROMPT,
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
    """轻量校验 LLM 回复：只检查身份否认，不再强制包含关键词。

    身份由 system prompt (PERSONALITY_PROMPT) 保证，
    不需要通过验证强制在每条回复里插入产品名。
    """
    if not content or len(content) < 3:
        return False
    # 不能否认身份
    deny_patterns = ["不是 AeroSavor", "不是AeroSavor", "我是 MiMo",
                     "我是小米", "我是其他", "并非 AeroSavor",
                     "我是ChatGPT", "我是OpenAI", "我是Claude",
                     "我是GPT", "我是一个语言模型"]
    for pat in deny_patterns:
        if pat in content:
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
    if chat_type == "negative_only":
        return random.choice(_NEGATIVE_ONLY_FALLBACKS)
    return random.choice(_FALLBACK_RESPONSES)


async def generate_chat_node(state: dict) -> dict:
    """调用 LLM 生成闲聊回复。

    chat_type 由 intent_parser 提供，不同类型有不同深度的回答：
    - 问候：简短欢迎 + 引导
    - 身份：名字 + 开发者 + 定位
    - 功能：详细展开四项功能
    - 社交/位置确认/其他闲聊：通用回复

    当 stream_chat_response=True 时（SSE 端点），只准备 prompt 不调 LLM，
    由 SSE 端点自行流式生成。
    """
    session_id = state.get("session_id", "")
    user_query = state.get("user_query", "")
    chat_type = state.get("chat_type") or _classify_chat_type(user_query)

    await push_event(session_id, evt_agent_start("chat_agent", "生成回复..."))

    # SSE 流式模式：只准备 prompt，由端点流式生成
    if state.get("stream_chat_response"):
        await push_event(session_id, evt_agent_done("chat_agent", "准备流式回复..."))
        return {"chat_prompt": state.get("chat_prompt", ""), "final_response": ""}

    chat_prompt = state.get("chat_prompt", "")
    if not chat_prompt:
        await push_event(session_id, evt_agent_degraded("chat_agent", "回复已生成（兜底）", "无有效 prompt"))
        return {"final_response": _get_fallback(chat_type), "chat_prompt": None}

    llm = _get_llm()
    if llm is None:
        await push_event(session_id, evt_agent_degraded("chat_agent", "回复已生成（兜底）", "LLM 不可用"))
        return {"final_response": _get_fallback(chat_type), "chat_prompt": None}

    try:
        result = await asyncio.wait_for(
            llm.ainvoke(
                chat_prompt,
                max_tokens=500,
                system_prompt=PERSONALITY_PROMPT,
            ),
            timeout=20.0,
        )
        content = result.content.strip() if hasattr(result, "content") else str(result).strip()

        if not content:
            await push_event(session_id, evt_agent_degraded("chat_agent", "回复已生成（兜底）", "LLM 返回空"))
            return {"final_response": _get_fallback(chat_type), "chat_prompt": None}

        # 截断修复：末尾缺少标点时补上，不再丢弃整段回复
        if content[-1] not in "。！？.!?～~）)】]":
            last_sent = max(content.rfind("。"), content.rfind("！"), content.rfind("？"),
                            content.rfind("~"), content.rfind("，"))
            if last_sent > len(content) // 2:
                content = content[:last_sent + 1]
            else:
                content = content + "。"

        # 轻量校验：只检查身份否认
        if _validate_response(content, chat_type):
            await push_event(session_id, evt_agent_done("chat_agent", "回复已生成"))
            return {"final_response": content}

        # 校验失败（否认身份）→ 兜底
        logger.info("generate_chat: validation failed for %s. LLM said: %s", chat_type, content[:80])
        await push_event(session_id, evt_agent_degraded("chat_agent", "回复已生成（兜底）", "身份否认校验失败"))
        return {"final_response": _get_fallback(chat_type), "chat_prompt": None}

    except Exception as e:
        logger.warning("generate_chat_node LLM failed: %s (query=%s)", e, user_query[:30])
        await push_event(session_id, evt_agent_degraded("chat_agent", "回复已生成（兜底）", f"LLM 异常: {e}"))
        return {"final_response": _get_fallback(chat_type), "chat_prompt": None}
