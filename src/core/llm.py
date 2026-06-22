"""极简 Claude 客户端 - 兼容小米代理（Bearer token）和官方 Anthropic（x-api-key）。

用 httpx 直接调，不依赖 langchain-anthropic，避免 Bearer/x-api-key 切换问题。
带重试：429/5xx 自动重试（指数退避）。
支持 LangSmith 链路追踪（LANGCHAIN_TRACING_V2=true 时自动上报 LLM 调用）。
"""
from __future__ import annotations

import asyncio
import json
import time

import httpx

from .config import settings
from .logging import get_logger

logger = get_logger(__name__)

# ── LangSmith 追踪（可选） ──
_traceable = None
if settings.LANGCHAIN_TRACING_V2 and settings.LANGCHAIN_API_KEY:
    try:
        from langsmith import traceable as _traceable
    except ImportError:
        logger.warning("langsmith not installed, tracing disabled")

# 重试配置
MAX_RETRIES = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
INITIAL_BACKOFF = 1.0  # 秒


class ClaudeClient:
    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "claude-sonnet-4-6",
        timeout: float = 120.0,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        # 规范化 base_url：去掉末尾 /v1 /v1/messages 等后缀
        raw = (base_url or "https://api.anthropic.com").rstrip("/")
        for suffix in ("/v1/messages", "/v1", "/messages"):
            if raw.endswith(suffix):
                raw = raw[: -len(suffix)]
        self.base_url = raw.rstrip("/")
        self._http = httpx.AsyncClient(timeout=timeout)

    def _headers(self) -> dict:
        # 自定义代理（如小米）用 Bearer；官方用 x-api-key。都带上。
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    async def ainvoke(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.3,
        system_prompt: str | None = None,
    ) -> str:
        """单 prompt → 文本输出。带重试。失败返回空串（调用方负责降级）。"""
        t0 = time.monotonic()
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        url = f"{self.base_url}/v1/messages"

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self._http.post(url, headers=self._headers(), json=body)
                resp.raise_for_status()
                data = resp.json()
                break  # 成功，跳出重试循环
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning("claude timeout (%.0fs) attempt %d/%d", self.timeout, attempt + 1, MAX_RETRIES + 1)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(INITIAL_BACKOFF * (2 ** attempt))
                    continue
                return ""
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in RETRYABLE_STATUS and attempt < MAX_RETRIES:
                    logger.warning("claude HTTP %d (retryable) attempt %d/%d", status_code, attempt + 1, MAX_RETRIES + 1)
                    await asyncio.sleep(INITIAL_BACKOFF * (2 ** attempt))
                    continue
                logger.warning("claude HTTP %s: %s", status_code, e.response.text[:200])
                return ""
            except httpx.HTTPError as e:
                last_error = e
                logger.warning("claude HTTP error: %s attempt %d/%d", e, attempt + 1, MAX_RETRIES + 1)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(INITIAL_BACKOFF * (2 ** attempt))
                    continue
                return ""
        else:
            logger.warning("claude all retries exhausted: %s", last_error)
            return ""

        # Anthropic 原生格式: data["content"] = [{"type":"text","text":"..."}]
        content_blocks = data.get("content") or []
        out_parts: list[str] = []
        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            # 跳过 thinking 块，只保留 text
            if block.get("type") == "text" and block.get("text"):
                out_parts.append(block["text"])
        text = "\n".join(out_parts).strip()

        # 兼容 OpenAI 风格响应（万一代理转成了那种）
        if not text and data.get("choices"):
            try:
                text = data["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError):
                pass

        elapsed = time.monotonic() - t0

        # LangSmith 追踪：记录 LLM 调用
        if _traceable is not None:
            try:
                _report_llm_run(
                    prompt=prompt[:200],
                    response=text[:200],
                    model=self.model,
                    latency_s=elapsed,
                    purpose="ainvoke",
                )
            except Exception:
                pass

        return text

    async def astream(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.5,
        system_prompt: str | None = None,
    ):
        """流式输出：逐 token yield 文本片段（Anthropic SSE streaming API）。

        失败时抛出异常，调用方可 fallback 到 ainvoke。
        """
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "messages": messages,
        }
        url = f"{self.base_url}/v1/messages"

        async with self._http.stream(
            "POST", url, headers=self._headers(), json=body,
            timeout=self.timeout,
        ) as resp:
            resp.raise_for_status()
            buffer = ""
            async for raw_chunk in resp.aiter_text():
                buffer += raw_chunk
                # Anthropic SSE 以 \n 分隔事件，每行 "event:xxx\ndata:{json}\n"
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        return
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    # content_block_delta 事件携带文本片段
                    if data.get("type") == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield delta.get("text", "")
                    # message_stop 事件：流结束
                    elif data.get("type") == "message_stop":
                        return
                    # 也兼容 OpenAI-style SSE（某些代理可能转换格式）
                    elif "choices" in data:
                        delta = (data["choices"] or [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content

    async def aclose(self) -> None:
        await self._http.aclose()


def _report_llm_run(
    prompt: str,
    response: str,
    model: str,
    latency_s: float,
    purpose: str,
) -> None:
    """向 LangSmith 上报一次 LLM 调用（轻量级，不阻塞主流程）。"""
    try:
        from langsmith import Client as LangSmithClient

        ls = LangSmithClient()
        ls.create_run(
            name=f"llm_{purpose}",
            run_type="llm",
            inputs={"prompt": prompt},
            outputs={"response": response},
            extra={"model": model, "latency_s": latency_s},
            project_name=settings.LANGCHAIN_PROJECT,
        )
    except Exception:
        pass  # 静默失败，不影响主流程


# 全局单例
_client: ClaudeClient | None = None


def get_claude() -> ClaudeClient | None:
    """没配置 Key 时返回 None，调用方走规则降级。"""
    global _client
    if _client is not None:
        return _client
    if not settings.ANTHROPIC_API_KEY:
        return None
    _client = ClaudeClient(
        api_key=settings.ANTHROPIC_API_KEY,
        base_url=settings.ANTHROPIC_BASE_URL or None,
        model=settings.CLAUDE_MODEL,
    )
    return _client


async def close_claude() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
