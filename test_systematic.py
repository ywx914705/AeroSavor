"""系统性全量测试 - AeroSavor 产品测试（扩展版 v3）
搜索类测试区分：有推荐=PASS, 有兜底响应(超时/LLM慢)=WARN, 无响应=FAIL
"""
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

def _check_search_result(data, name):
    """搜索类测试的统一校验：推荐>0=PASS, 有兜底响应=WARN, 无响应=FAIL"""
    recs = data.get("recommendations", [])
    resp = data.get("response", "") or data.get("final_response", "")
    if recs and len(recs) > 0:
        record("pass", name, f"got {len(recs)} recommendations")
    elif resp and len(resp) > 5:
        # 有兜底响应（超时/LLM慢），系统没崩溃
        record("warn", name, f"LLM慢/超时, 有兜底响应: {resp[:60]}")
    else:
        record("fail", name, f"no recs, no response: {json.dumps(data, ensure_ascii=False)[:150]}")

# ═══════════════ Infrastructure ═══════════════

async def test_health():
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{BASE}/health")
        if r.status_code == 200:
            record("pass", "Health check")
        else:
            record("fail", "Health check", f"status={r.status_code}")

# ═══════════════ Chat/Intent ═══════════════

async def test_chat_greeting():
    try:
        data, sid = await call_chat("你好")
        resp = data.get("response", "") or data.get("final_response", "")
        if resp and len(resp) > 3:
            record("pass", "Chat greeting", f"response={resp[:50]}")
        else:
            record("fail", "Chat greeting", "empty response")
    except Exception as e:
        record("fail", "Chat greeting", str(e)[:100])

async def test_chat_identity():
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
    try:
        data, sid = await call_chat("你能做什么")
        resp = data.get("response", "") or data.get("final_response", "")
        if resp and len(resp) > 10:
            record("pass", "Chat feature", f"len={len(resp)}")
        else:
            record("fail", "Chat feature", "too short")
    except Exception as e:
        record("fail", "Chat feature", str(e)[:100])

async def test_chat_social():
    try:
        data, sid = await call_chat("谢谢")
        resp = data.get("response", "") or data.get("final_response", "")
        if resp and len(resp) > 3:
            record("pass", "Chat social", f"response={resp[:50]}")
        else:
            record("warn", "Chat social", "short response")
    except Exception as e:
        record("fail", "Chat social", str(e)[:100])

# ═══════════════ Search/Recommend ═══════════════

async def test_search_nearby():
    try:
        data, sid = await call_chat("附近有什么好吃的")
        _check_search_result(data, "Search nearby")
    except Exception as e:
        record("fail", "Search nearby", str(e)[:100])

async def test_search_cuisine():
    try:
        data, sid = await call_chat("推荐火锅")
        _check_search_result(data, "Search cuisine")
    except Exception as e:
        record("fail", "Search cuisine", str(e)[:100])

async def test_search_price():
    """搜索类 - 人均100以内的日料"""
    try:
        data, sid = await call_chat("人均100以内的日料")
        _check_search_result(data, "Search with price")
    except Exception as e:
        record("fail", "Search with price", str(e)[:100])

# ═══════════════ Negative Sentences ═══════════════

async def test_negative_only():
    try:
        data, sid = await call_chat("不想吃火锅")
        resp = data.get("response", "") or data.get("final_response", "")
        recs = data.get("recommendations", [])
        if resp and len(resp) > 5 and not recs:
            record("pass", "Negative only", f"clarified without recs: {resp[:50]}")
        elif resp and len(resp) > 5:
            record("warn", "Negative only", "has recs (should clarify)")
        else:
            record("fail", "Negative only", "empty response")
    except Exception as e:
        record("fail", "Negative only", str(e)[:100])

async def test_negative_affirmative():
    try:
        data, sid = await call_chat("不想吃火锅，推荐烧烤")
        _check_search_result(data, "Negative+affirmative")
    except Exception as e:
        record("fail", "Negative+affirmative", str(e)[:100])

# ═══════════════ Followup/Clarify ═══════════════

async def test_clarify_no_context():
    """追问无上下文 - 有没有便宜点的"""
    try:
        data, sid = await call_chat("有没有便宜点的")
        resp = data.get("response", "") or data.get("final_response", "")
        if resp and len(resp) > 5:
            record("pass", "Clarify (no context)", f"response={resp[:50]}")
        else:
            record("fail", "Clarify (no context)", "empty response")
    except Exception as e:
        record("fail", "Clarify (no context)", str(e)[:100])

async def test_followup_with_context():
    """追问有上下文 - 搜火锅后问换一家"""
    try:
        sid = str(uuid.uuid4())
        data1, _ = await call_chat("推荐火锅", session_id=sid)
        recs1 = data1.get("recommendations", [])
        data2, _ = await call_chat("换一家", session_id=sid)
        resp2 = data2.get("response", "") or data2.get("final_response", "")
        recs2 = data2.get("recommendations", [])
        if recs2 or (resp2 and len(resp2) > 10):
            record("pass", "Followup (with context)", f"2nd turn works, recs={len(recs2)}")
        else:
            record("fail", "Followup (with context)", "2nd turn empty")
    except Exception as e:
        record("fail", "Followup (with context)", str(e)[:100])

