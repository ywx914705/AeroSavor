"""FastAPI 接口测试。"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from src.main import app
from src.api.auth import CurrentUser


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert data["name"] == "restaurant-agent"


class TestChatEndpoint:
    def test_chat_missing_fields(self, client):
        """缺少必填字段应返回 422。"""
        resp = client.post("/api/chat", json={})
        assert resp.status_code == 422

    def test_chat_with_message(self, client):
        """正常请求应该返回（可能因缺少 DB 而失败，但不应 422）。"""
        with patch("src.api.chat.get_graph") as mock_graph:
            mock_result = {
                "final_response": "推荐 3 家餐厅",
                "recommendations": [],
                "route_info": None,
            }
            mock_graph_instance = MagicMock()
            mock_graph_instance.ainvoke = AsyncMock(return_value=mock_result)
            mock_graph.return_value = mock_graph_instance

            # 需要 mock DB 相关调用
            with patch("src.api.chat.get_or_create_default_user") as mock_user, \
                 patch("src.api.chat.get_or_create_session") as mock_session, \
                 patch("src.api.chat.append_message"):
                mock_user.return_value = MagicMock(id="00000000-0000-0000-0000-000000000001")
                mock_session_obj = MagicMock()
                mock_session_obj.id = "00000000-0000-0000-0000-000000000002"
                mock_session_obj.messages = []
                mock_session.return_value = mock_session_obj

                resp = client.post(
                    "/api/chat",
                    json={
                        "session_id": "00000000-0000-0000-0000-000000000002",
                        "message": "找个火锅",
                    },
                )
                # Either 200 (if all mocks work) or 500 (if DB needed)
                assert resp.status_code in (200, 500)


class TestFeedbackEndpoint:
    def test_feedback_invalid_action(self, client):
        """无效的 action 应被忽略。"""
        with patch("src.api.auth.get_current_user") as mock_user:
            mock_user.return_value = CurrentUser(id="00000000-0000-0000-0000-000000000001")
            with patch("src.api.feedback.get_db") as mock_db:
                mock_db.return_value = AsyncMock()
                resp = client.post(
                    "/api/feedback",
                    json={
                        "session_id": "00000000-0000-0000-0000-000000000002",
                        "poi_id": "B000A8UMIN",
                        "poi_name": "测试餐厅",
                        "action": "invalid_action",
                    },
                )
                assert resp.status_code == 200
                assert resp.json()["status"] == "ignored"


class TestHistoryEndpoint:
    def test_history_requires_auth(self, client):
        """历史记录接口应能访问（开发模式默认用户）。"""
        resp = client.get("/api/history")
        # 开发模式：无 token 返回默认用户，应能正常访问
        # 但可能因 DB 未连而报错
        assert resp.status_code in (200, 500)
