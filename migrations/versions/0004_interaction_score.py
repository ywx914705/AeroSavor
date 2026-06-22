"""为 interactions 表新增 score_breakdown JSONB 字段。

存储个性化排序的分数明细，为"个性化推荐"提供数据佐证。

Revision ID: 0004_interaction_score
Revises: 0003_session_search_context
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0004_interaction_score"
down_revision = "0003_session_search_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interactions",
        sa.Column("score_breakdown", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interactions", "score_breakdown")
