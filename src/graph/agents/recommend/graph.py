"""RecommendAgent 子图组装 — 含质量检查。

流程：rank → quality_check → (通过) llm_recommend → END
                    ├→ (不通过但有结果) llm_recommend → END（兜底推荐，有总比没有好）
                    └→ (不通过且无结果) END（消息已写入 agent_messages，触发 Supervisor 重搜）
"""
from __future__ import annotations
from langgraph.graph import StateGraph, END
from .state import RecommendState
from .nodes import rank_node, quality_check_node, llm_recommend_node


def _route_after_quality_check(state: dict) -> str:
    """质量检查后的路由：通过/有结果→生成推荐，无结果→END触发重搜"""
    if state.get("quality_check_passed"):
        return "llm_recommend"
    # 即使质量检查不通过，只要有 ranked_pois，仍然生成兜底推荐
    ranked_pois = state.get("ranked_pois") or []
    if ranked_pois:
        return "llm_recommend"
    # 完全没有结果，返回 END 触发 Supervisor 重搜
    return END


def build_recommend_agent():
    g = StateGraph(RecommendState)
    g.add_node("rank", rank_node)
    g.add_node("quality_check", quality_check_node)
    g.add_node("llm_recommend", llm_recommend_node)

    g.set_entry_point("rank")
    g.add_edge("rank", "quality_check")

    # 质量检查后的路由：
    # 通过 → llm_recommend → END
    # 不通过但有结果 → llm_recommend（兜底推荐）→ END
    # 不通过且无结果 → END（触发 Supervisor 重搜）
    g.add_conditional_edges(
        "quality_check",
        _route_after_quality_check,
        {
            "llm_recommend": "llm_recommend",
            END: END,
        },
    )

    g.add_edge("llm_recommend", END)

    return g
