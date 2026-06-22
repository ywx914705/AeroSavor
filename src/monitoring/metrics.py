"""Prometheus 业务指标埋点。

在 main.py 中 import 并 expose /metrics 端点即可采集。
不依赖外部服务，纯内存计数器。
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# ── 搜索指标 ──

search_requests_total = Counter(
    "restaurant_search_total",
    "搜索请求总数",
    labelnames=["intent", "result_count_bucket"],
)

# result_count_bucket: "0" / "1-3" / "4-10" / "10+"

# ── 推荐指标 ──

recommendation_latency = Histogram(
    "recommendation_latency_seconds",
    "图执行总耗时（从意图解析到最终输出）",
    buckets=[0.5, 1, 2, 3, 5, 8, 13],
)

recommendation_count = Histogram(
    "recommendation_count",
    "每次推荐返回的餐厅数量",
    buckets=[0, 1, 2, 3, 4, 5],
)

# ── 高德 API 指标 ──

amap_api_calls = Counter(
    "amap_api_calls_total",
    "高德 API 调用次数",
    labelnames=["endpoint", "cache_hit"],
)

amap_api_latency = Histogram(
    "amap_api_latency_seconds",
    "高德 API 响应时间",
    labelnames=["endpoint"],
    buckets=[0.1, 0.3, 0.5, 1, 2, 4, 8],
)

# ── 用户行为指标 ──

user_feedback_total = Counter(
    "user_feedback_total",
    "用户反馈次数",
    labelnames=["action"],
)

# ── LLM 指标 ──

llm_calls_total = Counter(
    "llm_calls_total",
    "LLM 调用次数",
    labelnames=["purpose", "status"],
)
# purpose: intent / recommend / summary / chat
# status: success / fallback / error

llm_latency = Histogram(
    "llm_latency_seconds",
    "LLM 响应时间",
    labelnames=["purpose"],
    buckets=[0.5, 1, 2, 4, 8, 15],
)

# ── 系统指标 ──

active_sessions = Gauge(
    "restaurant_active_sessions",
    "当前活跃会话数（近 1 小时有交互）",
)

rate_limit_hits = Counter(
    "rate_limit_hits_total",
    "限流触发次数",
)


def _bucket_count(n: int) -> str:
    if n == 0:
        return "0"
    if n <= 3:
        return "1-3"
    if n <= 10:
        return "4-10"
    return "10+"
