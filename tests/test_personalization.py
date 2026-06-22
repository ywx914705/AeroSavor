"""个性化排序单测。"""
from __future__ import annotations

import pytest

from src.services.personalization import (
    cold_start_rank,
    cosine_similarity,
    rerank_pois,
)


def test_cosine_similarity_basic():
    assert cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine_similarity([], [1, 0]) == 0.0


def test_cold_start_prefers_higher_rating_when_close():
    pois = [
        {"id": "a", "rating": 4.8, "cost": 100, "distance": 200},
        {"id": "b", "rating": 3.5, "cost": 100, "distance": 200},
    ]
    out = cold_start_rank(pois, {})
    assert out[0]["id"] == "a"


def test_cold_start_penalizes_over_budget():
    pois = [
        {"id": "expensive", "rating": 4.9, "cost": 500, "distance": 100},
        {"id": "cheap", "rating": 4.2, "cost": 100, "distance": 200},
    ]
    out = cold_start_rank(pois, {"price_max": 150})
    # 超预算的应被压到后面
    assert out[0]["id"] == "cheap"


@pytest.mark.asyncio
async def test_rerank_with_disliked_cuisine():
    """被显式不喜欢的菜系应被惩罚。"""
    pois = [
        {
            "id": "1",
            "name": "辣餐厅",
            "type": "辣椒炒肉",
            "rating": 4.8,
            "cost": 100,
            "distance": 100,
        },
        {
            "id": "2",
            "name": "日料",
            "type": "日本料理",
            "rating": 4.0,
            "cost": 100,
            "distance": 100,
        },
    ]
    pref = {
        "preference_text": "喜欢日料",
        "preferred_cuisines": ["日本料理"],
        "disliked_cuisines": ["辣椒炒肉"],
        "price_range": [80, 200],
        "min_rating": 3.5,
        "preferred_features": [],
        "embedding": None,
    }
    out = await rerank_pois("u1", pois, {}, user_preference=pref)
    assert out[0]["id"] == "2"