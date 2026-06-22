"""填充测试数据：创建测试用户 + 模拟交互记录。

用于开发和评估推荐效果。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.core.database import db_session
from src.models import Interaction, Session, User, UserPreferenceEmbedding
from src.services.preference_service import update_user_preference_embedding

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def seed() -> None:
    """填充测试数据。"""
    async with db_session() as db:
        # 确保测试用户存在
        res = await db.execute(select(User).where(User.id == TEST_USER_ID))
        user = res.scalar_one_or_none()
        if user is None:
            user = User(id=TEST_USER_ID, nickname="测试用户")
            db.add(user)
            await db.commit()
            print("✅ 创建测试用户")

        # 创建测试会话
        session_id = uuid.uuid4()
        session = Session(
            id=session_id,
            user_id=TEST_USER_ID,
            messages=[
                {"role": "user", "content": "附近找个日料"},
                {"role": "assistant", "content": "推荐 3 家日料"},
            ],
        )
        db.add(session)

        # 模拟交互记录
        interactions = [
            Interaction(
                user_id=TEST_USER_ID,
                session_id=session_id,
                poi_id="B000A8UMIN",
                poi_name="将太无二(望京店)",
                poi_type="日本料理",
                poi_rating=4.5,
                poi_cost=150,
                poi_location="116.473168,39.993015",
                action="clicked",
                search_keyword="日料",
                hour_of_day=12,
            ),
            Interaction(
                user_id=TEST_USER_ID,
                session_id=session_id,
                poi_id="B000A8UIN2",
                poi_name="鳗步·活鳗料理(望京店)",
                poi_type="日本料理",
                poi_rating=4.7,
                poi_cost=200,
                poi_location="116.475000,39.994000",
                action="navigated",
                search_keyword="日料",
                hour_of_day=12,
            ),
            Interaction(
                user_id=TEST_USER_ID,
                session_id=session_id,
                poi_id="B000A8XYZ1",
                poi_name="川味观(望京店)",
                poi_type="川菜",
                poi_rating=4.2,
                poi_cost=80,
                poi_location="116.470000,39.991000",
                action="disliked",
                search_keyword="川菜",
                hour_of_day=18,
            ),
            Interaction(
                user_id=TEST_USER_ID,
                session_id=session_id,
                poi_id="B000A8ABC3",
                poi_name="粤菜馆(望京店)",
                poi_type="粤菜",
                poi_rating=4.6,
                poi_cost=120,
                poi_location="116.472000,39.995000",
                action="liked",
                search_keyword="粤菜",
                hour_of_day=19,
            ),
            Interaction(
                user_id=TEST_USER_ID,
                session_id=session_id,
                poi_id="B000A8DEF4",
                poi_name="星巴克(望京SOHO店)",
                poi_type="咖啡厅",
                poi_rating=4.3,
                poi_cost=40,
                poi_location="116.474000,39.993500",
                action="visited",
                search_keyword="咖啡",
                hour_of_day=15,
            ),
        ]
        for inter in interactions:
            db.add(inter)

        await db.commit()
        print(f"✅ 创建 {len(interactions)} 条交互记录")

    # 更新偏好向量
    await update_user_preference_embedding(TEST_USER_ID)
    print("✅ 更新用户偏好向量")

    # 验证
    async with db_session() as db:
        res = await db.execute(
            select(UserPreferenceEmbedding).where(
                UserPreferenceEmbedding.user_id == TEST_USER_ID
            )
        )
        pref = res.scalar_one_or_none()
        if pref:
            print(f"✅ 偏好文本: {pref.preference_text}")
            print(f"   喜欢菜系: {pref.preferred_cuisines}")
            print(f"   不喜欢菜系: {pref.disliked_cuisines}")
            print(f"   价格区间: {pref.price_range}")
        else:
            print("⚠️ 偏好向量未生成")


if __name__ == "__main__":
    asyncio.run(seed())
