"""用户偏好服务（向量化 + 结构化）。"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import db_session
from ..core.logging import get_logger
from ..models import Interaction, UserPreferenceEmbedding

logger = get_logger(__name__)


async def get_user_preference(
    db: AsyncSession, user_id: str | uuid.UUID
) -> dict | None:
    """读取用户偏好（结构化 + 向量）。"""
    uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    res = await db.execute(
        select(UserPreferenceEmbedding).where(
            UserPreferenceEmbedding.user_id == uid
        )
    )
    row = res.scalar_one_or_none()
    if row is None:
        return None

    return {
        "preference_text": row.preference_text or "",
        "preferred_cuisines": list(row.preferred_cuisines or []),
        "disliked_cuisines": list(row.disliked_cuisines or []),
        "price_range": list(row.price_range or []),
        "min_rating": float(row.min_rating) if row.min_rating else None,
        "preferred_features": list(row.preferred_features or []),
        "embedding": row.embedding.tolist() if row.embedding is not None else None,
    }


async def _summarize_with_llm(records: list[dict]) -> str:
    """让 Claude 总结偏好文本（失败时用规则降级）。"""
    if not records:
        return ""

    # 规则降级：从交互记录中聚合菜系/价格分布
    types = [r["poi_type"] for r in records if r.get("poi_type")]
    costs = [r["poi_cost"] for r in records if r.get("poi_cost")]
    avg_cost = int(sum(costs) / len(costs)) if costs else None

    fallback = "用户偏好"
    if types:
        from collections import Counter

        top = ", ".join(t for t, _ in Counter(types).most_common(3))
        fallback += f"：常去 {top}"
    if avg_cost:
        fallback += f"，人均约 {avg_cost} 元"

    if not settings.ANTHROPIC_API_KEY:
        return fallback

    try:
        from ..core.llm import get_claude
        from ..graph.prompts import PREFERENCE_SUMMARY_PROMPT

        llm = get_claude()
        if llm is None:
            return fallback
        interaction_text = "\n".join(
            f"- {r.get('action', 'viewed')} {r.get('poi_name')}（{r.get('poi_type','')}，"
            f"人均¥{r.get('poi_cost','-')}，评分{r.get('poi_rating','-')}）"
            for r in records
        )
        text = await asyncio.wait_for(
            llm.ainvoke(
                PREFERENCE_SUMMARY_PROMPT.format(interactions=interaction_text),
                max_tokens=300,
            ),
            timeout=15.0,
        )
        return text.strip() or fallback
    except Exception as e:
        logger.warning("LLM summarize failed, fallback to rule: %s", e)
        return fallback


async def _embed_text(text: str) -> list[float] | None:
    """Embedding（兼容 OpenAI API，如 DashScope / 硅基流动）。"""
    if not settings.OPENAI_API_KEY or not text:
        return None
    try:
        from openai import AsyncOpenAI

        kwargs: dict = {"api_key": settings.OPENAI_API_KEY}
        if settings.OPENAI_BASE_URL:
            kwargs["base_url"] = settings.OPENAI_BASE_URL
        client = AsyncOpenAI(**kwargs)
        resp = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=text,
        )
        return list(resp.data[0].embedding)
    except Exception as e:
        logger.warning("embedding failed: %s", e)
        return None


async def update_user_preference_embedding(user_id: str | uuid.UUID) -> None:
    """从近期交互生成偏好文本 + 向量并写库。

    主路径：clicked / navigated / liked / visited 这四类强信号。
    回退：当强信号交互为空（用户只浏览不互动）时，退化使用最近 30 条
    `viewed` 记录——总比让用户永远停留在"新用户"状态好，但要在 preference_text
    末尾标注（弱信号），避免后续把它当作高置信度数据。
    """
    uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    weak_signal = False
    async with db_session() as db:
        res = await db.execute(
            select(Interaction)
            .where(
                Interaction.user_id == uid,
                Interaction.action.in_(
                    ["clicked", "navigated", "liked", "visited"]
                ),
            )
            .order_by(Interaction.created_at.desc())
            .limit(30)
        )
        interactions = res.scalars().all()

        if not interactions:
            # 回退：用最近 30 条 viewed 记录
            res = await db.execute(
                select(Interaction)
                .where(
                    Interaction.user_id == uid,
                    Interaction.action == "viewed",
                )
                .order_by(Interaction.created_at.desc())
                .limit(30)
            )
            interactions = res.scalars().all()
            if not interactions:
                logger.info("no interactions for user %s, skip embedding", uid)
                return
            weak_signal = True
            logger.info(
                "user %s has no strong interactions, fallback to %d viewed records",
                uid, len(interactions),
            )

        records = [
            {
                "poi_name": i.poi_name,
                "poi_type": i.poi_type,
                "poi_rating": float(i.poi_rating) if i.poi_rating else None,
                "poi_cost": i.poi_cost,
                "search_keyword": i.search_keyword,
                "action": i.action,
            }
            for i in interactions
        ]

        pref_text = await _summarize_with_llm(records)
        if weak_signal and pref_text:
            pref_text = pref_text.rstrip() + "（基于浏览行为推测，非强意向）"
        embedding = await _embed_text(pref_text)

        # 抽取结构化偏好：优先 LLM 提取，失败时规则降级
        preferred, disliked, price_range, preferred_features = (
            await _extract_structured_preferences(pref_text, records, uid, db)
        )

        # upsert
        existing = await db.execute(
            select(UserPreferenceEmbedding).where(
                UserPreferenceEmbedding.user_id == uid
            )
        )
        row = existing.scalar_one_or_none()
        if row is None:
            row = UserPreferenceEmbedding(user_id=uid)
            db.add(row)

        row.preference_text = pref_text
        if embedding is not None:
            row.embedding = embedding
        row.preferred_cuisines = preferred
        row.disliked_cuisines = disliked if disliked else None
        if price_range:
            row.price_range = price_range
        row.preferred_features = preferred_features if preferred_features else None

        # min_rating：从交互记录中计算最低评分
        ratings = [r["poi_rating"] for r in records if r.get("poi_rating")]
        if ratings:
            row.min_rating = min(ratings)

        await db.commit()
        logger.info("updated preference for user %s: %s", uid, pref_text[:50])


async def _extract_structured_preferences(
    pref_text: str,
    records: list[dict],
    uid: uuid.UUID,
    db: AsyncSession,
) -> tuple[list[str], list[str], list[int] | None, list[str]]:
    """提取结构化偏好：优先 LLM（PREFERENCE_STRUCTURED_PROMPT），失败时规则降级。

    返回 (preferred_cuisines, disliked_cuisines, price_range, preferred_features)
    """
    from collections import Counter

    # ── 规则降级：始终先计算，LLM 失败时使用 ──
    cuisine_counter: Counter = Counter()
    for r in records:
        if r.get("poi_type"):
            cuisine_counter[r["poi_type"]] += 1
    rule_preferred = [c for c, _ in cuisine_counter.most_common(5)]

    disliked_counter: Counter = Counter()
    disliked_res = await db.execute(
        select(Interaction.poi_type)
        .where(
            Interaction.user_id == uid,
            Interaction.action == "disliked",
        )
        .order_by(Interaction.created_at.desc())
        .limit(20)
    )
    for (poi_type,) in disliked_res.all():
        if poi_type:
            disliked_counter[poi_type] += 1
    rule_disliked = [c for c, _ in disliked_counter.most_common(5)]

    costs = [r["poi_cost"] for r in records if r.get("poi_cost")]
    rule_price_range = [max(0, min(costs) - 30), max(costs) + 50] if costs else None

    rule_features: list[str] = []

    # ── LLM 路径 ──
    if settings.ANTHROPIC_API_KEY and pref_text:
        try:
            from ..core.llm import get_claude
            from ..graph.prompts import PREFERENCE_STRUCTURED_PROMPT

            llm = get_claude()
            if llm is not None:
                interaction_text = "\n".join(
                    f"- {r.get('action', 'viewed')} {r.get('poi_name')}（{r.get('poi_type','')}，"
                    f"人均¥{r.get('poi_cost','-')}，评分{r.get('poi_rating','-')}）"
                    for r in records
                )
                result = await asyncio.wait_for(
                    llm.ainvoke(
                        PREFERENCE_STRUCTURED_PROMPT.format(
                            preference_text=pref_text,
                            interactions=interaction_text,
                        ),
                        max_tokens=300,
                    ),
                    timeout=15.0,
                )
                import json

                parsed = json.loads(result.strip())
                preferred = parsed.get("preferred_cuisines", rule_preferred)
                disliked = parsed.get("disliked_cuisines", rule_disliked)
                pr = parsed.get("price_range")
                price_range = pr if pr and len(pr) == 2 else rule_price_range
                features = parsed.get("preferred_features", rule_features)
                return preferred, disliked, price_range, features
        except Exception as e:
            logger.warning("LLM structured extraction failed, fallback to rule: %s", e)

    # ── 规则降级 ──
    return rule_preferred, rule_disliked, rule_price_range, rule_features


async def embed_text(text: str) -> list[float] | None:
    """对外暴露的 embedding 工具。"""
    return await _embed_text(text)
