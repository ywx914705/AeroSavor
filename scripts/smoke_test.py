"""端到端联通性测试 - 不依赖 langgraph，仅验证关键外部依赖。

跑这个脚本可以确认：
  1. 高德 Web Key 能搜到真实 POI
  2. 小米 Claude 代理能正常返回（用我写的 ClaudeClient）
  3. 简化版的"搜索 -> LLM 推荐"链路能跑通

用法：python scripts/smoke_test.py
"""
import asyncio
import io
import json
import os
import sys
import pathlib

# Windows 控制台 UTF-8（避免 emoji/中文 GBK 报错）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

import httpx  # noqa: E402


# ──────────── 用我们项目里的 ClaudeClient ────────────
# 不导入 src.core.llm 里的 settings，避免触发整个 settings 加载链
class ClaudeClient:
    def __init__(self, api_key, base_url, model):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.http = httpx.AsyncClient(timeout=30.0)

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    async def ainvoke(self, prompt, max_tokens=2000, temperature=0.3):
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = await self.http.post(
            f"{self.base_url}/v1/messages", headers=self._headers(), json=body
        )
        resp.raise_for_status()
        data = resp.json()
        out = []
        for block in data.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                out.append(block.get("text", ""))
        return "\n".join(out).strip()

    async def aclose(self):
        await self.http.aclose()


# ──────────── 高德搜索 ────────────


async def amap_search_nearby(key, location, keywords):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://restapi.amap.com/v3/place/around",
            params={
                "key": key,
                "location": location,
                "keywords": keywords,
                "types": "050000",
                "radius": 1000,
                "extensions": "all",
                "output": "JSON",
                "offset": 5,
            },
        )
        data = r.json()
        if str(data.get("status")) != "1":
            raise RuntimeError(f"高德报错: {data}")
        return data.get("pois") or []


# ──────────── 主流程 ────────────


async def main():
    amap_key = os.getenv("AMAP_API_KEY")
    claude_key = os.getenv("ANTHROPIC_API_KEY")
    claude_base = os.getenv("ANTHROPIC_BASE_URL")
    claude_model = os.getenv("CLAUDE_MODEL", "mimo-v2.5")

    if not amap_key or not claude_key:
        print("❌ .env 缺少 AMAP_API_KEY 或 ANTHROPIC_API_KEY")
        sys.exit(1)

    print("==" * 30)
    print("📋 配置")
    print(f"  高德 Web Key: {amap_key[:8]}...{amap_key[-4:]}")
    print(f"  Claude 代理:  {claude_base}")
    print(f"  模型:         {claude_model}")
    print("==" * 30)

    # 1. 高德搜索
    print("\n🔍 [步骤 1] 高德搜索：望京 SOHO 周边火锅")
    pois = await amap_search_nearby(amap_key, "116.473168,39.993015", "火锅")
    print(f"   → 返回 {len(pois)} 家")
    simplified = []
    for p in pois[:5]:
        biz = p.get("biz_ext") or {}
        info = {
            "id": p.get("id"),
            "name": p.get("name"),
            "rating": biz.get("rating") or "-",
            "cost": biz.get("cost") or "-",
            "distance": p.get("distance"),
            "address": p.get("address"),
            "type": (p.get("type", "").split(";")[-1] if p.get("type") else ""),
        }
        simplified.append(info)
        print(
            f"   - {info['name']} | ⭐{info['rating']} | "
            f"¥{info['cost']} | {info['distance']}m"
        )

    # 2. Claude 代理 - 简单 ping
    print("\n🤖 [步骤 2] 小米 Claude 代理 ping")
    llm = ClaudeClient(claude_key, claude_base, claude_model)
    text = await llm.ainvoke("请用一个词回答：1+1=?", max_tokens=20)
    print(f"   → 返回: {text[:100]}")

    # 3. 端到端：把高德结果交给 Claude 生成推荐
    print("\n💬 [步骤 3] Claude 基于真实高德数据生成推荐")
    prompt = f"""你是餐厅推荐助手。根据以下真实餐厅数据，挑出 Top 2 并用一两句话给出推荐理由。

候选餐厅:
{json.dumps(simplified, ensure_ascii=False, indent=2)}

只输出 JSON，结构：
{{"recommendations":[{{"name":"...","reason":"..."}}]}}"""
    text = await llm.ainvoke(prompt, max_tokens=600, temperature=0.5)
    print("   → Claude 输出:")
    print("   " + "\n   ".join(text.splitlines()[:20]))

    await llm.aclose()
    print("\n" + "==" * 30)
    print("✅ 端到端链路全部跑通：高德 + 小米 Claude 代理 + 推荐生成")
    print("==" * 30)


if __name__ == "__main__":
    asyncio.run(main())
