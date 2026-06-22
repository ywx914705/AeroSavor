"""推荐效果评估。"""
import asyncio
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text  # noqa: E402

from src.core.database import db_session  # noqa: E402


async def main(days: int = 7):
    async with db_session() as db:
        row = (
            await db.execute(
                text(
                    """
            SELECT
                COUNT(*) FILTER (WHERE action = 'viewed')   AS impressions,
                COUNT(*) FILTER (WHERE action = 'clicked')  AS clicks,
                COUNT(*) FILTER (WHERE action = 'navigated')AS navigations,
                COUNT(*) FILTER (WHERE action = 'liked')    AS likes,
                COUNT(*) FILTER (WHERE action = 'disliked') AS dislikes,
                AVG(rating) FILTER (WHERE rating IS NOT NULL) AS avg_rating
            FROM interactions
            WHERE created_at > NOW() - (:days || ' days')::interval
        """
                ),
                {"days": days},
            )
        ).mappings().one()

    impressions = row["impressions"] or 0
    clicks = row["clicks"] or 0
    navigations = row["navigations"] or 0
    ctr = clicks / impressions if impressions else 0
    nav_rate = navigations / clicks if clicks else 0

    print(f"过去 {days} 天推荐效果:")
    print(f"  展示: {impressions}")
    print(f"  点击: {clicks}（CTR {ctr:.1%}）")
    print(f"  导航: {navigations}（导航转化 {nav_rate:.1%}）")
    print(f"  收藏: {row['likes']}  踩: {row['dislikes']}")
    print(f"  平均评分: {row['avg_rating']}")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    asyncio.run(main(days))