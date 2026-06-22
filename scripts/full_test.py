"""完整 LangGraph 链路非交互测试 - 直接传中文 query 进去（避免管道编码问题）。

验证：
  - 意图解析（小米 Claude 代理）
  - 高德搜索（Web Key）
  - 个性化排序（冷启动）
  - 推荐生成（Claude）
  - 最终格式化输出
"""
import asyncio
import io
import sys
import uuid
import pathlib

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from src.core.logging import setup_logging  # noqa: E402
from src.graph import build_graph, make_initial_state  # noqa: E402


QUERIES = [
    "找个望京附近的火锅",
    "人均 100 以内的日料",
]


async def main():
    setup_logging("INFO")
    graph = build_graph()
    session_id = str(uuid.uuid4())

    print("=" * 60)
    print("LangGraph 完整链路测试")
    print("=" * 60)

    for i, query in enumerate(QUERIES, 1):
        print(f"\n[Query {i}] {query}")
        print("-" * 60)

        state = make_initial_state(
            user_query=query,
            session_id=session_id,
            user_id="00000000-0000-0000-0000-000000000001",
            user_location="116.473168,39.993015",
            user_city="北京",
        )

        try:
            result = await graph.ainvoke(
                state,
                config={"configurable": {"thread_id": session_id}},
            )
        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback

            traceback.print_exc()
            continue

        print(f"\n意图: {result.get('intent')}")
        print(f"关键词: {result.get('search_keywords')}")
        print(f"目标位置: {result.get('target_location')}")
        print(f"原始 POI 数: {len(result.get('raw_pois') or [])}")
        print(f"推荐数: {len(result.get('recommendations') or [])}")
        print(f"\n最终响应:\n{result.get('final_response', '(空)')}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
