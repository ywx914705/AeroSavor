"""高德 API 客户端：带 Redis 缓存。

文档: https://lbs.amap.com/api/webservice/summary/
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import httpx
from redis.asyncio import Redis

from ..core.logging import get_logger

logger = get_logger(__name__)


class AmapAPIError(Exception):
    def __init__(self, code: str | None, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[Amap {code}] {message}")


class AmapClient:
    BASE_URL = "https://restapi.amap.com/v3"

    def __init__(self, api_key: str, redis: Redis | None = None):
        self.api_key = api_key
        self.redis = redis
        self.http = httpx.AsyncClient(timeout=8.0)

    async def aclose(self) -> None:
        await self.http.aclose()

    # ──────────────────────────────────────────────
    # 内部工具
    # ──────────────────────────────────────────────

    def _cache_key(self, endpoint: str, params: dict) -> str:
        p = {k: v for k, v in params.items() if k != "key"}
        raw = f"{endpoint}:{json.dumps(p, sort_keys=True, ensure_ascii=False)}"
        return f"amap:{hashlib.md5(raw.encode('utf-8')).hexdigest()}"

    async def _get(
        self,
        endpoint: str,
        params: dict,
        cache_ttl: int = 600,
    ) -> dict:
        cache_key = self._cache_key(endpoint, params)

        # 1. 查 Redis
        if self.redis is not None and cache_ttl > 0:
            try:
                cached = await self.redis.get(cache_key)
                if cached:
                    logger.debug("amap cache hit: %s", endpoint)
                    return json.loads(cached)
            except Exception as e:
                logger.warning("redis get failed: %s", e)

        # 2. 调高德
        params = {**params, "key": self.api_key, "output": "JSON"}
        try:
            resp = await self.http.get(f"{self.BASE_URL}{endpoint}", params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise AmapAPIError(code=None, message=f"HTTP error: {e}") from e

        if str(data.get("status")) != "1":
            raise AmapAPIError(
                code=str(data.get("infocode", "")),
                message=str(data.get("info", "高德 API 调用失败")),
            )

        # 3. 写缓存
        if self.redis is not None and cache_ttl > 0:
            try:
                await self.redis.setex(
                    cache_key,
                    cache_ttl,
                    json.dumps(data, ensure_ascii=False),
                )
            except Exception as e:
                logger.warning("redis setex failed: %s", e)

        return data

    # ──────────────────────────────────────────────
    # 搜索类
    # ──────────────────────────────────────────────

    async def search_nearby(
        self,
        location: str,
        keywords: str = "",
        types: str = "050000",
        radius: int = 1000,
        page: int = 1,
        offset: int = 20,
    ) -> list[dict]:
        data = await self._get(
            "/place/around",
            {
                "location": location,
                "keywords": keywords,
                "types": types,
                "radius": radius,
                "extensions": "all",
                "page": page,
                "offset": offset,
                "sortrule": "weight",
            },
        )
        return data.get("pois", []) or []

    async def search_by_text(
        self,
        keywords: str,
        city: str = "",
        types: str = "050000",
        page: int = 1,
    ) -> list[dict]:
        data = await self._get(
            "/place/text",
            {
                "keywords": keywords,
                "city": city,
                "types": types,
                "extensions": "all",
                "page": page,
                "offset": 20,
            },
        )
        return data.get("pois", []) or []

    # ──────────────────────────────────────────────
    # 地理编码
    # ──────────────────────────────────────────────

    async def geocode(self, address: str, city: str = "") -> str | None:
        """地理编码：地址 -> 坐标。

        高德 API 在 city 与地址不匹配时可能返回 30001 错误，
        此时会自动不带 city 参数重试一次。
        """
        try:
            data = await self._get(
                "/geocode/geo",
                {"address": address, "city": city},
                cache_ttl=3600,
            )
            geocodes = data.get("geocodes") or []
            return geocodes[0].get("location") if geocodes else None
        except AmapAPIError as e:
            # city 不匹配导致 30001 错误时，不带 city 重试
            if city and e.code in ("30001", "30002", "30003"):
                logger.info("geocode: city=%r mismatch for %r, retrying without city", city, address)
                data = await self._get(
                    "/geocode/geo",
                    {"address": address},
                    cache_ttl=3600,
                )
                geocodes = data.get("geocodes") or []
                return geocodes[0].get("location") if geocodes else None
            raise

    async def regeocode(self, location: str, radius: int = 100) -> dict:
        data = await self._get(
            "/geocode/regeo",
            {"location": location, "radius": radius, "extensions": "base"},
        )
        return data.get("regeocode", {}) or {}

    async def ip_locate(self, ip: str = "") -> dict:
        data = await self._get(
            "/ip",
            {"ip": ip} if ip else {},
            cache_ttl=1800,
        )
        return {
            "city": data.get("city"),
            "rectangle": data.get("rectangle"),
            "adcode": data.get("adcode"),
        }

    # ──────────────────────────────────────────────
    # 路线规划（不缓存）
    # ──────────────────────────────────────────────

    async def route_walking(self, origin: str, destination: str) -> dict:
        data = await self._get(
            "/direction/walking",
            {"origin": origin, "destination": destination},
            cache_ttl=0,
        )
        paths = (data.get("route") or {}).get("paths") or []
        if not paths:
            return {}
        p = paths[0]
        return {
            "mode": "步行",
            "duration_min": round(int(p.get("duration") or 0) / 60),
            "distance_m": int(p.get("distance") or 0),
        }

    async def route_driving(self, origin: str, destination: str) -> dict:
        data = await self._get(
            "/direction/driving",
            {"origin": origin, "destination": destination, "strategy": 0},
            cache_ttl=0,
        )
        paths = (data.get("route") or {}).get("paths") or []
        if not paths:
            return {}
        p = paths[0]
        return {
            "mode": "驾车",
            "duration_min": round(int(p.get("duration") or 0) / 60),
            "distance_m": int(p.get("distance") or 0),
            "tolls": float(p.get("tolls") or 0),
        }

    async def route_transit(self, origin: str, destination: str, city: str) -> dict:
        data = await self._get(
            "/direction/transit/integrated",
            {
                "origin": origin,
                "destination": destination,
                "city": city,
                "extensions": "base",
            },
            cache_ttl=0,
        )
        transits = (data.get("route") or {}).get("transits") or []
        if not transits:
            return {}
        t = transits[0]
        return {
            "mode": "公交",
            "duration_min": round(int(t.get("duration") or 0) / 60),
            "distance_m": int(t.get("distance") or 0),
            "cost": float((t.get("cost") or {}).get("transit_fee") or 0),
        }

    # ──────────────────────────────────────────────
    # 天气
    # ──────────────────────────────────────────────

    async def get_weather(self, city_code: str) -> dict:
        data = await self._get(
            "/weather/weatherInfo",
            {"city": city_code, "extensions": "base"},
            cache_ttl=1800,
        )
        lives = data.get("lives") or []
        if not lives:
            return {}
        w = lives[0]
        weather_str = w.get("weather", "")
        return {
            "weather": weather_str,
            "temperature": w.get("temperature"),
            "wind": w.get("winddirection"),
            "humidity": w.get("humidity"),
            "is_raining": "雨" in weather_str,
            "city": w.get("city"),
        }


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def haversine_distance(loc1: str, loc2: str) -> int:
    """两点距离（米），输入 'lng,lat'。"""
    try:
        lng1, lat1 = map(float, loc1.split(","))
        lng2, lat2 = map(float, loc2.split(","))
    except (ValueError, AttributeError):
        return 0

    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return int(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


# 城市中心点（兜底）。与 CITY_CODES 保持同步覆盖。
CITY_CENTERS = {
    # 直辖市
    "北京": "116.407526,39.904030",
    "上海": "121.473701,31.230416",
    "天津": "117.200983,39.084158",
    "重庆": "106.504962,29.533155",
    # 华南
    "广州": "113.264499,23.129163",
    "深圳": "114.057868,22.543099",
    "东莞": "113.760731,23.048468",
    "佛山": "113.122717,23.028762",
    "珠海": "113.576726,22.270715",
    "惠州": "114.412599,23.079404",
    "中山": "113.392611,22.517645",
    "汕头": "116.681450,23.354350",
    "湛江": "110.359387,21.270708",
    "南宁": "108.366540,22.817002",
    "桂林": "110.299012,25.274215",
    "柳州": "109.411703,24.325502",
    "北海": "109.119179,21.481254",
    "海口": "110.331661,20.031971",
    "三亚": "109.508268,18.247872",
    # 华东
    "杭州": "120.155070,30.274085",
    "南京": "118.796877,32.060255",
    "苏州": "120.585315,31.298886",
    "无锡": "120.301663,31.574729",
    "宁波": "121.549792,29.868388",
    "温州": "120.672111,28.000575",
    "嘉兴": "120.755486,30.746925",
    "绍兴": "120.580129,30.030094",
    "金华": "119.649589,29.089504",
    "台州": "121.420857,28.656236",
    "常州": "119.974059,31.811894",
    "南通": "120.864753,31.975528",
    "徐州": "117.184813,34.261672",
    "扬州": "119.413022,32.394349",
    "合肥": "117.227239,31.820586",
    "芜湖": "118.433092,31.352536",
    "济南": "117.000923,36.675807",
    "青岛": "120.355173,36.082982",
    "烟台": "121.391282,37.539297",
    "潍坊": "119.107078,36.707250",
    "临沂": "118.356448,35.104620",
    "淄博": "118.054827,36.813126",
    "威海": "122.120019,37.513408",
    "厦门": "118.089425,24.479833",
    "福州": "119.296470,26.074508",
    "泉州": "118.589421,24.908853",
    "南昌": "115.892151,28.676493",
    "九江": "115.992811,29.712034",
    # 华中
    "武汉": "114.305393,30.593099",
    "宜昌": "111.286801,30.691787",
    "襄阳": "112.144288,32.042005",
    "长沙": "112.982279,28.194090",
    "株洲": "113.134149,27.827433",
    "岳阳": "113.129031,29.357237",
    "郑州": "113.624931,34.745819",
    "洛阳": "112.453978,34.619685",
    "开封": "114.341587,34.797239",
    # 西南
    "成都": "104.066301,30.572961",
    "绵阳": "104.681768,31.467550",
    "德阳": "104.398021,31.127991",
    "贵阳": "106.713478,26.578343",
    "遵义": "106.937385,27.725564",
    "昆明": "102.832892,24.880095",
    "大理": "100.225032,25.589436",
    "丽江": "100.233026,26.872108",
    "拉萨": "91.140856,29.645553",
    # 西北
    "西安": "108.940175,34.341568",
    "咸阳": "108.705515,34.329567",
    "兰州": "103.823557,36.058039",
    "西宁": "101.778916,36.623178",
    "银川": "106.230909,38.487193",
    "乌鲁木齐": "87.617733,43.792818",
    # 华北
    "石家庄": "114.502461,38.045474",
    "保定": "115.464606,38.873891",
    "唐山": "118.175393,39.635113",
    "秦皇岛": "119.586579,39.942531",
    "邯郸": "114.490293,36.612453",
    "太原": "112.549248,37.857014",
    "大同": "113.298037,40.076702",
    "呼和浩特": "111.749185,40.842358",
    "包头": "109.840187,40.657449",
    # 东北
    "沈阳": "123.429096,41.796767",
    "大连": "121.618622,38.914590",
    "鞍山": "122.995696,41.110626",
    "抚顺": "123.971189,41.792841",
    "锦州": "121.126946,41.095605",
    "丹东": "124.383084,40.000299",
    "营口": "122.235151,40.666737",
    "阜新": "121.648993,42.011796",
    "辽阳": "123.172303,41.273379",
    "盘锦": "122.069635,41.119816",
    "铁岭": "123.844290,42.299757",
    "朝阳": "120.451290,41.576307",
    "葫芦岛": "120.856944,40.754525",
    "长春": "125.323544,43.817072",
    "吉林": "126.549572,43.837883",
    "哈尔滨": "126.642464,45.756967",
    "齐齐哈尔": "123.953000,47.342078",
    "大庆": "125.103720,46.588428",
}


def get_city_center(city: str) -> str | None:
    """返回城市中心坐标，未知城市返回 None（不再默认北京）。

    需要异步兜底的调用方请使用 resolve_city_center()。
    """
    return CITY_CENTERS.get(city)


# 高德城市编码（adcode）。覆盖范围与 CITY_CENTERS 一致。
CITY_CODES = {
    "北京": "110000",
    "上海": "310000",
    "天津": "120000",
    "重庆": "500000",
    "广州": "440100",
    "深圳": "440300",
    "东莞": "441900",
    "佛山": "440600",
    "珠海": "440400",
    "惠州": "441300",
    "中山": "442000",
    "汕头": "440500",
    "湛江": "440800",
    "南宁": "450100",
    "桂林": "450300",
    "柳州": "450200",
    "北海": "450500",
    "海口": "460100",
    "三亚": "460200",
    "杭州": "330100",
    "南京": "320100",
    "苏州": "320500",
    "无锡": "320200",
    "宁波": "330200",
    "温州": "330300",
    "嘉兴": "330400",
    "绍兴": "330600",
    "金华": "330700",
    "台州": "331000",
    "常州": "320400",
    "南通": "320600",
    "徐州": "320300",
    "扬州": "321000",
    "合肥": "340100",
    "芜湖": "340200",
    "济南": "370100",
    "青岛": "370200",
    "烟台": "370600",
    "潍坊": "370700",
    "临沂": "371300",
    "淄博": "370300",
    "威海": "371000",
    "厦门": "350200",
    "福州": "350100",
    "泉州": "350500",
    "南昌": "360100",
    "九江": "360400",
    "武汉": "420100",
    "宜昌": "420500",
    "襄阳": "420600",
    "长沙": "430100",
    "株洲": "430200",
    "岳阳": "430600",
    "郑州": "410100",
    "洛阳": "410300",
    "开封": "410200",
    "成都": "510100",
    "绵阳": "510700",
    "德阳": "510600",
    "贵阳": "520100",
    "遵义": "520300",
    "昆明": "530100",
    "大理": "532900",
    "丽江": "530700",
    "拉萨": "540100",
    "西安": "610100",
    "咸阳": "610400",
    "兰州": "620100",
    "西宁": "630100",
    "银川": "640100",
    "乌鲁木齐": "650100",
    "石家庄": "130100",
    "保定": "130600",
    "唐山": "130200",
    "秦皇岛": "130300",
    "邯郸": "130400",
    "太原": "140100",
    "大同": "140200",
    "呼和浩特": "150100",
    "包头": "150200",
    "沈阳": "210100",
    "大连": "210200",
    "鞍山": "210300",
    "抚顺": "210400",
    "锦州": "210700",
    "丹东": "210600",
    "营口": "210800",
    "阜新": "210900",
    "辽阳": "211000",
    "盘锦": "211100",
    "铁岭": "211200",
    "朝阳": "211300",
    "葫芦岛": "211400",
    "长春": "220100",
    "吉林": "220200",
    "哈尔滨": "230100",
    "齐齐哈尔": "230200",
    "大庆": "230600",
}


def get_city_code(city: str) -> str | None:
    """返回城市 adcode，未知城市返回 None（不再默认北京 110000）。

    需要兜底的调用方请自行处理 None，例如:
        get_city_code(city) or get_city_code(settings.AMAP_DEFAULT_CITY)
    """
    return CITY_CODES.get(city)


def is_known_city(city: str | None) -> bool:
    """判断字符串是否为本系统已知的城市名（用于 home_city 写入校验）。"""
    if not city:
        return False
    return city in CITY_CODES


def extract_city_name(text: str | None) -> str | None:
    """从可能包含区/县/街道的地点字符串中提取城市名。

    例: "成都武侯" → "成都", "北京朝阳" → "北京", "成都" → "成都"
    用于 home_city 写入时，将 LLM 提取的精确位置降级为城市级别。
    """
    if not text:
        return None
    # 先精确匹配
    if text in CITY_CODES:
        return text
    # 前缀匹配：找最长匹配的城市名（避免 "苏" 匹配到 "苏州" 之类的问题）
    for city in sorted(CITY_CODES.keys(), key=len, reverse=True):
        if text.startswith(city):
            return city
    return None


async def resolve_city_center(city: str, fallback: str | None = None) -> str:
    """异步版城市中心坐标获取：CITY_CENTERS → geocode → fallback。

    当 city 不在 CITY_CENTERS 中时，调用高德 geocode API 动态获取坐标。
    仅在所有方法都失败时才使用 fallback（默认为 settings.DEFAULT_LOCATION）。

    Args:
        city: 城市名（如 "昆山"、"苏州"）
        fallback: 最终兜底坐标，默认使用 settings.DEFAULT_LOCATION
    """
    result = CITY_CENTERS.get(city)
    if result:
        return result

    # 动态 geocode
    try:
        client = get_amap_client()
        geocoded = await client.geocode(city)
        if geocoded:
            logger.info("resolve_city_center: geocode resolved '%s' -> %s", city, geocoded)
            return geocoded
    except Exception as e:
        logger.warning("resolve_city_center: geocode failed for '%s': %s", city, e)

    # 最终兜底
    if fallback:
        return fallback
    from ..core.config import settings
    return settings.DEFAULT_LOCATION


async def resolve_city_from_hint(hint: str, user_city: str = "") -> str | None:
    """从位置提示文本中解析城市名：本地查找 → geocode+regeocode。

    对于不在 CITY_CODES 中的县级市（如"昆山"），通过高德 API 解析：
    1. geocode("昆山") → 获取坐标
    2. regeocode(坐标) → 获取 addressComponent.city（上级地级市，如"苏州"）

    Args:
        hint: 位置提示文本（如 "昆山"、"成都武侯"）
        user_city: 当前已知城市，作为 geocode 的 city 参数辅助定位

    Returns:
        城市名（如 "苏州"），或 None
    """
    # 快速路径：本地字典匹配
    city = extract_city_name(hint)
    if city:
        return city

    # 慢速路径：geocode + regeocode
    try:
        client = get_amap_client()
        location = await client.geocode(hint, user_city)
        if location:
            regeo = await client.regeocode(location)
            comp = regeo.get("addressComponent") or {}
            # 直辖市（北京/上海/天津/重庆）city 字段为空，需用 province
            city_name = comp.get("city") or comp.get("province")
            if city_name:
                # 去掉 "市" 后缀以匹配 CITY_CODES 的 key 格式
                city_name = city_name.rstrip("市")
                if city_name in CITY_CODES:
                    return city_name
                # 即使不在 CITY_CODES 中也返回，供显示使用
                return city_name
    except Exception as e:
        logger.warning("resolve_city_from_hint failed for '%s': %s", hint, e)

    return None


# ──────────────────────────────────────────────
# 全局客户端（懒加载）
# ──────────────────────────────────────────────

_client: AmapClient | None = None


def get_amap_client() -> AmapClient:
    global _client
    if _client is None:
        from ..core.config import settings
        from ..core.redis_client import get_redis

        _client = AmapClient(api_key=settings.AMAP_API_KEY, redis=get_redis())
    return _client


async def close_amap_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
