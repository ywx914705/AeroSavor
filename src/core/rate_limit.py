"""请求限流中间件 - Redis 优先，无 Redis 自动降级到内存。

按 user_id（带 token）或 client IP（匿名）维度，每小时 N 次。
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .logging import get_logger
from .redis_client import get_redis
from ..monitoring.metrics import rate_limit_hits as _rate_limit_counter

logger = get_logger(__name__)


class _MemoryBucket:
    """内存滑动窗口（无 Redis 时降级用）。

    带定期清理，防止 key 无限增长。
    """

    MAX_KEYS = 10_000  # 最多追踪的 key 数
    CLEANUP_INTERVAL = 300  # 每 5 分钟清理一次过期 key

    def __init__(self, window: int, limit: int):
        self.window = window
        self.limit = limit
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._last_cleanup = time.time()

    async def hit(self, key: str) -> tuple[bool, int]:
        """返回 (是否通过, 当前窗口内已用次数)。"""
        now = time.time()
        cutoff = now - self.window
        async with self._lock:
            # 定期清理过期 key，防止内存泄漏
            if now - self._last_cleanup > self.CLEANUP_INTERVAL:
                self._cleanup(cutoff)
                self._last_cleanup = now

            q = self.events[key]
            while q and q[0] < cutoff:
                q.popleft()
            # 空队列的 key 在下次 cleanup 时移除
            if len(q) >= self.limit:
                return False, len(q)
            q.append(now)
            return True, len(q) + 1

    def _cleanup(self, cutoff: float) -> None:
        """移除过期且为空的 key。"""
        expired = [
            k for k, q in self.events.items()
            if not q or q[-1] < cutoff
        ]
        for k in expired:
            del self.events[k]
        # 兜底：如果 key 数量超限，移除最旧的
        if len(self.events) > self.MAX_KEYS:
            sorted_keys = sorted(
                self.events.keys(),
                key=lambda k: self.events[k][-1] if self.events[k] else 0,
            )
            for k in sorted_keys[: len(self.events) - self.MAX_KEYS]:
                del self.events[k]


_memory_bucket: _MemoryBucket | None = None


def _get_memory_bucket(window: int, limit: int) -> _MemoryBucket:
    global _memory_bucket
    if _memory_bucket is None:
        _memory_bucket = _MemoryBucket(window, limit)
    return _memory_bucket


async def _check_redis(key: str, window: int, limit: int) -> tuple[bool, int]:
    """Redis incr + expire。"""
    try:
        r = get_redis()
        bucket = int(time.time() // window)
        rkey = f"ratelimit:{key}:{bucket}"
        # pipeline：原子的 incr + expire
        async with r.pipeline(transaction=True) as p:
            p.incr(rkey)
            p.expire(rkey, window + 5)
            count, _ = await p.execute()
        return count <= limit, int(count)
    except Exception as e:
        logger.debug("rate-limit redis failed, fallback memory: %s", e)
        return await _get_memory_bucket(window, limit).hit(key)


def _client_key(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return f"u:{auth[7:][:32]}"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return f"ip:{fwd.split(',')[0].strip()}"
    if request.client:
        return f"ip:{request.client.host}"
    return "ip:unknown"


# 仅对昂贵接口限流
LIMITED_PATHS = ("/api/chat", "/api/chat/stream")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, window: int = 3600, limit: int = 100):
        super().__init__(app)
        self.window = window
        self.limit = limit

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not any(path.startswith(p) for p in LIMITED_PATHS):
            return await call_next(request)

        key = _client_key(request)
        ok, used = await _check_redis(key, self.window, self.limit)
        if not ok:
            logger.warning("rate-limit hit: %s used=%d/%d", key, used, self.limit)
            _rate_limit_counter.inc()
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": f"请求过于频繁，每小时最多 {self.limit} 次，已用 {used} 次。",
                },
                headers={
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Used": str(used),
                    "Retry-After": str(self.window),
                },
            )
        resp = await call_next(request)
        resp.headers["X-RateLimit-Limit"] = str(self.limit)
        resp.headers["X-RateLimit-Used"] = str(used)
        return resp
