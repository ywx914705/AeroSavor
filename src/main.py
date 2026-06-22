"""FastAPI 入口。"""
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import chat, feedback, history
from .core.config import settings
from .core.llm import close_claude
from .core.logging import get_logger, setup_logging
from .core.rate_limit import RateLimitMiddleware
from .core.redis_client import close_redis
from .monitoring.metrics import generate_latest, CONTENT_TYPE_LATEST
from .tools.amap_client import close_amap_client

logger = get_logger(__name__)

# ── Sentry 初始化（有 DSN 时启用） ──
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=0.3,
        profiles_sample_rate=0.1,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("starting restaurant-agent")
    yield
    await close_amap_client()
    await close_redis()
    await close_claude()
    logger.info("stopped")


app = FastAPI(
    title="Restaurant Agent API",
    description="餐厅推荐智能体 - LangGraph + 高德 + pgvector",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS（开发模式宽松，生产请限制 origins）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限流：/api/chat 路径每小时 100 次
app.add_middleware(RateLimitMiddleware, window=3600, limit=100)


@app.get("/")
async def root():
    return {
        "name": "restaurant-agent",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": ["/chat", "/chat/stream", "/feedback", "/history", "/favorites"],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    """Prometheus 采集端点。"""
    from fastapi.responses import Response

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# 子路由
app.include_router(chat.router, prefix="/api")
app.include_router(feedback.router, prefix="/api")
app.include_router(history.router, prefix="/api")