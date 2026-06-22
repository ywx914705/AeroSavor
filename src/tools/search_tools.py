"""POI 搜索与标准化工具。"""
from __future__ import annotations

import asyncio

from ..core.logging import get_logger
from .amap_client import get_amap_client

logger = get_logger(__name__)


def normalize_poi(raw: dict) -> dict:
    """高德原始 POI → 标准结构。

    防御性处理：biz_ext / photos 等字段可能为 None。
    """
    biz = raw.get("biz_ext") or {}
    type_str = raw.get("type", "") or ""
    type_label = type_str.split(";")[1] if ";" in type_str else type_str

    photos = []
    for p in raw.get("photos") or []:
        url = p.get("url") if isinstance(p, dict) else None
        if url:
            photos.append(url)
        if len(photos) >= 2:
            break

    location = raw.get("location") or ""

    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "address": raw.get("address") or "",
        "location": location,
        "distance": int(float(raw.get("distance") or 0)),
        "tel": raw.get("tel") or "",
        "type": type_label,
        "typecode": raw.get("typecode") or "",
        "rating": float(biz.get("rating") or 0),
        "cost": int(float(biz.get("cost") or 0)),
        "open_time": biz.get("open_time") or "",
        "is_open": True,
        "photos": photos,
        "amap_url": (
            f"https://uri.amap.com/marker?position={location}"
            f"&name={raw.get('name', '')}"
        ),
    }


async def search_restaurants(
    location: str,
    keywords: list[str],
    radius: int = 1000,
    max_price: int = 999,
    min_rating: float = 0.0,
) -> list[dict]:
    """并发搜索多关键词，合并去重，过滤排序。

    Args:
        location: "lng,lat"
        keywords: 关键词列表，如 ["日料","寿司"]
        radius: 半径（米）
        max_price: 人均上限
        min_rating: 评分下限
    """
    client = get_amap_client()

    # 关键词为空时，退化为单次大类搜索
    kws = [kw for kw in keywords if kw and kw.strip()]
    if not kws:
        kws = [""]

    tasks = [
        client.search_nearby(
            location=location,
            keywords=kw,
            radius=radius,
        )
        for kw in kws
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 合并去重
    poi_map: dict[str, dict] = {}
    for r in results:
        if isinstance(r, Exception):
            logger.warning("amap search failed: %s", r)
            continue
        for poi in r:
            poi_id = poi.get("id")
            if poi_id and poi_id not in poi_map:
                poi_map[poi_id] = poi

    # 标准化 + 过滤
    filtered: list[dict] = []
    for poi in poi_map.values():
        n = normalize_poi(poi)
        if not n["name"] or not n["location"]:
            continue
        if n["cost"] > 0 and n["cost"] > max_price:
            continue
        if n["rating"] > 0 and n["rating"] < min_rating:
            continue
        filtered.append(n)

    # 默认按评分降序
    return sorted(filtered, key=lambda x: x.get("rating", 0), reverse=True)
