"""Multi-Agent 协作系统测试。

覆盖：
1. 消息总线 (messages.py)
2. Supervisor 决策 (supervisor_decision_node + route_after_supervisor)
3. SearchAgent 质量反馈 (filter_node)
4. RecommendAgent 质量检查 (quality_check_node)
5. 产品身份 (product_identity.py)
6. 事件总线 (event_bus.py)
7. 状态初始化 (make_initial_state)
8. 图构建 (builder.py)
"""
import asyncio
import pytest

# ──────────── 1. 消息总线 ────────────

class TestMessages:
    def test_make_result_message(self):
        from src.graph.messages import make_result_message
        msg = make_result_message("search_agent", 5, 4.2)
        assert msg["from_agent"] == "search_agent"
        assert msg["to_agent"] == "supervisor"
        assert msg["message_type"] == "result"
        assert msg["status"] == "success"
        assert msg["suggestion"] == "accept"
        assert msg["data"]["count"] == 5
        assert msg["data"]["avg_rating"] == 4.2

    def test_make_feedback_message(self):
        from src.graph.messages import make_feedback_message
        msg = make_feedback_message(
            "search_agent", "empty_result", "relocation",
            "No results found", tried_radius=2000
        )
        assert msg["from_agent"] == "search_agent"
        assert msg["message_type"] == "feedback"
        assert msg["status"] == "empty_result"
        assert msg["suggestion"] == "relocation"
        assert msg["data"]["tried_radius"] == 2000

    def test_make_error_message(self):
        from src.graph.messages import make_error_message
        msg = make_error_message("search_agent", "API timeout")
        assert msg["message_type"] == "error"
        assert msg["status"] == "error"
        assert msg["suggestion"] == "retry"

    def test_message_accumulation(self):
        """验证 agent_messages 使用 Annotated[list, add] 自动追加。"""
        from operator import add
        existing = [{"from": "a", "status": "s1", "reason": "r1"}]
        new = [{"from": "b", "status": "s2", "reason": "r2"}]
        combined = add(existing, new)
        assert len(combined) == 2
        assert combined[0]["from"] == "a"
        assert combined[1]["from"] == "b"


# ──────────── 2. Supervisor 决策 ────────────

class TestSupervisorDecision:
    def test_rule_empty_result_relocation(self):
        from src.graph.supervisor import _rule_based_supervisor_decision
        result = _rule_based_supervisor_decision({
            "filtered_pois": [], "iteration_count": 0, "agent_messages": []
        })
        assert result == "location_agent"

    def test_rule_low_result_search(self):
        from src.graph.supervisor import _rule_based_supervisor_decision
        result = _rule_based_supervisor_decision({
            "filtered_pois": [{"name": "x"}], "iteration_count": 1, "agent_messages": []
        })
        assert result == "search_agent"

    def test_rule_enough_result_recommend(self):
        from src.graph.supervisor import _rule_based_supervisor_decision
        result = _rule_based_supervisor_decision({
            "filtered_pois": [{"name": str(i)} for i in range(5)],
            "iteration_count": 0, "agent_messages": []
        })
        assert result == "recommend_agent"

    def test_rule_quality_poor_search(self):
        from src.graph.supervisor import _rule_based_supervisor_decision
        result = _rule_based_supervisor_decision({
            "filtered_pois": [{"name": str(i)} for i in range(5)],
            "iteration_count": 1,
            "agent_messages": [{"from_agent": "recommend_agent", "status": "quality_poor", "reason": "bad"}]
        })
        assert result == "search_agent"

    def test_rule_max_iteration_fallback(self):
        from src.graph.supervisor import _rule_based_supervisor_decision, MAX_ITERATIONS
        # 超过最大迭代但无质量差 → 还是可以推荐
        result = _rule_based_supervisor_decision({
            "filtered_pois": [{"name": str(i)} for i in range(3)],
            "iteration_count": MAX_ITERATIONS,
            "agent_messages": []
        })
        assert result == "recommend_agent"

    def test_route_after_supervisor_max_iteration_no_results(self):
        from src.graph.supervisor import route_after_supervisor, MAX_ITERATIONS
        result = route_after_supervisor({
            "iteration_count": MAX_ITERATIONS + 1,
            "filtered_pois": [],
            "next_action": "search_agent"
        })
        assert result == "format_response"

    def test_route_after_supervisor_max_iteration_with_results(self):
        from src.graph.supervisor import route_after_supervisor, MAX_ITERATIONS
        result = route_after_supervisor({
            "iteration_count": MAX_ITERATIONS + 1,
            "filtered_pois": [{"name": "x"}],
            "next_action": "search_agent"
        })
        assert result == "recommend_agent"

    def test_route_after_supervisor_quality_passed(self):
        from src.graph.supervisor import route_after_supervisor
        result = route_after_supervisor({
            "iteration_count": 1,
            "next_action": "recommend_agent",
            "completed_steps": ["recommend_agent"],
            "quality_check_passed": True,
            "filtered_pois": [{"name": "x"}]
        })
        assert result == "format_response"

    def test_route_after_supervisor_invalid_action(self):
        from src.graph.supervisor import route_after_supervisor
        result = route_after_supervisor({
            "iteration_count": 0,
            "next_action": "invalid_action",
            "completed_steps": [],
            "filtered_pois": []
        })
        assert result == "recommend_agent"  # default fallback

    def test_route_after_supervisor_search_agent(self):
        from src.graph.supervisor import route_after_supervisor
        result = route_after_supervisor({
            "iteration_count": 1,
            "next_action": "search_agent",
            "completed_steps": [],
            "filtered_pois": []
        })
        assert result == "search_agent"


