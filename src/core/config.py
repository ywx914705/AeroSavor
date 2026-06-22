"""全局配置（pydantic-settings 自动读取 .env）。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 高德地图
    AMAP_API_KEY: str = ""
    AMAP_DEFAULT_CITY: str = "北京"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = ""  # 自定义代理地址（如小米代理），留空则用官方
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # Embedding（兼容 OpenAI API 的服务，如 DashScope / 硅基流动）
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""  # 留空走 OpenAI 官方，填了走中转
    EMBEDDING_MODEL: str = "text-embedding-v4"

    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/restaurant_agent"
    REDIS_URL: str = "redis://localhost:6379/0"

    # 搜索参数
    DEFAULT_SEARCH_RADIUS: int = 1000
    MAX_SEARCH_RETRY: int = 2
    MAX_RECOMMENDATIONS: int = 5
    DEFAULT_LOCATION: str = "116.473168,39.993015"

    # 安全
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_EXPIRE_HOURS: int = 24 * 7

    # LangSmith
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "restaurant-agent"

    # Sentry
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "development"

    # 日志
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"  # text | json

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
