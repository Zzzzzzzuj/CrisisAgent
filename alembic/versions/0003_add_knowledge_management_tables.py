"""add knowledge management tables

Revision ID: 0003_knowledge_mgmt
Revises: 0002_auth_users
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_knowledge_mgmt"
down_revision = "0002_auth_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("source_category", sa.String(length=128), nullable=False, server_default="general"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content_hash", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("embedding_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("published_status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_documents_document_id", "knowledge_documents", ["document_id"], unique=True)
    op.create_index("ix_knowledge_documents_source", "knowledge_documents", ["source"])
    op.create_index("ix_knowledge_documents_source_category", "knowledge_documents", ["source_category"])
    op.create_index("ix_knowledge_documents_embedding_status", "knowledge_documents", ["embedding_status"])
    op.create_index("ix_knowledge_documents_published_status", "knowledge_documents", ["published_status"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chunk_id", sa.String(length=255), nullable=False),
        sa.Column(
            "document_id",
            sa.String(length=128),
            sa.ForeignKey("knowledge_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("source_category", sa.String(length=128), nullable=False, server_default="general"),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("score_hint", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_chunks_chunk_id", "knowledge_chunks", ["chunk_id"], unique=True)
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
    op.create_index("ix_knowledge_chunks_source", "knowledge_chunks", ["source"])
    op.create_index("ix_knowledge_chunks_source_category", "knowledge_chunks", ["source_category"])
    op.create_index("ix_knowledge_chunks_embedding_status", "knowledge_chunks", ["embedding_status"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_embedding_status", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_source_category", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_source", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_chunk_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_documents_published_status", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_embedding_status", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_source_category", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_source", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_document_id", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
