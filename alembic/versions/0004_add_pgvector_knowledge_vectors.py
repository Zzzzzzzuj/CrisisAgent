"""add pgvector knowledge vectors

Revision ID: 0004_pgvector
Revises: 0003_knowledge_mgmt
Create Date: 2026-08-20
"""

from alembic import op
import os
import sqlalchemy as sa


revision = "0004_pgvector"
down_revision = "0003_knowledge_mgmt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if _is_postgresql():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _create_vector_table()
    if _is_postgresql():
        op.execute("ALTER TABLE knowledge_chunk_vectors ADD COLUMN embedding vector(512)")
    else:
        op.add_column("knowledge_chunk_vectors", sa.Column("embedding", sa.Text(), nullable=True))
    op.create_index(
        "ix_knowledge_chunk_vectors_dimension",
        "knowledge_chunk_vectors",
        ["embedding_dimension"],
    )
    if _is_postgresql():
        _create_vector_index()


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunk_vectors_embedding")
    op.drop_index("ix_knowledge_chunk_vectors_dimension", table_name="knowledge_chunk_vectors")
    op.drop_table("knowledge_chunk_vectors")


def _create_vector_index() -> None:
    index_type = os.getenv("PGVECTOR_INDEX_TYPE", "ivfflat").strip().lower()
    if index_type == "none":
        return
    if index_type not in {"ivfflat", "hnsw"}:
        index_type = "ivfflat"

    distance = os.getenv("PGVECTOR_DISTANCE", "cosine").strip().lower()
    opclass = "vector_l2_ops" if distance == "l2" else "vector_cosine_ops"
    with_clause = " WITH (lists = 100)" if index_type == "ivfflat" else ""
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_vectors_embedding
        ON knowledge_chunk_vectors
        USING {index_type} (embedding {opclass})
        {with_clause}
        """
    )


def _create_vector_table() -> None:
    op.create_table(
        "knowledge_chunk_vectors",
        sa.Column(
            "chunk_id",
            sa.String(length=255),
            sa.ForeignKey("knowledge_chunks.chunk_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("embedding_model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"
