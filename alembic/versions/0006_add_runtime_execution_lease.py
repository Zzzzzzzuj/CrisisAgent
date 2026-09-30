"""Add DB-backed ownership and fencing for runtime execution.

Revision ID: 0006_runtime_lease
Revises: 0005_knowledge_governance
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_runtime_lease"
down_revision = "0005_knowledge_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_checkpoints", sa.Column("execution_kind", sa.String(length=16), nullable=False, server_default="dynamic"))
    op.add_column("agent_checkpoints", sa.Column("execution_owner", sa.String(length=64), nullable=True))
    op.add_column("agent_checkpoints", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_checkpoints", sa.Column("execution_fence", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("agent_checkpoints", "execution_fence")
    op.drop_column("agent_checkpoints", "lease_expires_at")
    op.drop_column("agent_checkpoints", "execution_owner")
    op.drop_column("agent_checkpoints", "execution_kind")