# ──────────── 3. SearchAgent 质量反馈 ────────────

class TestSearchFilter:
    def test_empty_result_feedback(self):
        from src.graph.agents.search.nodes import filter_node
        result = filter_node({
            "raw_pois": [], "price_max": 9999,
            "search_keywords": ["日料"], "current_radius": 1000
        })
        assert result["filtered_pois"] == []
        assert len(result["agent_messages"]) == 1
        assert result["agent_messages"][0]["status"] == "empty_result"
        assert result["agent_messages"][0]["suggestion"] == "relocation"

    def test_low_result_feedback(self):
        from src.graph.agents.search.nodes import filter_node
        result = filter_node({
            "raw_pois": [{"name": "店1", "location": "1,1", "rating": 4.0}],
            "price_max": 9999, "search_keywords": ["火锅"]
        })
        assert len(result["filtered_pois"]) == 1
        assert result["agent_messages"][0]["status"] == "low_result"
        assert result["agent_messages"][0]["suggestion"] == "expand_keywords"

    def test_success_feedback(self):
        from src.graph.agents.search.nodes import filter_node
        pois = [{"name": f"店{i}", "location": "1,1", "rating": 4.0 + i*0.1} for i in range(5)]
        result = filter_node({
            "raw_pois": pois, "price_max": 9999, "search_keywords": ["美食"]
        })
        assert len(result["filtered_pois"]) == 5
        assert result["agent_messages"][0]["status"] == "success"
        assert result["agent_messages"][0]["suggestion"] == "accept"

    def test_filter_removes_invalid_pois(self):
        from src.graph.agents.search.nodes import filter_node
        pois = [
            {"name": "有效店", "location": "1,1"},
            {"name": "", "location": "1,1"},  # 无 name
            {"name": "无位置", "location": ""},  # 无 location
            {"name": "完整", "location": "2,2", "rating": 4.5},
        ]
        result = filter_node({"raw_pois": pois, "price_max": 9999, "search_keywords": ["测试"]})
        assert len(result["filtered_pois"]) == 2


# ──────────── 4. RecommendAgent 质量检查 ────────────

