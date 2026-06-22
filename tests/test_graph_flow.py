"""LangGraph 图流程测试 — 更新到 Multi-Agent 协作架构。

旧的 src.graph.nodes / src.graph.edges 已重构为：
- supervisor.py (intent_parser, format_response, supervisor_decision 等)
- builder.py (图结构，路由函数)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.graph.state import make_initial_state
from src.graph.supervisor import (
    _parse_json_safely, _format_messages, _rule_based_intent,
    route_after_supervisor, _rule_based_supervisor_decision,
)


# ── _parse_json_safely ──

class TestParseJsonSafely:
    def test_plain_json(self):
        result = _parse_json_safely('{"intent": "search", "keywords": ["火锅"]}')
        assert result["intent"] == "search"
        assert result["keywords"] == ["火锅"]

    def test_json_in_code_block(self):
        result = _parse_json_safely('```json\n{"intent": "search"}\n```')
        assert result["intent"] == "search"

    def test_json_with_prefix(self):
        result = _parse_json_safely('Here is the result:\n{"intent": "search"}')
        assert result["intent"] == "search"

    def test_invalid_input(self):
        result = _parse_json_safely("not json at all")
        assert result == {}

    def test_nested_json(self):
        result = _parse_json_safely('{"a": {"b": [1, 2, 3]}}')
        assert result["a"]["b"] == [1, 2, 3]

    def test_empty_string(self):
        result = _parse_json_safely("")
        assert result == {}


# ── _format_messages ──

class TestFormatMessages:
    def test_basic(self):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = _format_messages(msgs)
        assert "user: hello" in result
        assert "assistant: hi there" in result

    def test_empty(self):
        assert _format_messages([]) == ""

    def test_truncation(self):
        msgs = [{"role": "user", "content": "x" * 200}]
        result = _format_messages(msgs)
        # Should be truncated to ~120 chars
        assert len(result.split(": ", 1)[1]) <= 123

    def test_limit(self):
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = _format_messages(msgs, limit=3)
        assert result.count("user:") == 3


# ── _rule_based_intent ──

class TestRuleBasedIntent:
    def test_known_cuisine(self):
        result = _rule_based_intent("找个火锅")
        assert result["intent"] == "search"
        assert "火锅" in result["search_keywords"]

    def test_price_extraction(self):
        result = _rule_based_intent("人均150以内的日料")
        assert result["price_max"] == 150

    def test_unknown_cuisine(self):
        result = _rule_based_intent("随便吃点")
        assert result["intent"] == "search"
        assert len(result["search_keywords"]) > 0


# ── route_after_supervisor (替代旧 after_intent / need_retry / need_route) ──

class TestRouteAfterSupervisor:
    def test_quality_passed_goes_to_format(self):
        result = route_after_supervisor({
            "iteration_count": 1,
            "next_action": "recommend_agent",
            "quality_check_passed": True,
            "filtered_pois": [{"name": "x"}],
        })
        assert result == "format_response"

    def test_max_iteration_with_results(self):
        from src.graph.supervisor import MAX_ITERATIONS
        result = route_after_supervisor({
            "iteration_count": MAX_ITERATIONS + 1,
            "filtered_pois": [{"name": "x"}],
            "next_action": "search_agent",
        })
        assert result == "recommend_agent"

    def test_max_iteration_no_results(self):
        from src.graph.supervisor import MAX_ITERATIONS
        result = route_after_supervisor({
            "iteration_count": MAX_ITERATIONS + 1,
            "filtered_pois": [],
            "next_action": "search_agent",
        })
        assert result == "format_response"

    def test_search_agent_action(self):
        result = route_after_supervisor({
            "iteration_count": 1,
            "next_action": "search_agent",
            "filtered_pois": [],
        })
        assert result == "search_agent"

    def test_invalid_action_defaults_to_recommend(self):
        result = route_after_supervisor({
            "iteration_count": 0,
            "next_action": "invalid_action",
            "filtered_pois": [],
        })
        assert result == "recommend_agent"


# ── make_initial_state ──

class TestMakeInitialState:
    def test_defaults(self):
        state = make_initial_state(
            user_query="test",
            session_id="s1",
            user_id="u1",
        )
        assert state["user_query"] == "test"
        assert state["intent"] == "search"
        assert state["is_new_user"] is True
        assert state["messages"] == []
        # Multi-Agent 协作字段
        assert state["agent_messages"] == []
        assert state["iteration_count"] == 0
        assert state["quality_check_passed"] is False

    def test_with_location(self):
        state = make_initial_state(
            user_query="test",
            session_id="s1",
            user_id="u1",
            user_location="116.473,39.993",
        )
        assert state["user_location"] == "116.473,39.993"
