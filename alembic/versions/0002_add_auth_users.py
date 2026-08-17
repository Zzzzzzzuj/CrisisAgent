"""add auth users

Revision ID: 0002_auth_users
Revises: 0001_prod_state
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_auth_users"
down_revision = "0001_prod_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="operator"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_role", "users", ["role"])

    op.add_column("approvals", sa.Column("reviewer_id", sa.Integer(), nullable=True))
    op.add_column("approvals", sa.Column("reviewer_username", sa.String(length=128), nullable=False, server_default=""))
    op.add_column("approvals", sa.Column("reviewer_role", sa.String(length=32), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("approvals", "reviewer_role")
    op.drop_column("approvals", "reviewer_username")
    op.drop_column("approvals", "reviewer_id")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