class TestQualityCheck:
    @pytest.mark.asyncio
    async def test_empty_pois_quality_fail(self):
        from src.graph.agents.recommend.nodes import quality_check_node
        result = await quality_check_node({
            "ranked_pois": [], "user_query": "火锅", "user_preference": None
        })
        assert result["quality_check_passed"] is False
        assert len(result["agent_messages"]) == 1
        assert result["agent_messages"][0]["status"] == "empty_result"

    @pytest.mark.asyncio
    async def test_quality_check_with_no_llm_few_results(self):
        """无 LLM 时，不足3家默认不通过。"""
        from src.graph.agents.recommend.nodes import quality_check_node
        from unittest.mock import patch

        with patch("src.graph.agents.recommend.nodes._get_llm", return_value=None):
            result = await quality_check_node({
                "ranked_pois": [{"name": "店1", "type": "火锅", "cost": 80, "rating": 4.5}],
                "user_query": "火锅",
                "user_preference": None,
                "iteration_count": 0,
            })
            assert result["quality_check_passed"] is False
            assert len(result["agent_messages"]) == 1

    @pytest.mark.asyncio
    async def test_quality_check_with_no_llm_enough_results(self):
        """无 LLM 时，≥3家默认通过。"""
        from src.graph.agents.recommend.nodes import quality_check_node
        from unittest.mock import patch

        with patch("src.graph.agents.recommend.nodes._get_llm", return_value=None):
            pois = [{"name": f"店{i}", "type": "火锅", "cost": 80, "rating": 4.5} for i in range(3)]
            result = await quality_check_node({
                "ranked_pois": pois,
                "user_query": "火锅",
                "user_preference": None,
                "iteration_count": 0,
            })
            assert result["quality_check_passed"] is True


# ──────────── 5. 产品身份 ────────────

class TestProductIdentity:
    def test_identity_fields(self):
        from src.core.product_identity import PRODUCT_IDENTITY
        assert PRODUCT_IDENTITY["name"] == "AeroSavor"
        assert PRODUCT_IDENTITY["developer"] == "忆往昔"
        assert len(PRODUCT_IDENTITY["capabilities"]) == 4

    def test_system_prompt_contains_identity(self):
        from src.core.product_identity import AEROSAVOR_IDENTITY_SYSTEM_PROMPT
        assert "AeroSavor" in AEROSAVOR_IDENTITY_SYSTEM_PROMPT
        assert "忆往昔" in AEROSAVOR_IDENTITY_SYSTEM_PROMPT

    def test_static_responses_contain_identity(self):
        from src.core.product_identity import GREETING_RESPONSE, CAPABILITY_RESPONSE, IDENTITY_RESPONSE
        assert "AeroSavor" in GREETING_RESPONSE
        assert "AeroSavor" in CAPABILITY_RESPONSE
        assert "AeroSavor" in IDENTITY_RESPONSE
        assert "忆往昔" in IDENTITY_RESPONSE

    def test_prompts_reexport(self):
        """验证 prompts.py 正确重导出 AEROSAVOR_SYSTEM_PROMPT。"""
        from src.graph.prompts import AEROSAVOR_SYSTEM_PROMPT
        assert "AeroSavor" in AEROSAVOR_SYSTEM_PROMPT
        assert "忆往昔" in AEROSAVOR_SYSTEM_PROMPT


# ──────────── 6. 事件总线 ────────────

