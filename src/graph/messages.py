"""Agent 消息总线 — Multi-Agent 协作的核心通信机制。

各 Agent 通过 agent_messages 发送消息：
- 汇报结果给 Supervisor（result/feedback/error）
- 向其他 Agent 发送请求（request）
- 响应其他 Agent 的请求（response）

消息追加到 SupervisorState.agent_messages（Annotated[list, add]），
自动追加不覆盖，保留完整协作历史。
"""
from __future__ import annotations

from typing import Literal, Optional, TypedDict


class AgentMessage(TypedDict):
    """Agent 间通信消息结构。"""
    from_agent: str          # 发送方：search_agent / recommend_agent / route_agent 等
    to_agent: str            # 接收方：supervisor / search_agent / recommend_agent / broadcast
    message_type: Literal[   # 消息类型
        "result",            # 正常完成，汇报结果
        "feedback",          # 质量反馈，可能需要调整策略
        "request",           # 请求另一个 Agent 执行任务
        "response",          # 响应请求
        "error"              # 遇到错误
    ]
    status: str              # success / low_result / empty_result / quality_poor / pending / accepted / error
    suggestion: Optional[str]  # 建议的下一步：expand_keywords / relocation / accept / retry
    reason: str              # 原因说明（给 Supervisor LLM 看的）
    data: dict               # 附加数据（如结果数量、mismatch 信息等）
    reply_to: Optional[str]  # 所响应的请求标识（request-response 链路）
    priority: str            # high / normal / low — 高优先级消息先处理


def make_result_message(from_agent: str, count: int, avg_rating: float) -> AgentMessage:
    """构造正常结果消息。"""
    return {
        "from_agent": from_agent,
        "to_agent": "supervisor",
        "message_type": "result",
        "status": "success",
        "suggestion": "accept",
        "reason": f"找到 {count} 家餐厅，平均评分 {avg_rating:.1f}",
        "data": {"count": count, "avg_rating": avg_rating},
        "reply_to": None,
        "priority": "normal",
    }


def make_feedback_message(
    from_agent: str,
    status: str,
    suggestion: str,
    reason: str,
    **data: object,
) -> AgentMessage:
    """构造质量反馈消息。

    Args:
        status: empty_result / low_result / quality_poor / error
        suggestion: expand_keywords / relocation / accept / retry
        reason: 给 Supervisor LLM 看的原因说明
        **data: 附加数据（mismatch_type, got_types, user_wants 等）
    """
    return {
        "from_agent": from_agent,
        "to_agent": "supervisor",
        "message_type": "feedback",
        "status": status,
        "suggestion": suggestion,
        "reason": reason,
        "data": data,
        "reply_to": None,
        "priority": "normal",
    }


def make_error_message(from_agent: str, reason: str, **data: object) -> AgentMessage:
    """构造错误消息。"""
    return {
        "from_agent": from_agent,
        "to_agent": "supervisor",
        "message_type": "error",
        "status": "error",
        "suggestion": "retry",
        "reason": reason,
        "data": data,
        "reply_to": None,
        "priority": "normal",
    }


def make_request_message(
    from_agent: str,
    to_agent: str,
    request_type: str,
    reason: str,
    priority: str = "normal",
    **data: object,
) -> AgentMessage:
    """构造 Agent 间请求消息。

    Args:
        from_agent: 发送方
        to_agent: 接收方（非 supervisor）
        request_type: 请求类型（search / evaluate / locate / recall）
        reason: 请求原因
        priority: high / normal / low
        **data: 请求附加数据
    """
    return {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "message_type": "request",
        "status": "pending",
        "suggestion": None,
        "reason": reason,
        "data": {"request_type": request_type, **data},
        "reply_to": None,
        "priority": priority,
    }


def make_response_message(
    from_agent: str,
    to_agent: str,
    reply_to: str,
    status: str,
    reason: str,
    **data: object,
) -> AgentMessage:
    """构造 Agent 间响应消息。

    Args:
        from_agent: 发送方
        to_agent: 接收方
        reply_to: 所响应的请求标识
        status: accepted / rejected / completed
        reason: 响应原因
        **data: 响应附加数据
    """
    return {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "message_type": "response",
        "status": status,
        "suggestion": None,
        "reason": reason,
        "data": data,
        "reply_to": reply_to,
        "priority": "normal",
    }
