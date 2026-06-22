"""CLI 演示：自然语言搜餐厅。

需要先：
  1. 配置 .env 中的 AMAP_API_KEY 与 ANTHROPIC_API_KEY
  2. （可选）启动 Redis 加速搜索：docker-compose up -d redis

运行：
  python -m scripts.demo_cli
"""
import asyncio
import io
import sys
import uuid

# 让脚本可以直接运行
import pathlib

# Windows 控制台 UTF-8（含 stdin/stdout/stderr）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from src.core.logging import setup_logging  # noqa: E402
from src.graph import build_graph, make_initial_state  # noqa: E402


async def main():
    setup_logging("INFO")
    graph = build_graph()
    session_id = str(uuid.uuid4())

    print("🍜 餐厅推荐智能体（CLI 演示）")
    print("输入需求开始（quit 退出）。默认位置：北京望京 SOHO\n")

    while True:
        try:
            query = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if not query:
            continue
        if query.lower() in {"quit", "exit", ":q"}:
            break

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
            print(f"\n[错误] {e}\n")
            continue

        print(f"\n助手:\n{result.get('final_response', '(无返回)')}\n")
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())