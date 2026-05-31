"""bots_v3 — add bot_deployments, bot_env_vars, bot_logs tables

Revision ID: d2e5f8a3c906
Revises: c1a9f3e2b047
Create Date: 2026-05-30 00:00:00.000000

Adds three new tables for the V3 execution layer:
  - bot_deployments  (deployment records)
  - bot_env_vars     (per-bot env vars, secrets masked in API)
  - bot_logs         (persistent structured logs)

No existing tables are modified.

Important:
- ENUM types are created once with checkfirst=True.
- Table columns reuse those ENUM types with create_type=False.
- Indexes are created explicitly once; columns do not use index=True.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "d2e5f8a3c906"
down_revision: Union[str, None] = "c1a9f3e2b047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


deployment_status_enum = postgresql.ENUM(
    "pending",
    "prepared",
    "deploying",
    "deployed",
    "failed",
    "stopped",
    name="deployment_status",
)

deployment_source_type_enum = postgresql.ENUM(
    "manual",
    "git",
    "upload",
    name="deployment_source_type",
)

bot_log_level_enum = postgresql.ENUM(
    "info",
    "warning",
    "error",
    "debug",
    name="bot_log_level",
)


def upgrade() -> None:
    bind = op.get_bind()

    # Create ENUM types once. Table columns below reuse them.
    deployment_status_enum.create(bind, checkfirst=True)
    deployment_source_type_enum.create(bind, checkfirst=True)
    bot_log_level_enum.create(bind, checkfirst=True)

    op.create_table(
        "bot_deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "bot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "prepared",
                "deploying",
                "deployed",
                "failed",
                "stopped",
                name="deployment_status",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "source_type",
            postgresql.ENUM(
                "manual",
                "git",
                "upload",
                name="deployment_source_type",
                create_type=False,
            ),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("commit_hash", sa.String(100), nullable=True),
        sa.Column("runtime", sa.String(100), nullable=True),
        sa.Column("main_file", sa.String(255), nullable=True),
        sa.Column("storage_path", sa.String(500), nullable=True),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bot_deployments_bot_id", "bot_deployments", ["bot_id"])
    op.create_index("ix_bot_deployments_status", "bot_deployments", ["status"])

    op.create_table(
        "bot_env_vars",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "bot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("is_secret", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bot_env_vars_bot_id", "bot_env_vars", ["bot_id"])

    op.create_table(
        "bot_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "bot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "deployment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bot_deployments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "level",
            postgresql.ENUM(
                "info",
                "warning",
                "error",
                "debug",
                name="bot_log_level",
                create_type=False,
            ),
            nullable=False,
            server_default="info",
        ),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bot_logs_bot_id", "bot_logs", ["bot_id"])
    op.create_index("ix_bot_logs_deployment_id", "bot_logs", ["deployment_id"])
    op.create_index("ix_bot_logs_created_at", "bot_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("bot_logs")
    op.drop_table("bot_env_vars")
    op.drop_table("bot_deployments")

    bot_log_level_enum.drop(op.get_bind(), checkfirst=True)
    deployment_source_type_enum.drop(op.get_bind(), checkfirst=True)
    deployment_status_enum.drop(op.get_bind(), checkfirst=True)
