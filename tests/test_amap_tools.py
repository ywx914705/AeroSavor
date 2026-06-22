"""高德工具单测：Redis 缓存命中、POI 标准化。"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.tools.amap_client import AmapClient, haversine_distance
from src.tools.search_tools import normalize_poi


def test_normalize_poi_handles_none_biz_ext():
    raw = {
        "id": "B0001",
        "name": "测试餐厅",
        "address": "测试路 1 号",
        "location": "116.4,39.9",
        "type": "餐饮服务;火锅店",
        "typecode": "050900",
        "distance": "200",
        "biz_ext": None,
        "photos": None,
    }
    n = normalize_poi(raw)
    assert n["id"] == "B0001"
    assert n["name"] == "测试餐厅"
    assert n["rating"] == 0.0
    assert n["cost"] == 0
    assert n["type"] == "火锅店"
    assert n["distance"] == 200


def test_haversine_distance():
    # 望京 SOHO → 国贸约 11km
    d = haversine_distance("116.473168,39.993015", "116.460,39.908")
    assert 9_000 < d < 13_000

    # 同点
    assert haversine_distance("116.4,39.9", "116.4,39.9") == 0


@pytest.mark.asyncio
async def test_amap_cache_hit():
    """命中缓存时不应该调高德 HTTP 接口。"""
    redis = AsyncMock()
    import json as _json

    redis.get.return_value = _json.dumps(
        {"status": "1", "pois": [{"id": "1", "name": "缓存的店"}]}
    )

    client = AmapClient(api_key="x", redis=redis)
    with patch.object(client.http, "get") as http_get:
        result = await client.search_nearby("116.4,39.9", "火锅")

    assert len(result) == 1
    assert result[0]["name"] == "缓存的店"
    http_get.assert_not_called()
    await client.aclose()


@pytest.mark.asyncio
async def test_amap_cache_miss_writes_cache():
    redis = AsyncMock()
    redis.get.return_value = None

    client = AmapClient(api_key="x", redis=redis)
    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "status": "1",
        "pois": [{"id": "1", "name": "新店"}],
    }
    fake_resp.raise_for_status.return_value = None

    with patch.object(client.http, "get", new=AsyncMock(return_value=fake_resp)):
        result = await client.search_nearby("116.4,39.9", "火锅")

    assert len(result) == 1
    redis.setex.assert_called_once()
    await client.aclose()