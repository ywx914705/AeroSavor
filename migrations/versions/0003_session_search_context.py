"""为 sessions 表新增 search_context JSONB 字段（多轮对话的结构化上下文）。

之前实现把 JSON 塞进 last_location 字段（本应存 'lng,lat' 坐标），
导致 last_location 名存实亡且语义混乱。本迁移分离两者。

Revision ID: 0003_session_search_context
Revises: 0002_embedding_1024
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0003_session_search_context"
down_revision = "0002_embedding_1024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("search_context", JSONB(), nullable=True),
    )
    # 把历史误存的 JSON 从 last_location 迁回 search_context
    # 仅迁移看起来是 JSON 的（以 { 开头的）；纯坐标保留在 last_location
    op.execute(
        """
        UPDATE sessions
        SET search_context = last_location::jsonb,
            last_location = NULL
        WHERE last_location IS NOT NULL
          AND last_location LIKE '{%'
        """
    )


def downgrade() -> None:
    op.drop_column("sessions", "search_context")
