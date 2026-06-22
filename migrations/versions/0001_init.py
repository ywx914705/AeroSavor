"""init schema with pgvector

Revision ID: 0001_init
Revises:
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from pgvector.sqlalchemy import Vector


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector 扩展
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")  # 用于 gen_random_uuid

    # users
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("nickname", sa.String(50)),
        sa.Column("avatar_url", sa.Text()),
        sa.Column("home_city", sa.String(20)),
        sa.Column("home_location", sa.String(50)),
        sa.Column("default_radius", sa.Integer(), server_default="1000"),
        sa.Column("price_preference", ARRAY(sa.Integer())),
        sa.Column("search_count", sa.Integer(), server_default="0"),
        sa.Column("last_active", sa.TIMESTAMP(timezone=True)),
    )

    # sessions
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("messages", JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("last_location", sa.Text()),
        sa.Column("last_search_keys", ARRAY(sa.Text())),
        sa.Column("turn_count", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])
    op.create_index("idx_sessions_updated", "sessions", [sa.text("updated_at DESC")])

    # interactions
    op.create_table(
        "interactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("poi_id", sa.String(50), nullable=False),
        sa.Column("poi_name", sa.String(200), nullable=False),
        sa.Column("poi_type", sa.String(100)),
        sa.Column("poi_typecode", sa.String(20)),
        sa.Column("poi_rating", sa.Numeric(3, 1)),
        sa.Column("poi_cost", sa.Integer()),
        sa.Column("poi_location", sa.Text()),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("search_keyword", sa.Text()),
        sa.Column("weather", sa.String(20)),
        sa.Column("hour_of_day", sa.SmallInteger()),
        sa.Column("rating", sa.SmallInteger()),
        sa.Column("comment", sa.Text()),
    )
    op.create_index("idx_interactions_user_id", "interactions", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_interactions_poi_id", "interactions", ["poi_id"])

    # user_preference_embeddings
    op.create_table(
        "user_preference_embeddings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("embedding", Vector(1024)),
        sa.Column("preference_text", sa.Text()),
        sa.Column("preferred_cuisines", ARRAY(sa.Text())),
        sa.Column("disliked_cuisines", ARRAY(sa.Text())),
        sa.Column("price_range", ARRAY(sa.Integer())),
        sa.Column("min_rating", sa.Numeric(2, 1)),
        sa.Column("preferred_features", ARRAY(sa.Text())),
    )
    # 向量索引：数据为空时建索引可能 warning，按 PRD 保留
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_preference_embedding "
        "ON user_preference_embeddings USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )

    # poi_cache
    op.create_table(
        "poi_cache",
        sa.Column("poi_id", sa.String(50), primary_key=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.Text()),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("typecode", sa.String(20)),
        sa.Column("tel", sa.String(100)),
        sa.Column("rating", sa.Numeric(3, 1)),
        sa.Column("cost", sa.Integer()),
        sa.Column("open_time", sa.Text()),
        sa.Column("photos", JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("view_count", sa.Integer(), server_default="0"),
        sa.Column("click_count", sa.Integer(), server_default="0"),
        sa.Column("nav_count", sa.Integer(), server_default="0"),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )

    # favorites
    op.create_table(
        "favorites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("poi_id", sa.String(50), nullable=False),
        sa.Column("poi_name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.UniqueConstraint("user_id", "poi_id"),
    )


def downgrade() -> None:
    op.drop_table("favorites")
    op.drop_table("poi_cache")
    op.execute("DROP INDEX IF EXISTS idx_preference_embedding")
    op.drop_table("user_preference_embeddings")
    op.drop_index("idx_interactions_poi_id", table_name="interactions")
    op.drop_index("idx_interactions_user_id", table_name="interactions")
    op.drop_table("interactions")
    op.drop_index("idx_sessions_updated", table_name="sessions")
    op.drop_index("idx_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")