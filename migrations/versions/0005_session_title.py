"""为 sessions 表新增 title 字段。

支持会话自动命名和手动重命名。

Revision ID: 0005_session_title
Revises: 0004_interaction_score
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_session_title"
down_revision = "0004_interaction_score"


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("title", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "title")
