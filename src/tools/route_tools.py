"""路线规划工具：步行/驾车并行。"""
from __future__ import annotations

import asyncio

from ..core.logging import get_logger
from .amap_client import get_amap_client

logger = get_logger(__name__)


async def plan_routes(origin: str, destination: str, city: str = "") -> dict:
    """并行计算步行/驾车（公交需城市参数，有城市则并行调用）。"""
    client = get_amap_client()

    walk_task = client.route_walking(origin, destination)
    drive_task = client.route_driving(origin, destination)
    transit_task = client.route_transit(origin, destination, city) if city else None

    if transit_task:
        walk, drive, transit = await asyncio.gather(
            walk_task, drive_task, transit_task, return_exceptions=True
        )
    else:
        walk, drive = await asyncio.gather(
            walk_task, drive_task, return_exceptions=True
        )
        transit = None

    return {
        "walking": walk if isinstance(walk, dict) else None,
        "driving": drive if isinstance(drive, dict) else None,
        "transit": transit if isinstance(transit, dict) else None,
        "nav_url": (
            f"https://uri.amap.com/navigation"
            f"?to={destination}&mode=car&policy=1&src=restaurant-agent"
        ),
    }
