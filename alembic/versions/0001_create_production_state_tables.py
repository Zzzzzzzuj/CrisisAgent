"""create production state tables

Revision ID: 0001_prod_state
Revises:
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_prod_state"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crisis_sessions",
        sa.Column("session_id", sa.String(length=64), primary_key=True),
        sa.Column("event", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CREATED"),
        sa.Column("final_statement_preview", sa.Text(), nullable=False, server_default=""),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crisis_sessions_status", "crisis_sessions", ["status"])

    op.create_table(
        "agent_checkpoints",
        sa.Column("session_id", sa.String(length=64), sa.ForeignKey("crisis_sessions.session_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("plan_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("event", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CREATED"),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("approval", sa.JSON(), nullable=False),
        sa.Column("failed_agents", sa.JSON(), nullable=False),
        sa.Column("current_agent", sa.String(length=64), nullable=True),
        sa.Column("state_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_checkpoints_status", "agent_checkpoints", ["status"])

    op.create_table(
        "agent_traces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=64), sa.ForeignKey("crisis_sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("start_time", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("end_time", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("trace_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=64), sa.ForeignKey("crisis_sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("reviewer", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("timestamp", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=64), sa.ForeignKey("crisis_sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("evaluator", sa.String(length=128), nullable=False, server_default="runtime"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_session_id", "audit_logs", ["session_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_session_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("evaluations")
    op.drop_table("approvals")
    op.drop_table("agent_traces")
    op.drop_index("ix_agent_checkpoints_status", table_name="agent_checkpoints")
    op.drop_table("agent_checkpoints")
    op.drop_index("ix_crisis_sessions_status", table_name="crisis_sessions")
    op.drop_table("crisis_sessions")