class TestEventBus:
    @pytest.mark.asyncio
    async def test_push_and_receive(self):
        from src.core.event_bus import push_event, get_queue, evt_agent_start, evt_agent_done
        session_id = "test-push-receive"
        await push_event(session_id, evt_agent_start("search_agent", "Searching..."))
        await push_event(session_id, evt_agent_done("search_agent", "Found 5"))
        q = get_queue(session_id)
        e1 = q.get_nowait()
        e2 = q.get_nowait()
        assert e1["type"] == "agent_start"
        assert e2["type"] == "agent_done"

    @pytest.mark.asyncio
    async def test_empty_session_id_noop(self):
        from src.core.event_bus import push_event, evt_agent_start
        # Should not raise
        await push_event("", evt_agent_start("test", "test"))

    @pytest.mark.asyncio
    async def test_collaboration_event(self):
        from src.core.event_bus import push_event, get_queue, evt_collaboration
        session_id = "test-collab"
        await push_event(session_id, evt_collaboration("supervisor", "Retrying..."))
        q = get_queue(session_id)
        e = q.get_nowait()
        assert e["type"] == "collaboration"
        assert e["from"] == "supervisor"

    @pytest.mark.asyncio
    async def test_supervisor_decision_event(self):
        from src.core.event_bus import push_event, get_queue, evt_supervisor_decision
        session_id = "test-sv"
        await push_event(session_id, evt_supervisor_decision("Low results", "search_agent"))
        q = get_queue(session_id)
        e = q.get_nowait()
        assert e["type"] == "supervisor_decision"
        assert e["reason"] == "Low results"
        assert e["next"] == "search_agent"


# ──────────── 7. 状态初始化 ────────────

class TestMakeInitialState:
    def test_new_collaboration_fields(self):
        from src.graph.state import make_initial_state
        state = make_initial_state(
            user_query="附近好吃的火锅",
            session_id="test-session",
            user_id="test-user",
        )
        assert state["agent_messages"] == []
        assert state["completed_steps"] == []
        assert state["next_action"] is None
        assert state["supervisor_reason"] is None
        assert state["iteration_count"] == 0
        assert state["quality_check_passed"] is False

    def test_existing_fields_unchanged(self):
        from src.graph.state import make_initial_state
        state = make_initial_state(
            user_query="test",
            session_id="s1",
            user_id="u1",
        )
        assert state["intent"] == "search"
        assert state["filtered_pois"] == []
        assert state["recommendations"] == []
        assert state["final_response"] == ""
        assert state["is_new_user"] is True


# ──────────── 8. 图构建 ────────────

class TestGraphBuild:
    def test_main_graph_has_supervisor_decision(self):
        from src.graph.builder import build_main_graph
        g = build_main_graph()
        node_names = list(g.nodes.keys())
        assert "supervisor_decision" in node_names
        assert "intent_parser" in node_names
        assert "search_agent" in node_names
        assert "recommend_agent" in node_names
        assert "chat_agent" in node_names
        assert "format_response" in node_names

    def test_recommend_agent_has_quality_check(self):
        from src.graph.agents.recommend.graph import build_recommend_agent
        g = build_recommend_agent()
        node_names = list(g.nodes.keys())
        assert "quality_check" in node_names
        assert "rank" in node_names
        assert "llm_recommend" in node_names

    def test_search_agent_has_filter(self):
        from src.graph.agents.search.graph import build_search_agent
        g = build_search_agent()
        node_names = list(g.nodes.keys())
        assert "filter" in node_names
        assert "search" in node_names

    def test_search_state_has_agent_messages(self):
        from src.graph.agents.search.state import SearchState
        # Verify agent_messages field exists
        annotations = SearchState.__annotations__
        assert "agent_messages" in annotations

    def test_recommend_state_has_collaboration_fields(self):
        from src.graph.agents.recommend.state import RecommendState
        annotations = RecommendState.__annotations__
        assert "quality_check_passed" in annotations
        assert "agent_messages" in annotations

    def test_supervisor_state_has_collaboration_fields(self):
        from src.graph.state import SupervisorState
        annotations = SupervisorState.__annotations__
        assert "agent_messages" in annotations
        assert "completed_steps" in annotations
        assert "next_action" in annotations
        assert "supervisor_reason" in annotations
        assert "iteration_count" in annotations
        assert "quality_check_passed" in annotations


# ──────────── 9. ChatAgent 身份 ────────────

