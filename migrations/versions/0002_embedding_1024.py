"""alter embedding dimension 1536 -> 1024

Revision ID: 0002_embedding_1024
Revises: 0001_init
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0002_embedding_1024"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 删除旧索引（如果存在）
    op.execute("DROP INDEX IF EXISTS idx_preference_embedding;")
    # 修改向量维度
    op.alter_column(
        "user_preference_embeddings",
        "embedding",
        type_=Vector(1024),
        existing_nullable=True,
    )
    # 重建索引
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_preference_embedding "
        "ON user_preference_embeddings USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_preference_embedding;")
    op.alter_column(
        "user_preference_embeddings",
        "embedding",
        type_=Vector(1536),
        existing_nullable=True,
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_preference_embedding "
        "ON user_preference_embeddings USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )
