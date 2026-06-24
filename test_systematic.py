"""系统性全量测试 - AeroSavor 产品测试"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import json
import time
import httpx
import uuid

BASE = "http://localhost:8000"
PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"

results = {"pass": 0, "fail": 0, "warn": 0, "details": []}

def record(status, name, detail=""):
    results[status] += 1
    results["details"].append({"status": status, "name": name, "detail": detail})
    print(f"  {status} {name}" + (f" - {detail}" if detail else ""))

async def call_chat(query, session_id=None, stream=False):
    sid = session_id or str(uuid.uuid4())
    url = f"{BASE}/api/chat/stream" if stream else f"{BASE}/api/chat"
    payload = {"message": query, "session_id": sid}
    async with httpx.AsyncClient(timeout=120.0) as client:
        if stream:
            async with client.stream("POST", url, json=payload) as resp:
                events = []
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            events.append(json.loads(line[6:]))
                        except:
                            pass
                return events, sid
        else:
            resp = await client.post(url, json=payload)
            return resp.json(), sid

async def test_health():
    """1. 健康检查"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{BASE}/health")
        if r.status_code == 200:
            record("pass", "Health check")
        else:
            record("fail", "Health check", f"status={r.status_code}")

async def test_chat_greeting():
    """2. 问候类 - 你好"""
    try:
        data, sid = await call_chat("你好")
        resp = data.get("response", "") or data.get("final_response", "")
        if resp and len(resp) > 3:
            record("pass", "Chat greeting", f"response={resp[:50]}")
        else:
            record("fail", "Chat greeting", f"empty response: {json.dumps(data, ensure_ascii=False)[:200]}")
    except Exception as e:
        record("fail", "Chat greeting", str(e)[:100])

async def test_chat_identity():
    """3. 身份类 - 你是谁"""
    try:
        data, sid = await call_chat("你是谁")
        resp = data.get("response", "") or data.get("final_response", "")
        if "AeroSavor" in resp or "aerosavor" in resp.lower():
            record("pass", "Chat identity", "contains AeroSavor")
        else:
            record("fail", "Chat identity", f"missing AeroSavor: {resp[:80]}")
    except Exception as e:
        record("fail", "Chat identity", str(e)[:100])

async def test_chat_feature():
    """4. 功能类 - 你能做什么"""
    try:
        data, sid = await call_chat("你能做什么")
        resp = data.get("response", "") or data.get("final_response", "")
        if resp and len(resp) > 10:
            record("pass", "Chat feature", f"len={len(resp)}")
        else:
            record("fail", "Chat feature", f"too short: {resp[:80]}")
    except Exception as e:
        record("fail", "Chat feature", str(e)[:100])

async def test_chat_social():
    """5. 社交类 - 谢谢"""
    try:
        data, sid = await call_chat("谢谢")
        resp = data.get("response", "") or data.get("final_response", "")
        if resp and len(resp) > 3:
            record("pass", "Chat social", f"response={resp[:50]}")
        else:
            record("warn", "Chat social", f"short response: {resp[:80]}")
    except Exception as e:
        record("fail", "Chat social", str(e)[:100])

async def test_search_nearby():
    """6. 搜索类 - 附近有什么好吃的"""
    try:
        data, sid = await call_chat("附近有什么好吃的")
        recs = data.get("recommendations", [])
        resp = data.get("response", "") or data.get("final_response", "")
        if recs and len(recs) > 0:
            record("pass", "Search nearby", f"got {len(recs)} recommendations")
        elif resp and len(resp) > 10:
            record("warn", "Search nearby", f"no recs but has response: {resp[:80]}")
        else:
            record("fail", "Search nearby", f"no recs, no response: {json.dumps(data, ensure_ascii=False)[:200]}")
    except Exception as e:
        record("fail", "Search nearby", str(e)[:100])

async def test_search_cuisine():
    """7. 搜索类 - 推荐火锅"""
    try:
        data, sid = await call_chat("推荐火锅")
        recs = data.get("recommendations", [])
        resp = data.get("response", "") or data.get("final_response", "")
        if recs and len(recs) > 0:
            record("pass", "Search cuisine", f"got {len(recs)} recommendations")
        elif resp and len(resp) > 10:
            record("warn", "Search cuisine", f"no recs but has response: {resp[:80]}")
        else:
            record("fail", "Search cuisine", "no recs, no response")
    except Exception as e:
        record("fail", "Search cuisine", str(e)[:100])

async def test_negative_only():
    """8. 否定句 - 不想吃火锅"""
    try:
        data, sid = await call_chat("不想吃火锅")
        resp = data.get("response", "") or data.get("final_response", "")
        recs = data.get("recommendations", [])
        # 否定句应该引导用户，而不是直接推荐
        if resp and len(resp) > 5 and not recs:
            record("pass", "Negative only", f"clarified without recs: {resp[:50]}")
        elif resp and len(resp) > 5:
            record("warn", "Negative only", f"has recs (should clarify): {resp[:50]}")
        else:
            record("fail", "Negative only", "empty response")
    except Exception as e:
        record("fail", "Negative only", str(e)[:100])