class TestChatIdentity:
    def test_chat_node_imports_from_product_identity(self):
        """验证 ChatAgent 使用统一身份模块。"""
        from src.graph.agents.chat.nodes import (
            _GREETING_PROMPT, _IDENTITY_PROMPT, _FEATURE_PROMPT,
            GREETING_RESPONSE as CHAT_GREETING,
        )
        # 确认 prompt 包含产品名
        assert "AeroSavor" in _GREETING_PROMPT
        assert "AeroSavor" in _IDENTITY_PROMPT
        assert "AeroSavor" in _FEATURE_PROMPT

    def test_classify_chat_type(self):
        from src.graph.agents.chat.nodes import _classify_chat_type
        assert _classify_chat_type("你好") == "greeting"
        assert _classify_chat_type("你是谁") == "identity"
        assert _classify_chat_type("你有什么功能") == "feature"
        assert _classify_chat_type("今天天气不错") == "chat"

    def test_validate_response_checks_identity(self):
        from src.graph.agents.chat.nodes import _validate_response
        # 正确身份
        assert _validate_response("你好！我是 AeroSavor，由忆往昔开发", "identity") is True
        # 缺少开发者名
        assert _validate_response("我是 AeroSavor", "identity") is False
        # 否认身份
        assert _validate_response("我不是 AeroSavor", "greeting") is False


# ──────────── 10. 跨轮次状态重置 ────────────

class TestIntentParserReset:
    """验证 intent_parser_node 重置 Multi-Agent 协作字段，防止跨轮次泄漏。"""

    def test_intent_parser_resets_quality_check_passed(self):
        """BUG 9 修复：quality_check_passed 应在新查询时重置为 False。"""
        from src.graph.supervisor import intent_parser_node
        # 模拟上一轮 quality_check_passed=True 的状态
        # intent_parser_node 是 async 的，需要用 asyncio.run
        import asyncio
        result = asyncio.run(intent_parser_node({
            "user_query": "找个火锅",
            "session_id": "test-reset",
            "messages": [],
            "prev_search_context": None,
            "quality_check_passed": True,  # 上一轮残留
            "iteration_count": 3,          # 上一轮残留
            "delegation_count": 2,         # 上一轮残留
        }))
        assert result.get("quality_check_passed") is False, \
            "quality_check_passed 应在新查询时重置为 False"

    def test_intent_parser_resets_iteration_count(self):
        """BUG 11 修复：iteration_count 应在新查询时重置为 0。"""
        from src.graph.supervisor import intent_parser_node
        import asyncio
        result = asyncio.run(intent_parser_node({
            "user_query": "找个火锅",
            "session_id": "test-reset",
            "messages": [],
            "prev_search_context": None,
            "iteration_count": 3,
        }))
        assert result.get("iteration_count") == 0, \
            "iteration_count 应在新查询时重置为 0"

    def test_intent_parser_resets_delegation_count(self):
        """BUG 10 修复：delegation_count 应在新查询时重置为 0。"""
        from src.graph.supervisor import intent_parser_node
        import asyncio
        result = asyncio.run(intent_parser_node({
            "user_query": "找个火锅",
            "session_id": "test-reset",
            "messages": [],
            "prev_search_context": None,
            "delegation_count": 2,
        }))
        assert result.get("delegation_count") == 0, \
            "delegation_count 应在新查询时重置为 0"

    def test_intent_parser_resets_pending_requests(self):
        """pending_request 字段应在新查询时清空。"""
        from src.graph.supervisor import intent_parser_node
        import asyncio
        result = asyncio.run(intent_parser_node({
            "user_query": "找个火锅",
            "session_id": "test-reset",
            "messages": [],
            "prev_search_context": None,
            "pending_request_for_search_agent": {"some": "request"},
            "pending_request_for_location_agent": {"some": "request"},
        }))
        assert result.get("pending_request_for_search_agent") is None
        assert result.get("pending_request_for_location_agent") is None


# ──────────── 11. SearchAgent filter_node suggestion 修复 ────────────

