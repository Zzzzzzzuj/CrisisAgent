"""add knowledge governance fields

Revision ID: 0005_knowledge_governance
Revises: 0004_pgvector
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_knowledge_governance"
down_revision = "0004_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="published"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("source_name", sa.String(length=255), nullable=False, server_default=""),
    )
    op.create_index("ix_knowledge_documents_status", "knowledge_documents", ["status"])
    op.create_index("ix_knowledge_documents_is_enabled", "knowledge_documents", ["is_enabled"])

    op.execute("UPDATE knowledge_documents SET status = COALESCE(NULLIF(published_status, ''), 'published')")
    op.execute("UPDATE knowledge_documents SET source_name = COALESCE(NULLIF(source, ''), title)")


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_is_enabled", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_status", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "source_name")
    op.drop_column("knowledge_documents", "is_enabled")
    op.drop_column("knowledge_documents", "status")
