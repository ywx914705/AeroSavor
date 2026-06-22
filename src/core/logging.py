"""统一日志配置。

支持环境变量 LOG_FORMAT=json 切换为结构化 JSON 日志（生产推荐）。
默认为人类可读的文本格式（开发用）。
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from .config import settings


class _JsonFormatter(logging.Formatter):
    """结构化 JSON 日志格式器。"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        # 附加自定义字段
        for key in ("request_id", "user_id", "session_id", "duration_ms"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        return json.dumps(log_entry, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    """人类可读的文本日志格式器。"""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        # 附加自定义字段
        extras = []
        for key in ("request_id", "user_id", "session_id", "duration_ms"):
            if hasattr(record, key):
                extras.append(f"{key}={getattr(record, key)}")
        if extras:
            base += f" [{', '.join(extras)}]"
        return base


def setup_logging(level: str | None = None) -> None:
    """初始化日志系统。

    通过环境变量 LOG_FORMAT=json 启用 JSON 结构化日志。
    通过环境变量 LOG_LEVEL=DEBUG 设置日志级别。
    """
    log_level = level or getattr(settings, "LOG_LEVEL", None) or "INFO"
    log_format = getattr(settings, "LOG_FORMAT", "text")

    if log_format.lower() == "json":
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = _TextFormatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    # 避免重复添加 handler
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)

    # 第三方库降级
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
