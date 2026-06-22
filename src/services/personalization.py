"""个性化排序服务。"""
from __future__ import annotations

import math
from typing import Any

from ..core.logging import get_logger
from .preference_service import embed_text

logger = get_logger(__name__)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _distance_score(distance_m: int) -> float:
    if distance_m <= 500:
        return 1.0
    if distance_m <= 1000:
        return 0.8
    if distance_m <= 2000:
        return 0.6
    if distance_m <= 3000:
        return 0.4
    return 0.2


def _price_score(
    cost: int,
    user_price_range: list | None,
    context_max: int | None,
) -> float:
    if cost == 0:
        return 0.6  # 价格未知，中等分

    if context_max and cost > context_max:
        return 0.1

    if user_price_range and len(user_price_range) >= 2:
        lo, hi = user_price_range[0], user_price_range[1]
        if lo <= cost <= hi:
            return 1.0
        if cost < lo:
            return 0.7
        return max(0.1, 1 - (cost - hi) / max(hi, 1))

    return 0.6


async def _preference_match_score(poi: dict, user_pref: dict | None) -> float:
    """POI 与用户偏好的匹配分。"""
    if not user_pref:
        return 0.5

    base = 0.5

    # 1. 向量相似度（如果有）
    user_emb = user_pref.get("embedding")
    if user_emb:
        poi_text = (
            f"{poi.get('name','')} {poi.get('type','')} "
            f"人均{poi.get('cost',0)}元 评分{poi.get('rating',0)} "
            f"{poi.get('open_time','')}"
        )
        poi_emb = await embed_text(poi_text)
        if poi_emb:
            base = cosine_similarity(poi_emb, user_emb)

    # 2. 显式偏好/不喜欢
    poi_type = poi.get("type", "") or ""
    for disliked in user_pref.get("disliked_cuisines") or []:
        if disliked and disliked in poi_type:
            base = max(0.0, base - 0.3)
            break

    for preferred in user_pref.get("preferred_cuisines") or []:
        if preferred and preferred in poi_type:
            base = min(1.0, base + 0.2)
            break

    return base


async def rerank_pois(
    user_id: str,
    pois: list[dict],
    context: dict[str, Any],
    user_preference: dict | None = None,
) -> list[dict]:
    """个性化重排序。

    评分公式: amap*0.25 + pref*0.35 + dist*0.20 + price*0.20
    """
    scored: list[dict] = []
    for poi in pois:
        amap_score = (poi.get("rating", 0) or 0) / 5.0
        dist_score = _distance_score(poi.get("distance", 9999))
        price_score = _price_score(
            poi.get("cost", 0),
            user_preference.get("price_range") if user_preference else None,
            context.get("price_max"),
        )
        pref_score = await _preference_match_score(poi, user_preference)

        final = (
            amap_score * 0.25
            + pref_score * 0.35
            + dist_score * 0.20
            + price_score * 0.20
        )

        scored.append(
            {
                **poi,
                "_score": round(final, 3),
                "_score_breakdown": {
                    "amap": round(amap_score, 2),
                    "preference": round(pref_score, 2),
                    "distance": round(dist_score, 2),
                    "price": round(price_score, 2),
                },
            }
        )

    return sorted(scored, key=lambda x: x["_score"], reverse=True)


def cold_start_rank(pois: list[dict], context: dict[str, Any]) -> list[dict]:
    """新用户冷启动排序：仅基于评分 + 距离 + 价格。"""
    out: list[dict] = []
    for poi in pois:
        amap_score = (poi.get("rating", 0) or 0) / 5.0
        dist_score = _distance_score(poi.get("distance", 9999))
        price_score = _price_score(
            poi.get("cost", 0), None, context.get("price_max")
        )
        score = amap_score * 0.5 + dist_score * 0.3 + price_score * 0.2
        out.append({**poi, "_score": round(score, 3)})

    return sorted(out, key=lambda x: x["_score"], reverse=True)