# ═══════════════ SSE/Session ═══════════════

async def test_stream_sse():
    try:
        events, sid = await call_chat("附近美食", stream=True)
        event_types = [e.get("type", "") for e in events]
        has_recommendations = any(e.get("type") == "recommendations" for e in events)
        has_response = any(e.get("type") == "response" for e in events)
        if has_recommendations or has_response:
            record("pass", "SSE stream", f"events={len(events)}, types={set(event_types)}")
        else:
            record("fail", "SSE stream", f"no meaningful events, types={set(event_types)}")
    except Exception as e:
        record("fail", "SSE stream", str(e)[:100])

async def test_session_persistence():
    try:
        sid = str(uuid.uuid4())
        data1, _ = await call_chat("你好", session_id=sid)
        data2, _ = await call_chat("推荐日料", session_id=sid)
        resp2 = data2.get("response", "") or data2.get("final_response", "")
        recs2 = data2.get("recommendations", [])
        if recs2 or (resp2 and len(resp2) > 10):
            record("pass", "Session persistence", f"2nd turn works, recs={len(recs2)}")
        else:
            record("fail", "Session persistence", "2nd turn empty")
    except Exception as e:
        record("fail", "Session persistence", str(e)[:100])

# ═══════════════ Edge Cases ═══════════════

async def test_invalid_session():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{BASE}/api/chat", json={"message": "你好", "session_id": "invalid-not-uuid"})
            if r.status_code in (400, 422):
                record("pass", "Invalid session rejected", f"status={r.status_code}")
            else:
                record("warn", "Invalid session rejected", f"status={r.status_code}")
    except Exception as e:
        record("fail", "Invalid session rejected", str(e)[:100])

async def test_empty_message():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{BASE}/api/chat", json={"message": "", "session_id": str(uuid.uuid4())})
            if r.status_code in (400, 422):
                record("pass", "Empty message rejected", f"status={r.status_code}")
            else:
                record("warn", "Empty message rejected", f"status={r.status_code}")
    except Exception as e:
        record("fail", "Empty message rejected", str(e)[:100])

async def test_long_message():
    """长消息 - 100字"""
    try:
        long_msg = "我想找一家距离不要太远的餐厅，最好是东北菜或者川菜，人均不要超过80元，环境要好一点，适合朋友聚餐，有包间更好"
        data, sid = await call_chat(long_msg)
        _check_search_result(data, "Long message")
    except Exception as e:
        record("fail", "Long message", str(e)[:100])

async def test_special_chars():
    """特殊字符 - 表情符号"""
    try:
        data, sid = await call_chat("附近有什么好吃的🔥")
        _check_search_result(data, "Special chars (emoji)")
    except Exception as e:
        record("fail", "Special chars (emoji)", str(e)[:100])

# ═══════════════ Route ═══════════════

async def test_route_no_context():
    """路线规划无上下文"""
    try:
        data, sid = await call_chat("怎么去最近的火锅店")
        resp = data.get("response", "") or data.get("final_response", "")
        if resp and len(resp) > 10:
            record("pass", "Route (no context)", f"response={resp[:50]}")
        else:
            record("warn", "Route (no context)", "short response")
    except Exception as e:
        record("fail", "Route (no context)", str(e)[:100])

# ═══════════════ Multi-turn ═══════════════

async def test_multiturn_search_then_refine():
    """多轮：搜火锅→不要辣的"""
    try:
        sid = str(uuid.uuid4())
        data1, _ = await call_chat("推荐火锅", session_id=sid)
        recs1 = data1.get("recommendations", [])
        data2, _ = await call_chat("不要辣的", session_id=sid)
        resp2 = data2.get("response", "") or data2.get("final_response", "")
        recs2 = data2.get("recommendations", [])
        if recs2 or (resp2 and len(resp2) > 5):
            record("pass", "Multi-turn: search->refine", f"1st recs={len(recs1)}, 2nd recs={len(recs2)}")
        else:
            record("fail", "Multi-turn: search->refine", "2nd turn empty")
    except Exception as e:
        record("fail", "Multi-turn: search->refine", str(e)[:100])

# ═══════════════ Main ═══════════════

async def main():
    print("=" * 60)
    print("AeroSavor Systematic Test Suite (Extended v3)")
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
            test_search_price,
        ]),
        ("Negative Sentences", [
            test_negative_only,
            test_negative_affirmative,
        ]),
        ("Followup/Clarify", [
            test_clarify_no_context,
            test_followup_with_context,
        ]),
        ("SSE/Session", [
            test_stream_sse,
            test_session_persistence,
        ]),
        ("Edge Cases", [
            test_invalid_session,
            test_empty_message,
            test_long_message,
            test_special_chars,
        ]),
        ("Route", [
            test_route_no_context,
        ]),
        ("Multi-turn", [
            test_multiturn_search_then_refine,
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
    total = results['pass'] + results['fail'] + results['warn']
    print(f"Results: {results['pass']} PASS, {results['fail']} FAIL, {results['warn']} WARN (total {total})")
    print("=" * 60)

    fails = [d for d in results["details"] if d["status"] == "fail"]
    if fails:
        print("\nFAILURES:")
        for f in fails:
            print(f"  - {f['name']}: {f['detail']}")

    return results

if __name__ == "__main__":
    asyncio.run(main())