class TestSearchFilterSuggestion:
    """验证 filter_node 对低结果数量的 suggestion 正确。"""

    def test_low_result_suggests_expand_keywords(self):
        """BUG 修复：1-2家结果时应建议 expand_keywords 而非 accept。"""
        from src.graph.agents.search.nodes import filter_node
        result = filter_node({
            "raw_pois": [{"name": "店1", "location": "1,1", "rating": 4.0}],
            "price_max": 9999,
            "search_keywords": ["火锅"]
        })
        assert result["agent_messages"][0]["status"] == "low_result"
        assert result["agent_messages"][0]["suggestion"] == "expand_keywords"

    def test_two_results_suggests_expand_keywords(self):
        from src.graph.agents.search.nodes import filter_node
        result = filter_node({
            "raw_pois": [
                {"name": "店1", "location": "1,1", "rating": 4.0},
                {"name": "店2", "location": "2,2", "rating": 3.8},
            ],
            "price_max": 9999,
            "search_keywords": ["火锅"]
        })
        assert result["agent_messages"][0]["status"] == "low_result"
        assert result["agent_messages"][0]["suggestion"] == "expand_keywords"


# ──────────── 12. _build_search_strategy 通用不匹配处理 ────────────

class TestBuildSearchStrategy:
    """验证 _build_search_strategy 处理所有 mismatch 类型。"""

    def test_general_mismatch_returns_strategy(self):
        """BUG 13 修复：general mismatch 应返回策略而非 None。"""
        from src.graph.supervisor import _build_search_strategy
        messages = [{
            "from_agent": "recommend_agent",
            "message_type": "feedback",
            "status": "quality_poor",
            "reason": "结果与用户需求不匹配",
            "data": {"mismatch_type": "general", "got_types": "", "user_wants": "火锅"},
        }]
        strategy = _build_search_strategy(messages, {"next_action": "search_agent"})
        assert strategy is not None
        assert strategy.get("mismatch_type") == "general"
        assert strategy.get("reason") is not None

    def test_empty_mismatch_returns_strategy(self):
        from src.graph.supervisor import _build_search_strategy
        messages = [{
            "from_agent": "recommend_agent",
            "message_type": "feedback",
            "status": "empty_result",
            "reason": "推荐列表为空",
            "data": {"mismatch_type": "empty"},
        }]
        strategy = _build_search_strategy(messages, {"next_action": "search_agent"})
        assert strategy is not None
        assert strategy.get("mismatch_type") == "empty"

    def test_cuisine_mismatch_with_avoid_types(self):
        from src.graph.supervisor import _build_search_strategy
        messages = [{
            "from_agent": "recommend_agent",
            "message_type": "feedback",
            "status": "quality_poor",
            "reason": "菜系不匹配",
            "data": {
                "mismatch_type": "cuisine_mismatch",
                "got_types": "快餐, 小吃",
                "prefer_types": ["日料", "寿司"],
            },
        }]
        strategy = _build_search_strategy(messages, {})
        assert strategy is not None
        assert strategy["avoid_types"] == ["快餐", "小吃"]
        assert strategy["prefer_types"] == ["日料", "寿司"]


# ──────────── 13. route_after_supervisor 安全守卫 ────────────

class TestRouteAfterSupervisorSafety:
    """验证 route_after_supervisor 使用 iteration_count 而非 completed_steps。"""

    def test_uses_iteration_count_not_completed_steps(self):
        """BUG 2 修复：安全守卫应基于 iteration_count 而非 completed_steps。"""
        from src.graph.supervisor import route_after_supervisor, MAX_ITERATIONS
        # completed_steps 有大量历史记录（跨轮次累积），但 iteration_count 已重置
        result = route_after_supervisor({
            "iteration_count": 1,  # 新轮次，iteration_count 正常
            "next_action": "search_agent",
            "completed_steps": ["supervisor_decision"] * 10,  # 跨轮次累积
            "filtered_pois": [{"name": "x"}],
        })
        # 应该正常路由到 search_agent，而不是被 completed_steps 守卫拦截
        assert result == "search_agent"