async def test_negative_affirmative():
    """9. 否定+肯定 - 不想吃火锅，推荐烧烤"""
    try:
        data, sid = await call_chat("不想吃火锅，推荐烧烤")
        recs = data.get("recommendations", [])
        resp = data.get("response", "") or data.get("final_response", "")
        if recs and len(recs) > 0:
            record("pass", "Negative+affirmative", f"got {len(recs)} recommendations")
        elif resp and len(resp) > 10:
            record("warn", "Negative+affirmative", "no recs but has response")
        else:
            record("fail", "Negative+affirmative", "no recs, no response")
    except Exception as e:
        record("fail", "Negative+affirmative", str(e)[:100])

async def test_stream_sse():
    """10. SSE 流式 - 附近美食"""
    try:
        events, sid = await call_chat("附近美食", stream=True)
        event_types = [e.get("type", "") for e in events]
        has_recommendations = any(e.get("type") == "recommendations" for e in events)
        has_response = any(e.get("type") == "response" for e in events)
        has_agent_start = any("agent_start" in e.get("type", "") for e in events)
        if has_recommendations or has_response:
            record("pass", "SSE stream", f"events={len(events)}, types={set(event_types)}")
        elif has_agent_start:
            record("warn", "SSE stream", f"agent started but no final output, types={set(event_types)}")
        else:
            record("fail", "SSE stream", f"no meaningful events, types={set(event_types)}")
    except Exception as e:
        record("fail", "SSE stream", str(e)[:100])

async def test_session_persistence():
    """11. 会话持久化 - 同一 session 多轮"""
    try:
        sid = str(uuid.uuid4())
        # 第一轮
        data1, _ = await call_chat("你好", session_id=sid)
        # 第二轮
        data2, _ = await call_chat("推荐日料", session_id=sid)
        resp2 = data2.get("response", "") or data2.get("final_response", "")
        recs2 = data2.get("recommendations", [])
        if recs2 or (resp2 and len(resp2) > 10):
            record("pass", "Session persistence", f"2nd turn works, recs={len(recs2)}")
        else:
            record("fail", "Session persistence", "2nd turn empty")
    except Exception as e:
        record("fail", "Session persistence", str(e)[:100])

async def test_invalid_session():
    """12. 无效 session_id"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{BASE}/api/chat", json={"message": "你好", "session_id": "invalid-not-uuid"})
            if r.status_code in (400, 422):
                record("pass", "Invalid session rejected", f"status={r.status_code}")
            else:
                record("warn", "Invalid session rejected", f"status={r.status_code}, should be 400/422")
    except Exception as e:
        record("fail", "Invalid session rejected", str(e)[:100])

async def test_empty_message():
    """13. 空消息"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{BASE}/api/chat", json={"message": "", "session_id": str(uuid.uuid4())})
            if r.status_code in (400, 422):
                record("pass", "Empty message rejected", f"status={r.status_code}")
            else:
                record("warn", "Empty message rejected", f"status={r.status_code}")
    except Exception as e:
        record("fail", "Empty message rejected", str(e)[:100])

async def test_route_query():
    """14. 路线规划 - 怎么去最近的火锅店"""
    try:
        data, sid = await call_chat("怎么去最近的火锅店")
        resp = data.get("response", "") or data.get("final_response", "")
        if resp and len(resp) > 10:
            record("pass", "Route query", f"response={resp[:50]}")
        else:
            record("warn", "Route query", f"short response: {resp[:80]}")
    except Exception as e:
        record("fail", "Route query", str(e)[:100])

async def test_clarify_query():
    """15. 澄清类 - 有没有便宜点的"""
    try:
        data, sid = await call_chat("有没有便宜点的")
        resp = data.get("response", "") or data.get("final_response", "")
        if resp and len(resp) > 5:
            record("pass", "Clarify query", f"response={resp[:50]}")
        else:
            record("fail", "Clarify query", "empty response")
    except Exception as e:
        record("fail", "Clarify query", str(e)[:100])

async def main():
    print("=" * 60)
    print("AeroSavor Systematic Test Suite")
    print("=" * 60)

    tests = [
        ("Infrastructure", [test_health]),
        ("Chat/Intent", [
            test_chat_greeting,
            test_chat_identity,
            test_chat_feature,
            test_chat_social,
        ]),
        ("Search/Recommend", [
            test_search_nearby,
            test_search_cuisine,
        ]),
        ("Negative Sentences", [
            test_negative_only,
            test_negative_affirmative,
        ]),
        ("SSE/Session", [
            test_stream_sse,
            test_session_persistence,
        ]),
        ("Edge Cases", [
            test_invalid_session,
            test_empty_message,
        ]),
        ("Route/Clarify", [
            test_route_query,
            test_clarify_query,
        ]),
    ]

    for category, test_list in tests:
        print(f"\n--- {category} ---")
        for test in test_list:
            t0 = time.monotonic()
            try:
                await test()
            except Exception as e:
                record("fail", test.__doc__, str(e)[:100])
            elapsed = time.monotonic() - t0
            print(f"    ({elapsed:.1f}s)")

    print("\n" + "=" * 60)
    print(f"Results: {results['pass']} PASS, {results['fail']} FAIL, {results['warn']} WARN")
    print("=" * 60)

    # Print failures
    fails = [d for d in results["details"] if d["status"] == "fail"]
    if fails:
        print("\nFAILURES:")
        for f in fails:
            print(f"  - {f['name']}: {f['detail']}")

    return results

if __name__ == "__main__":
    asyncio.run(main())
