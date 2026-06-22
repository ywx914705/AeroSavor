"""对话接口。"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import db_session, get_db
from ..core.llm import get_claude
from ..core.logging import get_logger
from ..core.event_bus import get_queue, cleanup_queue
from ..graph import build_graph, make_initial_state
from ..graph.prompts import AEROSAVOR_SYSTEM_PROMPT, STREAMING_SUMMARY_PROMPT
from ..models import Interaction
from ..monitoring.metrics import (
    _bucket_count,
    recommendation_count,
    recommendation_latency,
    search_requests_total,
)
from ..services.session_service import (
    append_message,
    get_or_create_default_user,
    get_or_create_session,
    get_prev_search_context,
    get_user,
    save_search_context,
    update_user_home_city,
)
from ..tools.coords import wgs84_to_gcj02
from .auth import CurrentUser, get_current_user

logger = get_logger(__name__)

router = APIRouter(prefix="", tags=["chat"])

# 单例图
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def _get_user_home_city(user_id: str) -> str | None:
    """从数据库读取用户的常驻城市。"""
    try:
        async with db_session() as db:
            u = await get_user(db, user_id)
            return u.home_city if u else None
    except Exception:
        return None


# ──────────── Schema ────────────


class LocationInput(BaseModel):
    lng: float
    lat: float
    # 客户端坐标系：浏览器原生 GPS 是 wgs84；高德 JS API / 经过转换的是 gcj02。
    # 默认按 gcj02（与本项目前端 useLocation 行为一致），原生 GPS 调用方需显式传 wgs84。
    coord_system: str = "gcj02"  # wgs84 | gcj02


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_location: LocationInput | None = None


class RecommendCard(BaseModel):
    id: str
    name: str
    rating: float = 0
    cost: int = 0
    distance: int = 0
    address: str = ""
    type: str = ""
    reason: str = ""
    highlight: str = ""
    suitable_for: str = ""
    amap_url: str = ""
    photos: list[str] = []
    location: str = ""


class ChatResponse(BaseModel):
    session_id: str
    response: str
    recommendations: list[RecommendCard] = []
    route_info: dict | None = None


# ──────────── 工具 ────────────


def _to_card(p: dict) -> RecommendCard:
    return RecommendCard(
        id=str(p.get("id", "")),
        name=str(p.get("name", "")),
        rating=float(p.get("rating", 0) or 0),
        cost=int(p.get("cost", 0) or 0),
        distance=int(p.get("distance", 0) or 0),
        address=str(p.get("address", "") or ""),
        type=str(p.get("type", "") or ""),
        reason=str(p.get("reason", "") or ""),
        highlight=str(p.get("highlight", "") or ""),
        suitable_for=str(p.get("suitable_for", "") or ""),
        amap_url=str(p.get("amap_url", "") or ""),
        photos=list(p.get("photos") or []),
        location=str(p.get("location", "") or ""),
    )


async def _save_interactions(
    user_id: str,
    session_id: str,
    state: dict,
) -> None:
    """异步把展示出来的 POI 写到 interactions 表（action=viewed）。"""
    try:
        async with db_session() as db:
            for rec in (state.get("recommendations") or [])[:5]:
                if not rec.get("id"):
                    continue
                db.add(
                    Interaction(
                        user_id=uuid.UUID(user_id),
                        session_id=uuid.UUID(session_id),
                        poi_id=str(rec["id"]),
                        poi_name=str(rec.get("name", "")),
                        poi_type=str(rec.get("type", ""))[:100] or None,
                        poi_typecode=str(rec.get("typecode", ""))[:20] or None,
                        poi_rating=float(rec.get("rating", 0) or 0) or None,
                        poi_cost=int(rec.get("cost", 0) or 0) or None,
                        poi_location=str(rec.get("location", "")) or None,
                        action="viewed",
                        search_keyword=", ".join(state.get("search_keywords") or []) or None,
                        weather=(state.get("weather") or {}).get("weather"),
                        hour_of_day=dt.now().hour,
                        score_breakdown={
                            "amap": rec.get("_score_breakdown", {}).get("amap"),
                            "preference": rec.get("_score_breakdown", {}).get("preference"),
                            "distance": rec.get("_score_breakdown", {}).get("distance"),
                            "price": rec.get("_score_breakdown", {}).get("price"),
                            "final": rec.get("_score"),
                        }
                        if rec.get("_score_breakdown") or rec.get("_score")
                        else None,
                    )
                )
            await db.commit()
    except Exception as e:
        logger.warning("save_interactions failed: %s", e)


# 偏好向量更新周期：每 N 轮触发一次。
# embedding API 有成本（~$0.001/次），不必每轮都跑。
_PREFERENCE_REFRESH_EVERY = 5


async def _post_chat_memory_tasks(
    user_id: str,
    session_id: str,
    state: dict,
    turn_count: int,
) -> None:
    """会话尾部的记忆维护：写永久层 home_city + 周期更新偏好向量。

    home_city 写入：优先使用 declared_preferences.city（精确城市名），
    其次用 declared_preferences.location（可能含区名，会自动提取城市名），
    最后用顶层 location_hint 作为备用源。
    偏好向量更新：每 _PREFERENCE_REFRESH_EVERY 轮触发一次。
    """
    # 1) 永久层 home_city
    try:
        declared = state.get("declared_preferences") or {}
        # 优先使用 city 字段（精确城市名），其次用 location（可能含区名）
        declared_city = declared.get("city") if isinstance(declared, dict) else None
        declared_loc = declared.get("location") if isinstance(declared, dict) else None
        # 也接受顶层 location_hint 作为备用源（某些 LLM 输出可能只填一边）
        candidate_city = declared_city or declared_loc or state.get("location_hint")
        if candidate_city:
            async with db_session() as db:
                wrote = await update_user_home_city(db, user_id, candidate_city)
                if wrote:
                    logger.info("home_city updated: user=%s city=%s", user_id, candidate_city)
    except Exception as e:
        logger.warning("update_user_home_city failed: %s", e)

    # 2) 偏好向量周期刷新
    try:
        if turn_count > 0 and turn_count % _PREFERENCE_REFRESH_EVERY == 0:
            from ..services.memory_service import memory_service
            await memory_service.update_preference_embedding(user_id)
    except Exception as e:
        logger.warning("update_user_preference_embedding failed: %s", e)


# ──────────── 路由 ────────────


def _merge_declared_prefs(ctx: dict, declared: dict) -> None:
    """将用户显式声明的偏好合并到 search_context（原地修改）。

    已有的值不覆盖（搜索结果优先），只补充新的声明。
    """
    if declared.get("location") and not ctx.get("location_hint"):
        ctx["location_hint"] = declared["location"]
    if declared.get("price_max") and not ctx.get("price_max"):
        ctx["price_max"] = declared["price_max"]
    if declared.get("price_min") and not ctx.get("price_min"):
        ctx["price_min"] = declared["price_min"]
    # 口味禁忌/偏好/环境需求 → 累加到 features 和专用字段
    for disliked in (declared.get("disliked") or []):
        ctx.setdefault("disliked", [])
        if disliked not in ctx["disliked"]:
            ctx["disliked"].append(disliked)
    for preferred in (declared.get("preferred") or []):
        ctx.setdefault("preferred", [])
        if preferred not in ctx["preferred"]:
            ctx["preferred"].append(preferred)
    for feat in (declared.get("features") or []):
        ctx.setdefault("features", [])
        if feat not in ctx["features"]:
            ctx["features"].append(feat)


def _normalize_location(loc: LocationInput | None) -> str | None:
    """前端输入坐标 → 高德 GCJ-02 格式 'lng,lat'。

    前端 useLocation 已将 WGS-84 转为 GCJ-02 并标记 coord_system='gcj02'。
    这里只做格式化；若前端没转，后端兜底再转一次。
    """
    if loc is None:
        return None
    lng, lat = loc.lng, loc.lat
    if (loc.coord_system or "gcj02").lower() == "wgs84":
        lng, lat = wgs84_to_gcj02(lng, lat)
    return f"{lng:.6f},{lat:.6f}"


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """同步对话。"""
    user = await get_or_create_default_user(db, current_user.id)
    session = await get_or_create_session(db, req.session_id, str(user.id))
    await append_message(db, str(session.id), "user", req.message)

    user_location = _normalize_location(req.user_location)

    # 读取上一轮搜索上下文（多轮对话关键）
    prev_ctx = await get_prev_search_context(db, str(session.id))
    if prev_ctx:
        logger.info("prev_ctx loaded: keys=%s recs=%d loc=%s",
                     list(prev_ctx.keys()), len(prev_ctx.get("recommendations", [])),
                     prev_ctx.get("location"))

    initial = make_initial_state(
        user_query=req.message,
        session_id=str(session.id),
        user_id=str(user.id),
        user_location=user_location,
        home_city=user.home_city,  # 永久层：跨会话的常驻城市
    )
    initial["messages"] = list(session.messages or [])
    if prev_ctx:
        initial["prev_search_context"] = prev_ctx

    graph = get_graph()
    t0 = time.monotonic()
    try:
        result = await graph.ainvoke(
            initial,
            config={"configurable": {"thread_id": str(session.id)}},
        )
    except Exception as e:
        logger.exception("graph invoke failed: %s", e)
        raise HTTPException(status_code=500, detail=f"agent error: {e}")

    elapsed = time.monotonic() - t0
    recs = result.get("recommendations") or []

    # ── 指标埋点 ──
    intent = result.get("intent", "search")
    search_requests_total.labels(
        intent=intent,
        result_count_bucket=_bucket_count(len(recs)),
    ).inc()
    recommendation_latency.observe(elapsed)
    recommendation_count.observe(len(recs))

    final = result.get("final_response", "")
    if not final:
        if intent in ("chat", "clarify"):
            final = "你好！我是 AeroSavor，告诉我你想吃什么，我来帮你找 😊"
        else:
            final = "抱歉，没有找到合适的餐厅。"
    response_text = final
    await append_message(db, str(session.id), "assistant", response_text)

    # 保存上下文供下一轮多轮对话使用
    intent = result.get("intent", "search")
    search_kw = result.get("search_keywords")
    has_search_ctx = intent == "search" and bool(search_kw)
    has_location = bool(result.get("location_hint") or result.get("resolved_location"))
    has_declared = bool(result.get("declared_preferences"))
    logger.info("ctx_save: intent=%s kw=%s has_search=%s has_loc=%s", intent, search_kw, has_search_ctx, has_location)
    if has_search_ctx or has_location or has_declared:
        # route 意图时，合并上轮搜索上下文（保留 keywords 和 recommendations）
        # 避免 route 意图覆盖上轮的推荐数据
        if intent == "route" and prev_ctx:
            search_ctx = {**prev_ctx}
            # 更新位置信息（可能更精确了）
            if result.get("resolved_location"):
                search_ctx["location"] = result.get("resolved_location")
            if result.get("location_hint"):
                search_ctx["location_hint"] = result.get("location_hint")
            if result.get("user_city"):
                search_ctx["city"] = result.get("user_city")
        else:
            search_ctx = {
                "keywords": result.get("search_keywords") or [],
                "price_max": result.get("price_max"),
                "price_min": result.get("price_min"),
                "location": result.get("resolved_location"),
                "location_hint": result.get("location_hint"),
                "features": result.get("feature_requests") or [],
                "city": result.get("user_city"),
                # 保存上轮推荐列表（供 route 意图"怎么去第X家"使用）
                "recommendations": [
                    {"id": r.get("id"), "name": r.get("name"), "location": r.get("location")}
                    for r in (result.get("recommendations") or [])[:5]
                ],
            }
        # 合并用户显式声明的偏好
        declared = result.get("declared_preferences")
        if declared:
            _merge_declared_prefs(search_ctx, declared)
        await save_search_context(db, str(session.id), search_ctx)

    asyncio.create_task(
        _save_interactions(str(user.id), str(session.id), result)
    )
    # 记忆任务必须 await，确保 home_city 写入后再返回响应，
    # 避免用户快速发送下一条消息时读到旧的 home_city=None
    await _post_chat_memory_tasks(
        str(user.id), str(session.id), result, session.turn_count or 0
    )

    return ChatResponse(
        session_id=str(session.id),
        response=response_text,
        recommendations=[
            _to_card(p) for p in (result.get("recommendations") or [])[:5]
        ],
        route_info=result.get("route_info"),
    )


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE 流式对话。"""
    user = await get_or_create_default_user(db, current_user.id)
    session = await get_or_create_session(db, req.session_id, str(user.id))
    await append_message(db, str(session.id), "user", req.message)

    user_location = _normalize_location(req.user_location)

    # 读取上一轮搜索上下文
    prev_ctx = await get_prev_search_context(db, str(session.id))

    initial = make_initial_state(
        user_query=req.message,
        session_id=str(session.id),
        user_id=str(user.id),
        user_location=user_location,
        home_city=user.home_city,  # 永久层：跨会话的常驻城市
    )
    initial["messages"] = list(session.messages or [])
    if prev_ctx:
        initial["prev_search_context"] = prev_ctx

    graph = get_graph()
    user_id = str(user.id)
    session_id = str(session.id)
    turn_count_for_memory = session.turn_count or 0

    async def generate():
        last_state: dict = {}
        accumulated = ""

        # 为当前会话注册事件队列
        event_queue = get_queue(session_id)

        try:
            # ── Phase 1: 跑图 + 同时转发 event_bus 思考事件到 SSE ──
            # 用 asyncio.Queue 做中间层：图节点 push_event → queue → SSE yield
            graph_done = asyncio.Event()
            graph_result_box: list[dict] = []

            async def _run_graph():
                try:
                    result = await graph.ainvoke(
                        initial,
                        config={"configurable": {"thread_id": session_id}},
                    )
                    graph_result_box.append(result)
                except Exception as e:
                    graph_result_box.append({"_error": e})
                finally:
                    graph_done.set()
                    # 推送一个哨兵事件，让事件转发循环退出
                    await event_queue.put({"type": "__graph_done__"})

            # 启动图执行（后台）
            asyncio.create_task(_run_graph())

            # 转发 event_bus 事件到 SSE 流
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # heartbeat
                    yield "data: {\"type\": \"heartbeat\"}\n\n"
                    continue

                if event.get("type") == "__graph_done__":
                    break
                # 跳过内部事件
                if event.get("type") == "done":
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # 取图结果
            result = graph_result_box[0]
            if "_error" in result:
                raise result["_error"]
            last_state = result

            # 立即推送推荐卡片
            recs = result.get("recommendations") or []
            if recs:
                payload = {
                    "type": "recommendations",
                    "data": [_to_card(p).model_dump() for p in recs[:5]],
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            # 推送路线信息（route 意图或推荐附带路线时）
            route_info = result.get("route_info")
            if route_info:
                yield f"data: {json.dumps({'type': 'route_info', 'route_info': route_info}, ensure_ascii=False)}\n\n"

            # ── Phase 2: 流式生成总结文本（逐 token 推送） ──
            # 如果 graph 闲聊意图（无推荐），直接推 final_response
            intent = result.get("intent", "search")
            has_recs = bool(recs)

            if has_recs and intent == "search":
                # 用 LLM astream 逐 token 生成总结
                weather = result.get("weather") or {}
                pref = result.get("user_preference")
                # 构造推荐摘要给 prompt
                rec_brief = "\n".join(
                    f"{i+1}. {r.get('name','')} | ⭐{r.get('rating','-')} | "
                    f"¥{r.get('cost','-')}/人 | {r.get('distance','-')}m | "
                    f"亮点:{r.get('highlight','')} | 理由:{r.get('reason','')}"
                    for i, r in enumerate(recs[:5])
                )
                prompt = STREAMING_SUMMARY_PROMPT.format(
                    user_query=req.message,
                    weather=f"{weather.get('weather','未知')} {weather.get('temperature','')}°C",
                    user_preference=(
                        pref.get("preference_text", "新用户") if pref else "新用户"
                    ),
                    recommendations=rec_brief,
                )

                llm = get_claude()
                streamed = False

                if llm is not None:
                    try:
                        async for chunk in llm.astream(prompt, max_tokens=600, system_prompt=AEROSAVOR_SYSTEM_PROMPT):
                            accumulated += chunk
                            streamed = True
                            payload = {
                                "type": "response",
                                "content": accumulated,
                            }
                            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    except Exception as e:
                        logger.warning("astream failed, fallback to final_response: %s", e)

                # astream 失败或无 LLM → 用 graph 的 final_response 兜底
                if not streamed:
                    fallback = result.get("final_response", "")
                    if fallback:
                        payload = {"type": "response", "content": fallback}
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        accumulated = fallback
                last_state["_final_text"] = accumulated
            else:
                # 非搜索意图（闲聊/澄清）—— ChatAgent 已在图内生成回复
                final_text = result.get("final_response", "")

                if final_text:
                    # 图内已生成完整回复，直接推送
                    payload = {"type": "response", "content": final_text}
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    accumulated = final_text
                else:
                    # 不应该发生，但安全兜底
                    fallback = "你好！我是 AeroSavor，告诉我你想吃什么，我来帮你找 😊"
                    payload = {"type": "response", "content": fallback}
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    accumulated = fallback

                last_state["_final_text"] = accumulated

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("stream failed: %s", e)
            err = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        finally:
            # 清理事件队列
            cleanup_queue(session_id)

        # ── 收尾：保存到数据库 ──
        try:
            async with db_session() as bg_db:
                final_text = last_state.get("_final_text") or last_state.get("final_response", "")
                if final_text:
                    sess = await get_or_create_session(bg_db, session_id, user_id)
                    msgs = list(sess.messages or [])
                    msgs.append({"role": "assistant", "content": final_text})
                    sess.messages = msgs
                    await bg_db.commit()

                intent = last_state.get("intent", "search")
                has_search_ctx = intent == "search" and last_state.get("search_keywords")
                has_location = bool(last_state.get("location_hint") or last_state.get("target_location"))
                has_declared = bool(last_state.get("declared_preferences"))
                if has_search_ctx or has_location or has_declared:
                    search_ctx = {
                        "keywords": last_state.get("search_keywords") or [],
                        "price_max": last_state.get("price_max"),
                        "price_min": last_state.get("price_min"),
                        "location": last_state.get("target_location"),
                        "location_hint": last_state.get("location_hint"),
                        "features": last_state.get("feature_requests") or [],
                        "city": last_state.get("user_city"),
                        "recommendations": [
                            {"id": r.get("id"), "name": r.get("name"), "location": r.get("location")}
                            for r in (last_state.get("recommendations") or [])[:5]
                        ],
                    }
                    declared = last_state.get("declared_preferences")
                    if declared:
                        _merge_declared_prefs(search_ctx, declared)
                    await save_search_context(bg_db, session_id, search_ctx)

            await _save_interactions(user_id, session_id, last_state)
            # 记忆维护：home_city + 周期偏好向量更新
            await _post_chat_memory_tasks(
                user_id, session_id, last_state, turn_count_for_memory
            )
        except Exception as e:
            logger.warning("post-stream save failed: %s", e)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )