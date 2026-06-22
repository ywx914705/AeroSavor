"""高德 API 连通性测试。"""
import asyncio
import io
import os
import sys

import httpx
from dotenv import load_dotenv

# Windows 控制台 UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

load_dotenv()

KEY = os.getenv("AMAP_API_KEY")


async def main():
    if not KEY or KEY == "your_amap_web_service_key":
        print("❌ 请在 .env 中设置 AMAP_API_KEY")
        sys.exit(1)

    async with httpx.AsyncClient(timeout=10) as c:
        # 1. 周边搜索
        r = await c.get(
            "https://restapi.amap.com/v3/place/around",
            params={
                "key": KEY,
                "location": "116.473168,39.993015",
                "keywords": "火锅",
                "types": "050000",
                "radius": 1000,
                "extensions": "all",
                "output": "JSON",
            },
        )
        data = r.json()
        if str(data.get("status")) != "1":
            print(f"❌ 周边搜索失败: {data}")
            sys.exit(1)
        pois = data.get("pois", []) or []
        print(f"✅ 周边搜索: 找到 {len(pois)} 家餐厅")
        for p in pois[:3]:
            biz = p.get("biz_ext") or {}
            print(
                f"   {p.get('name')} | "
                f"评分:{biz.get('rating', 'N/A')} | "
                f"人均:{biz.get('cost', 'N/A')} | "
                f"距离:{p.get('distance', '?')}m"
            )

        # 2. 地理编码
        r2 = await c.get(
            "https://restapi.amap.com/v3/geocode/geo",
            params={"key": KEY, "address": "北京望京SOHO", "output": "JSON"},
        )
        geo = r2.json()
        if geo.get("geocodes"):
            print(f"✅ 地理编码: 望京SOHO → {geo['geocodes'][0]['location']}")
        else:
            print(f"⚠️  地理编码无结果: {geo}")

        # 3. 天气
        r3 = await c.get(
            "https://restapi.amap.com/v3/weather/weatherInfo",
            params={"key": KEY, "city": "110000", "extensions": "base", "output": "JSON"},
        )
        wd = r3.json()
        lives = wd.get("lives") or []
        if lives:
            w = lives[0]
            print(f"✅ 天气: {w.get('weather')} {w.get('temperature')}°C")
        else:
            print(f"⚠️  天气接口无结果: {wd}")

    print("\n🎉 全部通过，可继续后续 Phase。")


if __name__ == "__main__":
    asyncio.run(main())