"""LangGraph nodes 关键工具函数单测 — 更新到 supervisor.py 路径。"""
from __future__ import annotations

from src.graph.supervisor import _parse_json_safely, _format_messages


def test_parse_json_plain():
    assert _parse_json_safely('{"a": 1}') == {"a": 1}


def test_parse_json_with_code_fence():
    text = "```json\n{\"a\": 1}\n```"
    assert _parse_json_safely(text) == {"a": 1}


def test_parse_json_with_prefix():
    text = "好的，结果如下：\n{\"intent\": \"search\"}"
    assert _parse_json_safely(text) == {"intent": "search"}


def test_parse_json_invalid_returns_empty():
    assert _parse_json_safely("not json at all") == {}


def test_format_messages_truncates():
    msgs = [{"role": "user", "content": "x" * 200}]
    s = _format_messages(msgs)
    assert s.startswith("user: ")
    assert len(s) <= 140
