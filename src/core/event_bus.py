"""协作状态事件总线 — SSE 实时推送 Agent 执行状态。

让用户在等待时看到 Agent 协作的思考过程，
这是"高级智能体"观感的核心体验。

使用内存字典存各会话的事件队列，轻量无外部依赖。
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

# 用内存字典存各会话的事件队列
_queues: dict[str, asyncio.Queue] = {}


def get_queue(session_id: str) -> asyncio.Queue:
    """获取或创建指定会话的事件队列。"""
    if session_id not in _queues:
        _queues[session_id] = asyncio.Queue()
    return _queues[session_id]


def cleanup_queue(session_id: str) -> None:
    """清理指定会话的事件队列。"""
    _queues.pop(session_id, None)


async def push_event(session_id: str, event: dict) -> None:
    """向指定会话推送一个事件。"""
    if not session_id:
        return
    queue = get_queue(session_id)
    await queue.put(event)


async def stream_events(session_id: str) -> AsyncGenerator[str, None]:
    """SSE 生成器，前端连接后持续接收事件。"""
    queue = get_queue(session_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "done":
                    break
            except asyncio.TimeoutError:
                yield "data: {\"type\": \"heartbeat\"}\n\n"
    finally:
        cleanup_queue(session_id)


# ── 标准事件构造函数 ──

def evt_agent_start(agent: str, message: str) -> dict:
    """Agent 开始执行。"""
    return {"type": "agent_start", "agent": agent, "message": message}


def evt_agent_done(agent: str, message: str) -> dict:
    """Agent 执行完成。"""
    return {"type": "agent_done", "agent": agent, "message": message}


def evt_collaboration(from_agent: str, message: str) -> dict:
    """Agent 间协作事件（如 Supervisor 决策重搜）。"""
    return {"type": "collaboration", "from": from_agent, "message": message}


def evt_supervisor_decision(reason: str, next_action: str) -> dict:
    """Supervisor 决策事件。"""
    return {"type": "supervisor_decision", "reason": reason, "next": next_action}


def evt_quality_retry(reason: str, new_strategy: str) -> dict:
    """质量不满足，基于反馈重新搜索。"""
    return {"type": "quality_retry", "reason": reason, "new_strategy": new_strategy}


def evt_agent_message(from_agent: str, to_agent: str, message: str) -> dict:
    """Agent 间直接通信事件。"""
    return {"type": "agent_message", "from": from_agent, "to": to_agent, "message": message}


def evt_delegation(from_agent: str, to_agent: str, task: str) -> dict:
    """Agent 委派任务给另一个 Agent。"""
    return {"type": "delegation", "from": from_agent, "to": to_agent, "task": task}


def evt_recommendations(data: list) -> dict:
    """推荐结果事件。"""
    return {"type": "recommendations", "data": data}


def evt_done() -> dict:
    """流程结束事件。"""
    return {"type": "done"}
