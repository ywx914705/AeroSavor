"""MemoryAgent 节点：读取用户偏好。"""
from __future__ import annotations

from ....core.logging import get_logger
from ....core.event_bus import push_event, evt_agent_start, evt_agent_done
from ....services.memory_service import memory_service

logger = get_logger(__name__)


async def read_preference_node(state: dict) -> dict:
    """从数据库读取用户偏好（向量 + 结构化）。"""
    session_id = state.get("session_id", "")
    user_id = state.get("user_id")

    await push_event(session_id, evt_agent_start("memory_agent", "读取偏好..."))

    if not user_id:
        await push_event(session_id, evt_agent_done("memory_agent", "新用户"))
        return {"user_preference": None, "is_new_user": True}

    try:
        pref = await memory_service.get_user_preference(user_id)

        if pref is None:
            await push_event(session_id, evt_agent_done("memory_agent", "新用户"))
            return {"user_preference": None, "is_new_user": True}

        await push_event(session_id, evt_agent_done("memory_agent", "偏好已加载"))
        return {"user_preference": pref, "is_new_user": False}
    except Exception as e:
        logger.warning("read_preference_node failed: %s", e)
        await push_event(session_id, evt_agent_done("memory_agent", "偏好读取失败"))
        return {"user_preference": None, "is_new_user": True}
